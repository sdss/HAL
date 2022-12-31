#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from dataclasses import dataclass
from time import time

from typing import Any

import numpy

from hal import config
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["ExposeMacro"]


@dataclass
class ExposeParameters:
    """Expose macro parameters."""

    boss_exptime: float | None
    apogee_exptime: float | None
    count_apogee: int | None
    count_boss: int | None
    pairs: bool
    dither: bool
    initial_apogee_dither: str
    readout_matching: bool


@dataclass
class BossExposure:
    """Parameters for a BOSS exposure."""

    n: int
    exptime: float
    actual_exptime: float
    read_sync: bool = True


@dataclass
class ApogeeExposure:
    """Parameters for an APOGEE exposure."""

    n: int
    exptime: float
    dither_position: str


class ExposeHelper:
    """Track exposure status, add/remove exposures, etc."""

    def __init__(self, macro: ExposeMacro, opts: dict[str, Any]):

        self.macro = macro
        self.params = self._update_params(opts)

        if "expose_boss" not in macro._flat_stages:
            self.params.count_boss = None
            self.params.readout_matching = False
        elif "expose_apogee" not in macro._flat_stages:
            self.params.count_apogee = None

        self.observatory = os.environ.get("OBSERVATORY", "APO").upper()

        # Currently running exposure.
        self.n_apogee = 0
        self.n_boss = 0

        # Information about each exposure to take.
        self.apogee_exps: list[ApogeeExposure] = []
        self.boss_exps: list[BossExposure] = []

        self.start_time: float = 0

        self.interval: float = 10
        self._monitor_task: asyncio.Task | None = None

        self.refresh()

    def _update_params(self, opts: dict[str, Any]):
        """Update parameters from the macro config."""

        return ExposeParameters(
            boss_exptime=opts["boss_exptime"],
            apogee_exptime=opts["apogee_exptime"],
            count_apogee=opts["count_apogee"],
            count_boss=opts["count_boss"],
            dither=opts["dither"],
            pairs=opts["pairs"],
            initial_apogee_dither=opts["initial_apogee_dither"],
            readout_matching=opts["readout_matching"],
        )

    async def start(self):
        """Indicate that exposures are starting. Output states on a timer."""

        self.start_time = time()
        self._monitor_task = asyncio.create_task(self._monitor())

    async def stop(self):
        """Stops the monitoring task."""

        if self._monitor_task:
            self._monitor_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._monitor_task

        self._monitor_task = None

    async def _monitor(self):
        """Outputs states at intervals."""

        while True:
            self.update_status()
            await asyncio.sleep(self.interval)

    @property
    def running(self):
        """Returns whether the exposures are running."""

        n_apogee = len(self.apogee_exps)
        n_boss = len(self.boss_exps)

        apogee_running = self.n_apogee > 0 and self.n_apogee < n_apogee
        boss_running = self.n_boss > 0 and self.n_boss < n_boss

        return apogee_running or boss_running

    def refresh(self):
        """Refreshes the list of exposures."""

        self._refresh_boss()
        self._refresh_apogee()

        self.update_status()

    def _refresh_boss(self):
        """Refreshes the list of BOSS exposures."""

        count = self.params.count_boss
        exptime = self.params.boss_exptime

        if exptime is None:
            return

        if count is None or count == 0 or count == len(self.boss_exps):
            return

        # We don't allow to reduce the number of exposures
        # below the one already being taken.
        if count < self.n_boss:
            count = self.params.count_boss = self.n_boss

        flushing = config["durations"]["boss"][self.observatory]["flushing"]
        readout = config["durations"]["boss"][self.observatory]["readout"]

        if count > len(self.boss_exps):
            # Add exposures. Do not touch exposures already completed or
            # in process. Set actual_exptime to zero for now. We'll set it next.
            for ii in range(self.n_boss + 1, count + 1):
                new = BossExposure(n=ii, exptime=exptime, actual_exptime=0.0)
                self.boss_exps.append(new)
        else:
            # Pop any exposures beyond the count number. Count cannot be
            # smaller than the current exposure.
            while len(self.boss_exps) > count:
                self.boss_exps.pop()

        # Reset the actual time an exposure will take. This is fine to do
        # at any point (I think). For the last exposure, we do not read the
        # exposure synchronously, and we assume the actual exposure time does
        # not include readout.
        for nexp, exp in enumerate(self.boss_exps):
            exp.actual_exptime = exp.exptime + flushing + readout
            exp.read_sync = True
            if nexp == len(self.boss_exps) - 1:
                exp.actual_exptime -= readout
                exp.read_sync = False

    def _refresh_apogee(self):
        """Refreshes the list of APOGEE exposures."""

        initial_dither = self.params.initial_apogee_dither
        pairs = self.params.pairs
        count = self.params.count_apogee

        if count is None or count == 0 or count == len(self.apogee_exps):
            return

        # We consider count the number of actual exposures, not dither pairs.
        if pairs:
            count *= 2

        # We don't allow to reduce the number of exposures below the one
        # already being taken. If doing dither pairs, we require completing them.
        if count < self.n_apogee:
            if pairs:
                self.params.count_apogee = self.n_apogee + self.n_apogee % 2
            else:
                self.params.count_apogee = self.n_apogee
            count = self.params.count_apogee

        exposure_times: list[float] = []

        if self.params.readout_matching:
            # We are matching exposure times. We use the BOSS exposure time as
            # reference to determine the full APOGEE exposure time.

            boss_exptime = self.params.boss_exptime
            flushing: float = config["durations"]["boss"][self.observatory]["flushing"]
            readout: float = config["durations"]["boss"][self.observatory]["readout"]

            if boss_exptime is None or boss_exptime == 0:
                return

            apogee_exptime = boss_exptime + flushing + readout

            # If we are doing pairs, the full exposure time corresponds to a pair.
            if pairs:
                apogee_exptime /= 2.0

            exposure_times = [apogee_exptime] * count

            # The last exposure (or two exposures if doing pairs) must be one BOSS
            # readout shorter. If pairs, we distribute that between the two dither
            # positions.
            if pairs:
                last_exptime = apogee_exptime - readout / 2.0
                exposure_times[-2:] = [last_exptime, last_exptime]
            else:
                exposure_times[-1] = apogee_exptime - readout

        else:
            # We are not matching readout times. Just exposure as many APOGEE
            # exposures/pairs as needed.

            apogee_exptime = self.params.apogee_exptime
            if apogee_exptime is None or apogee_exptime == 0:
                return

            exposure_times = [apogee_exptime] * count

        # Round up exposure times.
        exposure_times = list(numpy.ceil(exposure_times))

        dither_sequence = ""
        if self.params.dither is False:
            # If disable_dithering, just keep using the current dither position.
            dither_sequence = initial_dither * count
        else:
            # If we are dithering, the sequence starts on the current position
            # and changes every two dithers to minimise how much we move the
            # mechanism, e.g., ABBAABBA.
            current_dither_position = initial_dither
            dither_sequence = current_dither_position
            for i in range(1, count):
                if i % 2 != 0:
                    if dither_sequence[-1] == "A":
                        dither_sequence += "B"
                    else:
                        dither_sequence += "A"
                else:
                    dither_sequence += dither_sequence[-1]

        if count < len(self.apogee_exps):
            # Pop any exposures beyond the count number. Count cannot be
            # smaller than the current exposure.
            while len(self.boss_exps) > count:
                self.boss_exps.pop()

            return

        # Add exposures. Do not touch exposures already completed or in process.
        # Minimum exposure we can modify.
        min_exp = self.n_apogee + 1
        if pairs:
            min_exp = self.n_apogee + self.n_apogee % 2 + 1

        for ii in range(min_exp, count + 1):
            new = ApogeeExposure(
                n=ii,
                exptime=exposure_times[ii - 1],
                dither_position=dither_sequence[ii - 1],
            )
            self.apogee_exps.append(new)

    def yield_apogee(self):
        """Returns an iterator of APOGEE exposures."""

        while self.n_apogee < len(self.apogee_exps):
            self.n_apogee += 1
            self.update_status("apogee")
            yield self.apogee_exps[self.n_apogee - 1]

        self.update_status("apogee")
        yield None

    def yield_boss(self):
        """Returns an iterator of BOSS exposures."""

        while self.n_boss < len(self.boss_exps):
            self.n_boss += 1
            self.update_status("boss")
            yield self.boss_exps[self.n_boss - 1]

        self.update_status("boss")
        yield None

    def update_status(self, instrument: str | None = None):
        """Emits the exposure status keywords."""

        # Incomplete state. Just filling out the easy bits.
        state_apogee: dict = {
            "current": self.n_apogee,
            "n": len(self.apogee_exps),
            "pairs": self.params.pairs,
            "dither": "A",
            "etr": 0.0,
            "total_time": 0.0,
            "timestamp": 0,
        }

        state_boss: dict = {
            "current": self.n_boss,
            "n": len(self.boss_exps),
            "etr": 0.0,
            "total_time": 0.0,
            "timestamp": 0,
        }

        if not hasattr(self.macro, "command"):
            return

        if (instrument is None or instrument == "apogee") and len(self.apogee_exps) > 0:
            exps = self.apogee_exps

            if self.n_apogee == 0:
                state_apogee["dither"] = exps[0].dither_position
            else:
                state_apogee["dither"] = exps[self.n_apogee - 1].dither_position

            state_apogee["total_time"] = int(round(sum([exp.exptime for exp in exps])))
            state_apogee["timestamp"] = round(time(), 1)

            etr = state_apogee["total_time"]
            if self.start_time > 0:
                elapsed = time() - self.start_time
                etr -= elapsed
                if etr < 0:
                    etr = 0
            state_apogee["etr"] = int(round(etr))

            self.macro.command.debug(exposure_state_apogee=list(state_apogee.values()))

        if (instrument is None or instrument == "boss") and len(self.boss_exps) > 0:
            exps = self.boss_exps

            total_time = sum([exp.actual_exptime for exp in exps])
            state_boss["total_time"] = int(round(total_time))

            state_boss["timestamp"] = round(time(), 1)

            etr = state_boss["total_time"]
            if self.start_time > 0:
                elapsed = time() - self.start_time
                etr -= elapsed
                if etr < 0:
                    etr = 0
            state_boss["etr"] = int(round(etr))

            self.macro.command.debug(exposure_state_boss=list(state_boss.values()))


class ExposeMacro(Macro):
    """Takes a science exposure with APOGEE and/or BOSS."""

    name = "expose"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = [("expose_boss", "expose_apogee")]
    __CLEANUP__ = ["cleanup"]

    expose_helper: ExposeHelper

    def _reset_internal(self, **opts):
        """Reset the exposure status."""

        self.expose_helper = ExposeHelper(self, opts)

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
            lamp_st = [lamp[0] for lamp in self.helpers.lamps.list_status().values()]
            if any(lamp_st):
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

        # Tell the helper that we're about to start exposing.
        await self.expose_helper.start()

    async def expose_boss(self):
        """Exposes BOSS."""

        # Just in case there's a readout pending from some previous error. Although
        # maybe it's better to have to manually force this. Note that this does not
        # abort or clear an exposure at the ICC level, just the internal tracking
        # in HAL.
        self.helpers.boss.clear_readout()

        for exposure_info in self.expose_helper.yield_boss():
            if exposure_info is None:
                break

            await self.helpers.boss.expose(
                self.command,
                exposure_info.exptime,
                read_async=True,
            )

            # Except for the final exposure, we wait until the readout is complete.
            if exposure_info.read_sync:
                await self.helpers.boss.readout(self.command)

    async def expose_apogee(self):
        """Exposes APOGEE."""

        for exposure_info in self.expose_helper.yield_apogee():
            if exposure_info is None:
                break

            await self.helpers.apogee.expose(
                self.command,
                exposure_info.exptime,
                exp_type="object",
                dither_position=exposure_info.dither_position,
            )

    async def cleanup(self):
        """Cancel any running exposures."""

        await self.expose_helper.stop()

        # Close the APOGEE cold shutter.
        if "expose_apogee" in self._flat_stages:
            self.command.info("Closing APOGEE shutter.")
            await self.helpers.apogee.shutter(
                self.command,
                open=False,
                shutter="apogee",
            )

        if not self.failed:
            return

        if self.helpers.apogee.is_exposing():
            self.command.warning("APOGEE exposure is running. Not cancelling it.")

        if self.helpers.boss.is_exposing():
            self.command.warning("BOSS exposure is running. Not cancelling it.")
