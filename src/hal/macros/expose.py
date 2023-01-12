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

import numpy

from hal import config
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["ExposeMacro"]


@dataclass
class ExposeParameters:
    """Expose macro parameters."""

    boss_exptime: float | None = config["macros"]["expose"]["fallback"]["exptime"]
    apogee_exptime: float | None = None
    count_apogee: int | None = 1
    count_boss: int | None = 1
    pairs: bool = True
    dither: bool = True
    initial_apogee_dither: str = "A"
    readout_matching: bool = True


@dataclass
class BossExposure:
    """Parameters for a BOSS exposure."""

    n: int
    exptime: float
    actual_exptime: float
    read_sync: bool = True
    done: bool = False


@dataclass
class ApogeeExposure:
    """Parameters for an APOGEE exposure."""

    n: int
    exptime: float
    dither_position: str
    done: bool = False


class ExposeHelper:
    """Track exposure status, add/remove exposures, etc."""

    def __init__(self, macro: ExposeMacro, **opts):
        self.macro = macro

        self.observatory = os.environ.get("OBSERVATORY", "APO").upper()

        # Currently running exposure.
        self.n_apogee = 0
        self.n_boss = 0

        # Information about each exposure to take.
        self.apogee_exps: list[ApogeeExposure] = []
        self.boss_exps: list[BossExposure] = []

        self._apogee_exp_start_time: float = 0
        self._boss_exp_start_time: float = 0

        self.interval: float = 10
        self._monitor_task: asyncio.Task | None = None

        self.params: ExposeParameters = ExposeParameters()
        self.update_params(**opts)

        self.refresh()

    def update_params(self, **opts):
        """Update parameters from the macro config."""

        # Exclude options that are not in the dataclass.
        valid_opts = {
            opt: opts[opt]
            for opt in opts
            if opt in ExposeParameters.__dataclass_fields__
        }

        if self.running:
            valid_opts["initial_apogee_dither"] = self.params.initial_apogee_dither

        self.params.__dict__.update(**valid_opts)

        if "expose_boss" not in self.macro.flat_stages:
            self.params.count_boss = None
            self.params.readout_matching = False
        elif "expose_apogee" not in self.macro.flat_stages:
            self.params.count_apogee = None

        return self.params

    async def start(self):
        """Indicate that exposures are starting. Output states on a timer."""

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

        if exptime is None or count is None or count == 0:
            return

        # We don't allow to reduce the number of exposures
        # below the one already being taken.
        if count < self.n_boss:
            count = self.params.count_boss = self.n_boss

        flushing = config["durations"]["boss"][self.observatory]["flushing"]
        readout = config["durations"]["boss"][self.observatory]["readout"]

        if count < len(self.boss_exps):
            # Pop any exposures beyond the count number. Count cannot be
            # smaller than the current exposure.
            while len(self.boss_exps) > count and len(self.boss_exps) >= self.n_boss:
                self.boss_exps.pop()

        # Replace/append exposures, but only for those that have not been executed
        # or are not being executed.
        # Minimum exposure index that we can modify.
        min_exp_idx = 0 if self.n_boss == 0 else self.n_boss
        for ii in range(min_exp_idx, count):
            # Set actual_exptime to zero for now. We'll set it next.
            new = BossExposure(n=ii + 1, exptime=exptime, actual_exptime=0.0)

            # Replace existing exposures, or append if extending.
            if len(self.boss_exps) >= ii + 1:
                self.boss_exps[ii] = new
            else:
                self.boss_exps.append(new)

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
        n_exp = self.params.count_apogee

        if n_exp is None or n_exp == 0:
            return

        # We consider n_exp the number of actual exposures, not dither pairs.
        if pairs:
            n_exp *= 2

        # We don't allow to reduce the number of exposures below the one
        # already being taken. If doing dither pairs, we require completing them.
        if n_exp < self.n_apogee:
            if pairs:
                n_exp = self.n_apogee + self.n_apogee % 2
            else:
                n_exp = self.n_apogee

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

            exposure_times = [apogee_exptime] * n_exp

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

            exposure_times = [apogee_exptime] * n_exp

        # Round up exposure times.
        exposure_times = list(numpy.ceil(exposure_times))

        dither_sequence = ""
        if self.params.dither is False:
            # If disable_dithering, just keep using the current dither position.
            dither_sequence = initial_dither * n_exp
        else:
            # If we are dithering, the sequence starts on the current position
            # and changes every two dithers to minimise how much we move the
            # mechanism, e.g., ABBAABBA.
            current_dither_position = initial_dither
            dither_sequence = current_dither_position
            for i in range(1, n_exp):
                if i % 2 != 0:
                    if dither_sequence[-1] == "A":
                        dither_sequence += "B"
                    else:
                        dither_sequence += "A"
                else:
                    dither_sequence += dither_sequence[-1]

        if n_exp < len(self.apogee_exps):
            n_apogee = self.n_apogee
            # Pop any exposures beyond n_exp. n_exp cannot be
            # smaller than the current exposure.
            while len(self.apogee_exps) > n_exp and len(self.apogee_exps) >= n_apogee:
                self.apogee_exps.pop()

        # Replace/append exposures, but only for those that have not been executed
        # or are not being executed.

        # Minimum exposure index that we can modify. Preserve full dither sets.
        if pairs is False:
            min_exp_idx = 0 if self.n_apogee == 0 else self.n_apogee
        else:
            min_exp_idx = 0 if self.n_apogee == 0 else self.n_apogee + self.n_apogee % 2

        for ii in range(min_exp_idx, n_exp):
            new = ApogeeExposure(
                n=ii + 1,
                exptime=exposure_times[ii],
                dither_position=dither_sequence[ii],
            )

            # Replace existing exposures, or append if extending.
            if len(self.apogee_exps) >= ii + 1:
                self.apogee_exps[ii] = new
            else:
                self.apogee_exps.append(new)

    def yield_apogee(self):
        """Returns an iterator of APOGEE exposures."""

        while self.n_apogee < len(self.apogee_exps):
            self.n_apogee += 1
            self._apogee_exp_start_time = time()
            self.update_status("apogee")
            yield self.apogee_exps[self.n_apogee - 1]

        self.update_status("apogee")
        yield None

    def yield_boss(self):
        """Returns an iterator of BOSS exposures."""

        while self.n_boss < len(self.boss_exps):
            self.n_boss += 1
            self._boss_exp_start_time = time()
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
            this_exp = exps[self.n_apogee - 1] if self.n_apogee > 0 else None

            if self.n_apogee == 0:
                state_apogee["dither"] = exps[0].dither_position
            else:
                state_apogee["dither"] = exps[self.n_apogee - 1].dither_position

            state_apogee["total_time"] = int(round(sum([exp.exptime for exp in exps])))
            state_apogee["timestamp"] = round(time(), 1)

            n_completed = 0 if self.n_apogee == 0 else self.n_apogee - 1
            if this_exp and this_exp.done:
                n_completed += 1

            etr = state_apogee["total_time"]
            etr -= sum([exps[ii].exptime for ii in range(0, n_completed)])
            if self._apogee_exp_start_time > 0 and this_exp and not this_exp.done:
                exp_elapsed = time() - self._apogee_exp_start_time
                etr -= exp_elapsed
                if etr < 0:
                    etr = 0
            state_apogee["etr"] = int(round(etr))

            self.macro.command.debug(exposure_state_apogee=list(state_apogee.values()))

        if (instrument is None or instrument == "boss") and len(self.boss_exps) > 0:
            exps = self.boss_exps
            this_exp = exps[self.n_boss - 1] if self.n_boss > 0 else None

            total_time = sum([exp.actual_exptime for exp in exps])
            state_boss["total_time"] = int(round(total_time))

            state_boss["timestamp"] = round(time(), 1)

            n_completed = 0 if self.n_boss == 0 else self.n_boss - 1
            if this_exp and this_exp.done:
                n_completed += 1

            etr = state_boss["total_time"]
            etr -= sum([exps[ii].actual_exptime for ii in range(0, n_completed)])
            if self._boss_exp_start_time > 0 and this_exp and not this_exp.done:
                exp_elapsed = time() - self._boss_exp_start_time
                etr -= exp_elapsed
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
    _pause_event = asyncio.Event()

    def _reset_internal(self, **opts):
        """Reset the exposure status."""

        self.expose_helper = ExposeHelper(self, **opts)

        # An event blocker for when we wait to pause the execution of the macro.
        if not self._pause_event.is_set():
            self._pause_event.set()

    async def prepare(self):
        """Prepare for exposures and run checks."""

        self.command.debug(expose_is_paused=False)

        do_apogee = "expose_apogee" in self.flat_stages
        do_boss = "expose_boss" in self.flat_stages

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

        await self._pause_event.wait()

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

            exposure_info.done = True

            # We wait at the end of the loop so that if a new exposure is
            # added while we are paused, the next iteration of the loop
            # will yield it.
            await self._pause_event.wait()

            # If we have added exposures while paused and the expose, then
            # this exposure readout will have become sync so we give it another
            # try.
            if exposure_info.read_sync and self.helpers.boss.readout_pending:
                await self.helpers.boss.readout(self.command)

    async def expose_apogee(self):
        """Exposes APOGEE."""

        await self._pause_event.wait()

        for exposure_info in self.expose_helper.yield_apogee():
            if exposure_info is None:
                break

            await self.helpers.apogee.expose(
                self.command,
                exposure_info.exptime,
                exp_type="object",
                dither_position=exposure_info.dither_position,
            )

            exposure_info.done = True

            await self._pause_event.wait()

    async def cleanup(self):
        """Cancel any running exposures."""

        await self.expose_helper.stop()

        # Close the APOGEE cold shutter.
        if "expose_apogee" in self.flat_stages:
            self.command.info("Closing APOGEE shutter.")
            await self.helpers.apogee.shutter(
                self.command,
                open=False,
                shutter="apogee",
            )

        if self.helpers.apogee.is_exposing():
            self.command.warning("APOGEE exposure is running. Not cancelling it.")

        if self.helpers.boss.is_exposing():
            if self.helpers.boss.is_reading():
                self.command.info("BOSS is reading.")
            else:
                self.command.warning("BOSS exposure is running. Not cancelling it.")

    async def _pause(self):
        """Pauses the execution of the macro."""

        if self._pause_event.is_set():
            self._pause_event.clear()
            self.command.warning("Pausing execution of the expose macro.")
            self.command.debug(expose_is_paused=True)
        else:
            self.command.warning("Macro is already paused.")
            self.command.debug(expose_is_paused=True)

    async def _resume(self):
        """Resumes the execution of the macro."""

        if not self._pause_event.is_set():
            self._pause_event.set()
            self.command.warning("Resuming execution of the expose macro.")
            self.command.debug(expose_is_paused=False)
        else:
            self.command.warning("Macro is already running.")
            self.command.debug(expose_is_paused=False)
