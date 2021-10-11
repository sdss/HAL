#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from .base import Macro, StageStatus


__all__ = ["GotoFieldMacro"]


class GotoFieldMacro(Macro):
    """Go to field macro."""

    name = "goto_field"
    __STAGES__ = [("slew", "reconfigure"), "calibrations", "acquire", "guide"]

    async def slew(self):
        self.command.info("starting slew")
        await asyncio.sleep(5)
        self.command.info("done slew")

    async def reconfigure(self):
        self.command.info("starting reconfigure")
        await asyncio.sleep(4)
        self.command.info("done reconfigure")

    async def calibrations(self):
        try:
            self.command.info("starting calibrations")
            await asyncio.sleep(1)
            self.command.info("done calibrations")
        except asyncio.CancelledError:
            self.command.info("cancelling with cleanup.")
            self.set_stage_status("calibrations", StageStatus.CANCELLING)
            await asyncio.sleep(3)
            self.command.info("cleanup done")

    async def acquire(self):
        self.command.info("starting acquire")
        await asyncio.sleep(2)
        self.command.info("done acquire")

    async def guide(self):
        self.command.info("starting guide")
        await asyncio.sleep(3)
        self.command.info("done guide")
