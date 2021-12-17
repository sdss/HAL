#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: apogee.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import enum

from typing import TYPE_CHECKING

from hal import HALCommandType


if TYPE_CHECKING:
    from hal.actor import HALActor


__all__ = ["APOGEEHelper"]


class APOGEEHelper:
    """APOGEE instrument helper."""

    def __init__(self, actor: HALActor):

        self.actor = actor
        self.gang_helper = APOGEEGangHelper(actor)

    async def shutter(self, open=True, command: HALCommandType = None):
        """Opens/closes the shutter."""

        commander = command or self.actor

        position = "open" if open is True else "close"
        shutter_command = await commander.send_command("apogee", f"shutter {position}")

        if shutter_command.status.did_fail:
            if command is not None:
                command.error("Failed to open/close APOGEE shutter.")
            else:
                self.actor.write("e", text="Failed to open/close APOGEE shutter.")
            return False

        return True

    async def expose(
        self,
        exp_time: float,
        exp_type: str = "dark",
        command: HALCommandType | None = None,
    ):
        """Exposes APOGEE."""

        commander = command or self.actor

        expose_command = await commander.send_command(
            "apogee",
            f"expose time={exp_time:.1f} object={exp_type} ''",
        )

        if expose_command.status.did_fail:
            if command is not None:
                command.error("Failed to expose APOGEE.")
            else:
                self.actor.write("e", text="Failed to expose APOGEE.")
            return False

        return True


class APOGEEGangHelper:
    def __init__(self, actor: HALActor):

        self.actor = actor
        self.flag: APOGEEGang = APOGEEGang.UNKNWON

        actor.models["mcp"]["apogeeGang"].register_callback(self._update_flag)

    async def _update_flag(self, value: list):
        """Callback to update the gang connector flag."""

        self.flag = APOGEEGang(int(value[0]))

    def get_position(self):
        """Return the position of the gang connector."""

        return self.flag.name

    def at_podium(self):
        """Return True if the gang connector is on the podium."""

        pos = self.get_position()
        ok = (pos == self.flag.POIDUM) or (pos == self.flag.PODIUM_DENSE)
        return ok

    def at_cartridge(self):
        """Returns True if the gang connector is at the cartridge."""

        return self.get_position() == self.flag.AT_CART


class APOGEEGang(enum.Enum):
    """Flags for the ``mcp.apogeeGang`` keyword."""

    UNKNWON = 0
    DISCONNECTED = 1
    AT_CART = 2
    POIDUM = 4
    PODIUM_DENSE = 12
    PODIUM_SPARSE = 20
    PODIUM_1M = 36
