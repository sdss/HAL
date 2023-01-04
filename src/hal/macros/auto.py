#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-25
# @Filename: auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
from contextlib import suppress

from hal import config
from hal.exceptions import MacroError
from hal.macros.macro import Macro


class AutoModeMacro(Macro):
    """A macro that runs one iteration of the auto mode."""

    name = "auto"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = ["load", "goto_field", "expose"]
    __CLEANUP__ = ["cleanup"]

    def __init__(self, name: str | None = None):
        super().__init__(name)

        self._preload_design_task: asyncio.Task | None = None

    async def prepare(self):
        """Prepare stage."""

        pass

    def message(self, message: str, level: str = "i"):
        """Emits a message using the ``auto_mode_message`` keyword."""

        self.command.write(level, auto_mode_message=message)

    async def load(self):
        """Load a (pre-)loaded design."""

        jaeger = self.helpers.jaeger

        if jaeger.configuration and jaeger.configuration.observed is False:
            self.message("Found unobserved design loaded.")

        elif jaeger.preloaded is None:
            self.message("No preloaded designs found. Loading new queue design.")

            if not await jaeger.load_from_queue(self.command):
                raise MacroError("Failed loading design.")

        else:
            self.message("Loading preloaded design.")
            await jaeger.from_preloaded(self.command)

        # Make sure everything all keywords have been emitted and database queries run.
        await asyncio.sleep(1)

        if not jaeger.configuration:
            raise MacroError("Failed loading design. No active configuration.")

        c_id = jaeger.configuration.configuration_id
        d_id = jaeger.configuration.design_id
        self.message(f"Processign configuration {c_id} ({d_id}).")

    async def goto_field(self):
        """Runs the goto-field macro with the appropriate stages."""

        goto = self.helpers.macros["goto_field"]

        if goto.running:
            self.command.warning("goto-field is running. Waiting for it to complete.")
            result = await goto.wait_until_complete()
            if not result:
                raise MacroError("Background goto-field failed. Cancelling auto mode.")
            # Skip goto-field since it's already been done.
            return

        configuration = self.helpers.jaeger.configuration

        if configuration is None:
            return MacroError("No configuration loaded.")
        elif configuration.cloned is True:
            stages = config["macros"]["goto_field"]["cloned_stages"]
        elif configuration.new_field is False:
            stages = config["macros"]["goto_field"]["repeat_field_stages"]
        elif configuration.is_rm_field is True:
            stages = config["macros"]["goto_field"]["rm_field_stages"]
        else:
            stages = config["macros"]["goto_field"]["new_field_stages"]

        if len(stages) == 0:  # For cloned designs.
            self.message("Skipping goto-field.")
            return

        self.message("Running goto-field.")

        goto.reset(self.command, stages)
        if not await goto.run():
            raise MacroError("Goto field failed during auto mode.")

    async def expose(self):
        """Exposes the camera and schedules next design."""

        expose_macro = self.helpers.macros["expose"]

        if expose_macro.running:
            self.command.warning("expose is running. Waiting for it to complete.")
            result = await expose_macro.wait_until_complete()
            if not result:
                raise MacroError("Background expose failed. Cancelling auto mode.")
            # Skip expose since it's already been done.
            # TODO: this will not load a new design.
            return

        # Make sure guiding is good enough to start exposing.
        if not self.helpers.cherno.is_guiding():
            raise MacroError("Guider is not running. Cannot expose.")

        target_rms = self.config["target_rms"]
        if not self.helpers.cherno.guiding_at_rms(target_rms):
            self.command.info("RMS not reched yet. Waiting for guider to converge.")
            try:
                await self.helpers.cherno.wait_for_rms(target_rms, max_wait=180)
            except asyncio.TimeoutError:
                raise MacroError("Timed out waiting for guider to converge.")

        # Calculate expose time and schedule preloading a design.
        count = self.config["count"]
        exptime = config["macros"]["expose"]["fallback"]["exptime"]
        flushing = config["durations"]["boss"][self.actor.observatory]["flushing"]
        readout = config["durations"]["boss"][self.actor.observatory]["readout"]
        total_time = (exptime + flushing + readout) * count - readout

        wait_design_load = int(total_time - 180)
        self.command.debug(f"Scheduling next design preload in {wait_design_load} s.")
        await self._preload_design(wait_design_load)

        self.message("Exposing cameras.")
        expose_macro.reset(self.command, count_boss=count)
        if not await expose_macro.run():
            raise MacroError("Expose failed during auto mode.")

    async def cleanup(self):
        """Cleanup stage."""

        if self.cancelled:
            await self._cancel_preload_task()

    async def _preload_design(self, delay: float):
        """Preloads the next design after a delay."""

        async def _preload_executor(delay: float):
            await asyncio.sleep(delay)
            await self.helpers.jaeger.load_from_queue(self.command, preload=True)

        await self._cancel_preload_task()
        self._preload_design_task = asyncio.create_task(_preload_executor(delay))

    async def _cancel_preload_task(self):
        """Cancels an existing preload task."""

        if self._preload_design_task and not self._preload_design_task.done():
            self._preload_design_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._preload_design_task

        self._preload_design_task = None