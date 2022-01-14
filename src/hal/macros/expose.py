#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


from __future__ import annotations

import asyncio

from hal import config
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["ExposeMacro"]


class ExposeMacro(Macro):
    """Takes a science exposure with APOGEE and/or BOSS."""

    name = "expose"

    __STAGES__ = ["prepare", ("expose_boss", "expose_apogee")]
    __CLEANUP__ = ["cleanup"]

    _exposure_state_apogee: list = [0, 0, True, "A", 0.0]
    _exposure_state_boss: list = [0, 0, 0.0]

    def _reset_internal(self, **opts):
        """Reset the exposure status."""

        self._exposure_state_apogee = [0, 0, True, "A", 0.0]
        self._exposure_state_boss = [0, 0, 0.0]

    async def prepare(self):
        """Prepare for exposures and run checks."""

        do_apogee = "expose_apogee" in self._flat_stages
        do_boss = "expose_boss" in self._flat_stages

        # First check if we are exposing and if we are fail before doing anything else.
        if do_apogee and self.helpers.apogee.is_exposing():
            raise MacroError("APOGEE is already exposing.")

        if do_boss and self.helpers.boss.is_exposing():
            raise MacroError("BOSS is already exposing.")

        # Check lamps. They must be turned off manually (but maybe add a parameter?)
        lamp_status = [lamp[0] for lamp in self.helpers.lamps.list_status().values()]
        if any(lamp_status):
            raise MacroError("Some lamps are on.")

        # Concurrent tasks to run.
        tasks = [self.helpers.ffs.open(self.command)]

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

        self._exposure_state_apogee[3] = self.helpers.apogee.get_dither_position()
        self.command.info(exposure_state_apogee=self._exposure_state_apogee)
        self.command.info(exposure_state_boss=self._exposure_state_boss)

    async def expose_boss(self):
        """Exposes BOSS."""

        count: int = self.config["count_boss"] or self.config["count"]
        assert count, "Invalid number of exposures."

        self._exposure_state_boss[1] = count

        exp_time: float = self.config["boss_exposure_time"]
        assert exp_time, "Invalid exposure time."

        etr_one = (
            config["durations"]["boss_flushing"]
            + exp_time
            + config["durations"]["boss_readout"]
        )

        for n_exp in range(count):
            self._exposure_state_boss[0] = n_exp + 1
            self._exposure_state_boss[2] = (count - n_exp) * etr_one

            self.command.info(exposure_state_boss=self._exposure_state_boss)

            await self.helpers.boss.expose(self.command, exp_time)

    async def expose_apogee(self):
        """Exposes APOGEE."""

        count: int = self.config["count_apogee"] or self.config["count"]
        assert count, "Invalid number of exposures."

        # For APOGEE we report the number of dithers.
        single = self.config["single"]
        if single is False:
            count *= 2

        self._exposure_state_apogee[1] = count
        self._exposure_state_apogee[2] = not single

        boss_exp_time: float = self.config["boss_exposure_time"]
        boss_flushing: float = config["durations"]["boss_flushing"]
        boss_readout: float = config["durations"]["boss_readout"]

        exp_time: float | None = self.config["apogee_exposure_time"]
        if exp_time is None:
            exp_time = boss_exp_time + boss_flushing + boss_readout
            if single is False:
                exp_time /= 2.0

        final_exp_time = exp_time
        if "expose_boss" in self._flat_stages:
            if single:
                final_exp_time = exp_time - boss_readout
            else:
                final_exp_time = exp_time - boss_readout / 2.0

        if self.config["initial_apogee_dither"]:
            await self.helpers.apogee.set_dither_position(
                self.command,
                self.config["initial_apogee_dither"],
            )

        n_full = n_full_left = count - 2 if single is False else count - 1
        n_final_left = 2 if single is False else 1

        current_dither_position = self.helpers.apogee.get_dither_position()
        if current_dither_position is None:
            raise MacroError("Invalid current dither position.")

        if single:
            dither_sequence = current_dither_position * count
        else:
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

            is_final = True if n_exp >= n_full else False
            if is_final is False and n_exp > 0:
                n_final_left -= 1
            if is_final:
                if n_full > 0 and n_full_left > 0:
                    n_full_left -= 1
                elif n_exp > 0:
                    n_final_left -= 1

            self._exposure_state_apogee[0] = n_exp + 1

            etr = n_full_left * exp_time + n_final_left * final_exp_time
            self._exposure_state_apogee[4] = etr

            new_dither_position = dither_sequence[n_exp]
            self._exposure_state_apogee[3] = new_dither_position

            self.command.info(exposure_state_apogee=self._exposure_state_apogee)

            this_exp_time = exp_time if is_final is False else final_exp_time
            await self.helpers.apogee.expose(
                self.command,
                this_exp_time,
                exp_type="object",
                dither_position=new_dither_position,
            )

    async def cleanup(self):
        """Finish the expose macro."""

        pass
