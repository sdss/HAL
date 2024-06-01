#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-05-21
# @Filename: auto_pilot.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sdsstools.utils import cancel_task

from hal import config
from hal.exceptions import MacroError
from hal.helpers import get_default_exposure_time
from hal.macros.expose import ExposeMacro
from hal.macros.macro import Macro


__all__ = ["AutoPilotMacro"]


@dataclass
class SystemState:
    """Stores the state of the system."""

    macro: AutoPilotMacro

    apogee_exposure_state: str | None = None
    boss_exposure_state: str | None = None

    apogee_exposure_time_remaining: float = 0
    boss_exposure_time_remaining: float = 0
    exposure_time_remaining: float = 0

    def update_exposure_state(self):
        """Updates the exposure state for the current exposures."""

        try:
            self.apogee_exposure_state = self.macro.helpers.apogee.get_exposure_state()
        except ValueError:
            self.apogee_exposure_state = None

        try:
            self.boss_exposure_state = self.macro.helpers.boss.get_exposure_state()
        except ValueError:
            self.boss_exposure_state = None

    def update_time_remaining(self):
        """Updates the remaining time for the current exposures."""

        self.apogee_time_remaining = self.macro.helpers.apogee.exposure_time_remaining
        self.boss_time_remaining = self.macro.helpers.boss.exposure_time_remaining

        self.exposure_time_remaining = max(
            self.apogee_time_remaining,
            self.boss_time_remaining,
        )

    async def wait_integration_done(self, wait_readout_done: bool = False):
        """Blocks until the spectrographs are not exposing."""

        while True:
            apogee_exposing = self.macro.helpers.apogee.is_exposing()
            boss_exposing = self.macro.helpers.boss.is_exposing()

            if apogee_exposing or boss_exposing:
                await asyncio.sleep(1)
                continue

            if wait_readout_done and self.macro.helpers.boss.readout_pending:
                self.macro._auto_pilot_message("Waiting for BOSS to read out")
                await self.macro.helpers.boss.readout(self.macro.command)

            break


class AutoPilotMacro(Macro):
    """Auto pilot macro."""

    name = "auto_pilot"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = ["load", "goto_field", "expose"]
    __CLEANUP__ = ["cleanup"]

    def __init__(self):
        super().__init__()

        self.system_state = SystemState(self)

        self._hartmann: bool = False
        self._preload_task: asyncio.Task | None = None

    @property
    def hartmann(self):
        """Returns whether a Hartmann is scheduled."""

        return self._hartmann

    @hartmann.setter
    def hartmann(self, value: bool):
        """Sets whether a Hartmann is to be scheduled."""

        self._hartmann = value

        if self.command:
            self.command.debug(auto_pilot_hartmann=value)

    async def prepare(self):
        """Prepares the auto pilot."""

        # Update spectrograph states.
        self.system_state.update_exposure_state()
        self.system_state.update_time_remaining()

        # If we don't know about the spec states, fail.
        if self.system_state.apogee_exposure_state is None:
            raise MacroError("Cannot determine APOGEE exposure state.")
        if self.system_state.boss_exposure_state is None:
            raise MacroError("Cannot determine BOSS exposure state.")

        # Is there a configuration loaded and has it been observed?
        configuration = self.helpers.jaeger.configuration
        observed = configuration and configuration.observed

        if self.system_state.exposure_time_remaining > 0:
            # We are exposing.
            if self.helpers.jaeger.preloaded or not observed:
                # There is already a preloaded configuration. Just wait
                # until the exposure is done.
                self._auto_pilot_message("Waiting for exposure before loading design")

            else:
                # We need to preload a design.
                await self._preload_design()

            # Now wait until the exposure is done.
            await self.system_state.wait_integration_done()

    async def load(self):
        """Loads a new design."""

        configuration = self.helpers.jaeger.configuration

        if self.helpers.jaeger.preloaded:
            self._auto_pilot_message("Loading preloaded configuration")

            try:
                await self.helpers.jaeger.from_preloaded(self.command)
            except Exception as ee:
                # This mostly can happen if jaeger is restarted after preloading a
                # configuration that HAL had tracked but after the restart does not
                # exist anymore.

                self._auto_pilot_message(f"Preloaded configuration failed: {ee}.", "w")

                self.helpers.jaeger.preloaded = None
                if configuration:
                    configuration.observed = True

                await self.load()
                return

        elif configuration and not configuration.observed:
            self._auto_pilot_message("Found unobserved configuration")

        else:
            self._auto_pilot_message("Loading new design from the queue")
            if not await self.helpers.jaeger.load_from_queue(self.command):
                raise MacroError("Failed loading design")

        # Make sure everything all keywords have been emitted and database queries run.
        await asyncio.sleep(1)

        if not self.helpers.jaeger.configuration:
            raise MacroError("Failed loading design. No active configuration.")

        c_id = self.helpers.jaeger.configuration.configuration_id
        d_id = self.helpers.jaeger.configuration.design_id
        self._auto_pilot_message(f"Processign configuration {c_id} ({d_id})")

    async def goto_field(self):
        """Runs the go-to field procedure."""

        goto_macro = self.helpers.macros["goto_field"]
        if goto_macro.running:
            self._auto_pilot_message("Waiting for goto-field macro to complete", "w")
            if not await goto_macro.wait_until_complete():
                raise MacroError("Background goto-field failed. Cancelling auto mode.")

        configuration = self.helpers.jaeger.configuration
        if configuration is None:
            raise MacroError("No configuration loaded.")

        if configuration.goto_complete:
            self._auto_pilot_message("Goto-field already complete")
            return

        stages = configuration.get_goto_field_stages()

        if len(stages) == 0:  # For cloned designs.
            self._auto_pilot_message("Skipping goto-field")
            return

        if self.hartmann and "boss_hartmann" not in stages:
            stages.append("boss_hartmann")

        self._auto_pilot_message("Running goto-field")
        goto_macro.reset(self.command, stages)

        result = await goto_macro.run()

        if self.hartmann and "boss_hartmann" in stages:
            self.hartmann = False

        if not result:
            raise MacroError("Goto-field failed during auto pilot mode.")

    async def expose(self):
        """Exposes the cameras."""

        expose_macro = self.helpers.macros["expose"]
        if expose_macro.running:
            # This should not generally happen because in prepare we waited until any
            # previous exposure was done and reading.
            self._auto_pilot_message("Waiting for expose macro to complete", "w")
            if not await expose_macro.wait_until_complete():
                raise MacroError("Background expose failed. Cancelling auto mode.")

        # Wait until previous exposures are done and read.
        self._auto_pilot_message("Waiting for previous exposures to finish")
        await self.system_state.wait_integration_done(wait_readout_done=True)

        # Make sure guiding is good enough to start exposing.
        if not self.helpers.cherno.is_guiding():
            raise MacroError("Guider is not running. Cannot expose.")

        min_rms = self.config["min_rms"]
        if not self.helpers.cherno.guiding_at_rms(min_rms):
            self._auto_pilot_message("Waiting for guider to converge")
            try:
                await self.helpers.cherno.wait_for_rms(min_rms, max_wait=180)
            except asyncio.TimeoutError:
                raise MacroError("Timed out waiting for guider to converge.")

        # Calculate expose time and schedule preloading a design.
        # The exposure time depends on the design mode.
        design_mode: str | None = None
        if self.helpers.jaeger.configuration:
            design_mode = self.helpers.jaeger.configuration.design_mode
        exptime = get_default_exposure_time(self.actor.observatory, design_mode)

        count = self.config["count"]
        flushing = config["durations"]["boss"][self.actor.observatory]["flushing"]
        readout = config["durations"]["boss"][self.actor.observatory]["readout"]
        total_time = (exptime + flushing + readout) * count - readout

        # Reset the exposure macro to update ETR but do not start the exposures yet.
        expose_macro.reset(
            self.command,
            count_boss=count,
            count_apogee=count,
            boss_exptime=exptime,
            apogee_exptime=exptime,
        )

        # Calculate the time to preload the next design and schedule it. This may
        # change if the count changes and the ETR does too.
        preload_ahead = self.config["preload_ahead_time"]
        wait_design_load = int(total_time - preload_ahead)
        self._auto_pilot_message(f"Scheduling preload in {wait_design_load} s")

        await self._cancel_preload_task()
        self._preload_task = asyncio.create_task(self._schedule_preload(preload_ahead))

        self._auto_pilot_message("Exposing cameras")
        if not await expose_macro.run():
            raise MacroError("Expose failed during auto mode.")

    async def cleanup(self):
        """Cleans up after the auto pilot."""

        if self.cancelled:
            await self._cancel_preload_task()

    def _auto_pilot_message(self, message: str, level: str = "i"):
        """Emits a message using the ``auto_pilot_message`` keyword."""

        self.command.write(level, auto_pilot_message=message)

    async def _schedule_preload(self, preload_ahead: float):
        """Preloads the next design after a delay."""

        expose_macro = self.helpers.macros["expose"]
        assert isinstance(expose_macro, ExposeMacro)

        while True:
            await asyncio.sleep(1)

            if not expose_macro.running:
                continue

            if expose_macro.expose_helper.etr <= preload_ahead:
                break

        if self.is_cancelling() or self.cancelled or self.failed:
            self._auto_pilot_message("Auto-pilot was cancelled. Not preloading design.")
            return

        self._auto_pilot_message("Preloading design from the queue")
        await self._preload_design(now=True)

        # At this point we consider this configuration has been observed.
        if self.helpers.jaeger.configuration:
            self.helpers.jaeger.configuration.observed = True

    async def _preload_design(
        self,
        now: bool = False,
        ahead_time: float | None = None,
    ):
        """Preloads a design.

        If ``now=True`` or the spectrographs are idle, the design is preloaded
        immediately, otherwise waits until ``ahead_time`` seconds remain in the
        exposure. If ``ahead_time`` is ``None``, defaults to the macro
        configuration ``preload_ahead_time`` value.

        """

        self.system_state.update_time_remaining()

        if now is False and self.system_state.exposure_time_remaining > 0:
            if ahead_time is None:
                ahead_time = self.config["preload_ahead_time"]

            assert ahead_time is not None and ahead_time >= 0
            ahead_time = round(ahead_time, 1)

            self._auto_pilot_message(f"Wating {ahead_time} s before preloading design")
            while True:
                self.system_state.update_time_remaining()
                if self.system_state.exposure_time_remaining <= ahead_time:
                    break

                await asyncio.sleep(1)

        # Assume that we are exposing BOSS and account for the readout
        # time that is not included in exposure_time_remaining.
        boss_readout = config["durations"]["boss"][self.observatory]["readout"]
        extra_epoch_delay = self.system_state.exposure_time_remaining + boss_readout
        self._auto_pilot_message(f"Preloading with delay {extra_epoch_delay:.1f} s")

        await self.helpers.jaeger.load_from_queue(
            self.command,
            preload=True,
            extra_epoch_delay=extra_epoch_delay,
        )

    async def _cancel_preload_task(self):
        """Cancels an existing preload task."""

        await cancel_task(self._preload_task)
        self._preload_task = None
