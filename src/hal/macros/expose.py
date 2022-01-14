#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


from __future__ import annotations

import asyncio

from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["ExposeMacro"]


class ExposeMacro(Macro):
    """Takes a science exposure with APOGEE and/or BOSS."""

    name = "expose"

    __STAGES__ = ["prepare", "expose_boss", "expose_apogee"]
    __CLEANUP__ = ["cleanup"]

    async def prepare(self):
        """Prepare for exposures and run checks."""

        do_apogee = "expose_apogee" in self.stages
        do_boss = "expose_boss" in self.stages

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

    async def expose_boss(self):
        """Exposes BOSS."""

        pass

    async def expose_apogee(self):
        """Exposes APOGEE."""

        pass

    async def cleanup(self):
        """Finish the expose macro."""

        pass
