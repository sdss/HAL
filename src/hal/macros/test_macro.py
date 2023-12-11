#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-12-11
# @Filename: test_macro.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from hal.macros import Macro


__all__ = ["TestMacro"]


class TestMacro(Macro):
    """A macro just for testing."""

    name = "test"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = [("stage1", "stage2"), "stage3"]
    __CLEANUP__ = ["cleanup"]

    async def prepare(self):
        """Prepares the macro."""

        self.command.info("Preparing macro.")
        await asyncio.sleep(1)

        return True

    async def stage1(self):
        """Stage 1."""

        self.command.info("Running stage 1.")
        await asyncio.sleep(1)

        return True

    async def stage2(self):
        """Stage 2."""

        self.command.info("Running stage 2.")
        await asyncio.sleep(2)

        return True

    async def stage3(self):
        """Stage 3."""

        self.command.info("Running stage 3.")
        await asyncio.sleep(0.5)

        return True

    async def cleanup(self):
        """Runs the cleanup."""

        await asyncio.sleep(0.5)

        return True
