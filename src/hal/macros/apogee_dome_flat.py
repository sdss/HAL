#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: apogee_dome_flat.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from hal.exceptions import MacroError

from .base import Macro


__all__ = ["APOGEEDomeFlatMacro"]


class APOGEEDomeFlatMacro(Macro):
    """Take an APOGEE dome flat after an exposure."""

    name = "apogee_dome_flat"

    __STAGES__ = ["gang_at_cart", ("ffs", "open_shutter"), "expose", "cleanup"]
    __CLEANUP__ = ["cleanup"]

    async def gang_at_cart(self):
        """Checks that the gang connected is at the cart."""

        assert self.command.actor

        if not self.command.actor.helpers.apogee.gang_helper.at_cartridge():
            raise MacroError("The APOGEE gang connector is not at the cart.")

        return True

    async def ffs(self):
        """Check the FFS status and closes it."""

        assert self.command.actor

        result = await self.command.actor.helpers.ffs.close(self.command)
        if result is False:
            raise MacroError("Failed closing FFS.")

    async def open_shutter(self):
        """Opens the APOGEE cold shutter."""

        assert self.command.actor

        apogee = self.command.actor.helpers.apogee

        if not await apogee.shutter(True, command=self.command):
            raise MacroError("Failed opening APOGEE shutter.")

    async def expose(self):
        """Takes the dome flat. Turns on the FFS after the fourth read."""

        assert self.command.actor

        apogee = self.command.actor.helpers.apogee

        self.command.actor.models["apogee"]["utrReadState"].register_callback(
            self._flash_lamps
        )

        self.command.info("Taking APOGEE dome flat.")
        await apogee.expose(50, exp_type="DomeFlat", command=self.command)

        return True

    async def _flash_lamps(self, value: list):
        """Flases the FF lamps."""

        if len(value) == 0:
            return

        n_read = int(value[2])
        if n_read == 3:
            time_to_flash = 4.0

            self.command.info(text="Calling ff_lamp.on")

            self.command.send_command("mcp", "ff.on")  # Do not wait for the command.
            await asyncio.sleep(time_to_flash)

            lamp_off = await self.command.send_command("mcp", "ff.off")
            if lamp_off.status.did_fail:
                raise MacroError("Failed flashing lamps.")

        return

    async def cleanup(self):
        """Closes the shutter and does cleanup."""

        assert self.command.actor

        apogee = self.command.actor.helpers.apogee

        self.command.actor.models["apogee"]["utrReadState"].remove_callback(
            self._flash_lamps
        )

        if not await apogee.shutter(False, command=self.command):
            self.command.error("Failed closing APOGEE shutter.")
