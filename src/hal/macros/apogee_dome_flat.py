#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: apogee_dome_flat.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from clu.legacy.tron import TronKey

from hal.exceptions import MacroError

from .base import Macro


__all__ = ["APOGEEDomeFlatMacro"]


class APOGEEDomeFlatMacro(Macro):
    """Take an APOGEE dome flat after an exposure."""

    name = "apogee_dome_flat"

    __STAGES__ = ["gang_at_cart", ("ffs", "open_shutter"), "expose"]
    __CLEANUP__ = ["cleanup"]

    __ffs_initial_state: str | None = None

    async def gang_at_cart(self):
        """Checks that the gang connected is at the cart."""

        assert self.command.actor

        if not self.command.actor.helpers.apogee.gang_helper.at_cartridge():
            raise MacroError("The APOGEE gang connector is not at the cart.")

        return True

    async def ffs(self):
        """Check the FFS status and closes it."""

        if self.command.actor.helpers.ffs.all_closed():
            self.command.debug("FFS already closed.")
            self.__ffs_initial_state = "closed"
            return
        elif self.command.actor.helpers.ffs.all_open():
            self.__ffs_initial_state = "open"
        else:
            raise MacroError("Cannot determine state of FFS.")

        self.command.info("Closing FFS.")

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

    async def _flash_lamps(self, key: TronKey):
        """Flases the FF lamps."""

        if len(key.value) == 0:
            return

        state = key.value[1]
        n_read = int(key.value[2])
        if n_read == 3 and state == "Reading":
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

        try:
            self.command.actor.models["apogee"]["utrReadState"].remove_callback(
                self._flash_lamps
            )
        except AssertionError:
            pass

        if not await apogee.shutter(False, command=self.command):
            self.command.error("Failed closing APOGEE shutter.")

        if self.__ffs_initial_state == "open":
            self.command.info("Reopening FFS.")
            await self.command.actor.helpers.ffs.open(self.command)
        else:
            self.command.info("Keeping FFS closed.")
