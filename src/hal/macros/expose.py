#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


from __future__ import annotations

import asyncio
from time import time

import numpy

from hal import config
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["ExposeMacro"]


class ExposeMacro(Macro):
    """Takes a science exposure with APOGEE and/or BOSS."""

    name = "expose"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = [("expose_boss", "expose_apogee")]
    __CLEANUP__ = ["cleanup"]

    _state_apogee: dict = {
        "current": 0,
        "n": 0,
        "pairs": True,
        "dither": "A",
        "etr": 0.0,
        "total_time": 0.0,
        "timestamp": 0,
    }

    _state_boss: dict = {
        "current": 0,
        "n": 0,
        "etr": 0.0,
        "total_time": 0.0,
        "timestamp": 0,
    }

    def _reset_internal(self, **opts):
        """Reset the exposure status."""

        self._state_apogee = ExposeMacro._state_apogee.copy()
        self._state_boss = ExposeMacro._state_boss.copy()

    async def prepare(self):
        """Prepare for exposures and run checks."""

        do_apogee = "expose_apogee" in self._flat_stages
        do_boss = "expose_boss" in self._flat_stages

        # First check if we are exposing and if we are fail before doing anything else.
        if do_apogee and self.helpers.apogee.is_exposing():
            raise MacroError("APOGEE is already exposing.")

        if do_boss and self.helpers.boss.is_exposing():
            raise MacroError("BOSS is already exposing.")

        if do_apogee and self.command.actor.observatory != "LCO":
            if not self.command.actor.helpers.apogee.gang_helper.at_cartridge():
                raise MacroError("The APOGEE gang connector is not at the cart.")

        # Check that IEB FBI are off.
        try:
            cmd = await self.send_command("jaeger", "ieb status")
            fbi_led1, fbi_led2, *_ = cmd.replies.get("fbi_led")
        except (MacroError, KeyError):
            fbi_led1 = fbi_led2 = 0.0
            self.command.warning("Failed getting FBI levels but moving on.")

        if float(fbi_led1) > 0.1 or float(fbi_led2) > 0.1:
            raise MacroError("FBI LEDs are not off.")

        # Check lamps. They must be turned off manually (but maybe add a parameter?)
        if self.command.actor.observatory == "APO":
            lamp_status = [
                lamp[0] for lamp in self.helpers.lamps.list_status().values()
            ]
            if any(lamp_status):
                raise MacroError("Some lamps are on.")
        else:
            self.command.warning("Skipping lamps check for now.")

        # Concurrent tasks to run.
        tasks = []
        if self.command.actor.observatory == "APO":
            tasks.append(self.helpers.ffs.open(self.command))

        if do_apogee:
            initial_dither = self.config["initial_apogee_dither"]
            if initial_dither:
                tasks.append(
                    self.helpers.apogee.set_dither_position(
                        self.command,
                        initial_dither,
                    )
                )

            tasks.append(
                self.helpers.apogee.shutter(
                    self.command,
                    open=True,
                    shutter="apogee",
                )
            )

            if self.config["with_fpi"]:
                tasks.append(
                    self.helpers.apogee.shutter(
                        self.command,
                        open=True,
                        shutter="fpi",
                    )
                )

        await asyncio.gather(*tasks)

        self._state_apogee["dither"] = self.helpers.apogee.get_dither_position()
        self.command.info(exposure_state_apogee=list(self._state_apogee.values()))
        self.command.info(exposure_state_boss=list(self._state_boss.values()))

    async def expose_boss(self):
        """Exposes BOSS."""

        if self.config["boss"] is False:
            return

        count: int = self.config["count_boss"] or self.config["count"]
        assert count, "Invalid number of exposures."

        self._state_boss["n"] = count

        exp_time: float = self.config["boss_exposure_time"]
        assert exp_time, "Invalid exposure time."

        # Just in case there's a readout pending from some previous error. Although
        # maybe it's better to have to manually force this.
        self.helpers.boss.clear_readout()

        etr_one = (
            config["durations"]["boss_flushing"]
            + exp_time
            + config["durations"]["boss_readout"]
        )
        self._state_boss["total_time"] = count * etr_one

        for n_exp in range(count):
            self._state_boss["current"] = n_exp + 1
            self._state_boss["etr"] = (count - n_exp) * etr_one

            # Timestamp
            self._state_boss["timestamp"] = time()

            self.command.info(exposure_state_boss=list(self._state_boss.values()))

            await self.helpers.boss.expose(self.command, exp_time)

    async def expose_apogee(self):
        """Exposes APOGEE."""

        if self.config["apogee"] is False:
            return

        count: int = self.config["count_apogee"] or self.config["count"]
        assert count, "Invalid number of exposures."

        # For APOGEE we report the number of dithers.
        pairs = self.config["pairs"]
        if pairs:
            count *= 2

        self._state_apogee["n"] = count
        self._state_apogee["pairs"] = pairs

        boss_exp_time: float = self.config["boss_exposure_time"]
        boss_flushing: float = config["durations"]["boss_flushing"]
        boss_readout: float = config["durations"]["boss_readout"]

        # If the exposure time for APOGEE is not set, use the one for BOSS
        # but divide by two if we are doing dither pairs. Otherwise just use
        # apogee_exposure_time is always per exposure (rewardless of whether we
        # are doing dither pairs or single exposures).
        apogee_exp_time: float | None = self.config["apogee_exposure_time"]
        if apogee_exp_time is None:
            readout_match = True
            apogee_exp_time = boss_exp_time + boss_flushing + boss_readout
            if pairs:
                apogee_exp_time /= 2.0
        else:
            readout_match = False

        # Initially we assume all the exposures have the same exposure time.
        exposure_times = [apogee_exp_time] * count

        # We want the final exposure or dither pair to finish as the BOSS readout
        # begins. This allows us to do something during readout like slewing or
        # folding the FPS. We calculate an exposure time for the last exposure/pair
        # by removing the BOSS readout time.
        if "expose_boss" in self._flat_stages and readout_match is True:
            if pairs:
                last_exp_time = apogee_exp_time - boss_readout / 2.0
                exposure_times[-2:] = [last_exp_time, last_exp_time]
            else:
                last_exp_time = apogee_exp_time - boss_readout
                exposure_times[-1] = last_exp_time

        exposure_times = numpy.ceil(exposure_times)
        self._state_apogee["total_time"] = sum(exposure_times)

        # Set the first dither and determine the dither sequence.
        if self.config["initial_apogee_dither"]:
            await self.helpers.apogee.set_dither_position(
                self.command,
                self.config["initial_apogee_dither"],
            )

        current_dither_position = self.helpers.apogee.get_dither_position()
        if current_dither_position is None:
            raise MacroError("Invalid current dither position.")

        if self.config["disable_dithering"]:
            # If disable_dithering, just keep using the current dither position.
            dither_sequence = current_dither_position * count
        else:
            # If we are dithering, the sequence starts on the current position
            # and changes every two dithers to minimise how much we move the
            # mechanism, e.g., ABBAABBA.
            dither_sequence = current_dither_position
            for i in range(1, count):
                if i % 2 != 0:
                    if dither_sequence[-1] == "A":
                        dither_sequence += "B"
                    else:
                        dither_sequence += "A"
                else:
                    dither_sequence += dither_sequence[-1]

        for n_exp in range(count):

            self._state_apogee["current"] = n_exp + 1

            etr = sum(exposure_times[n_exp:])
            self._state_apogee["etr"] = etr

            new_dither_position = dither_sequence[n_exp]
            self._state_apogee["dither"] = new_dither_position

            # Timestamp
            self._state_apogee["timestamp"] = time()

            self.command.info(exposure_state_apogee=list(self._state_apogee.values()))

            await self.helpers.apogee.expose(
                self.command,
                exposure_times[n_exp],
                exp_type="object",
                dither_position=new_dither_position,
            )

    async def cleanup(self):
        """Cancel any running exposures."""

        if not self.failed:
            return

        # Wait a bit to give APOGEE or BOSS time to update exposureStatus if the
        # macro failed very quickly.
        await asyncio.sleep(5)

        if self.helpers.apogee.is_exposing():
            self.command.warning("APOGEE exposure is running. Not cancelling it.")

        if self.helpers.boss.is_exposing():
            self.command.warning("BOSS exposure is running. Not cancelling it.")

        # Close the APOGEE cold shutter.
        if "expose_apogee" in self._flat_stages:
            await self.helpers.apogee.shutter(
                self.command,
                open=False,
                shutter="apogee",
            )
