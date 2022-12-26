#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-25
# @Filename: auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from hal import config
from hal.exceptions import MacroError
from hal.macros.macro import Macro


class AutoModeMacro(Macro):
    """A macro that runs one iteration of the auto mode."""

    name = "expose"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = ["load", "goto_field", ("guide", "expose")]
    __CLEANUP__ = ["cleanup"]

    def __init__(self, name: str | None = None):
        super().__init__(name)

        self._load_design: asyncio.Task | None = None

    async def prepare(self):
        """Prepare stage."""

        # TODO: if auto is called while an exposure is in process or a goto is running,
        # here we will decide how much to wait and what stages to skip.

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

        # Acquire but do not guide.
        if "guide" in stages:
            stages.remove("guide")

        if len(stages) == 0:  # For cloned designs.
            self.message("Skipping goto-field.")
            return

        self.message("Running goto-field.")

        goto.reset(self.command, stages)
        if not await goto.run():
            raise MacroError("Goto field failed during auto mode.")

    async def guide(self):
        """Start the guide loop."""

        if not self.helpers.tcc.check_axes_status("Tracking"):
            raise MacroError("Axes must be tracking for guiding.")

        if not self.helpers.ffs.all_open():
            self.command.info("Opening FFS")
            await self.helpers.ffs.open(self.command)

        guider_time = self.config["guider_time"]

        self.command.info("Starting guide loop.")
        await self.helpers.cherno.guide(
            self.command,
            exposure_time=guider_time,
            wait=False,
        )

    async def expose(self):
        """Exposes the camera and schedules next design."""

        n_exposures = self.config["n_exposures"]

        total_time = 900 * n_exposures

        self.message("Starting guide loop.")
        wait_design_load = total_time - 180
        self._load_design = asyncio.create_task(self._preload_design(wait_design_load))

        self.message("Exposing cameras.")
        expose_macro = self.helpers.macros["expose"]
        expose_macro.reset(self.command, count_boss=n_exposures)
        if not await expose_macro.run():
            raise MacroError("Expose failed during auto mode.")

    async def cleanup(self):
        """Cleanup stage."""

        pass

    async def _preload_design(self, delay: float):
        """Preloads the next design after a delay."""

        await asyncio.sleep(delay)
        await self.helpers.jaeger.load_from_queue(self.command, preload=True)
