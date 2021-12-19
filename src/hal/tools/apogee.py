#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: apogee.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import enum

from clu import CommandStatus

from hal import config
from hal.actor import HALActor, HALCommandType
from hal.exceptions import HALError


__all__ = ["APOGEEHelper"]


class APOGEEHelper:
    """APOGEE instrument helper."""

    def __init__(self, actor: HALActor):

        self.actor = actor
        self.gang_helper = APOGEEGangHelper(actor)

    async def shutter(self, command: HALCommandType, open=True):
        """Opens/closes the shutter."""

        position = "open" if open is True else "close"

        shutter_command = await self._send_command(
            command,
            f"shutter {position}",
            time_limit=config["timeouts"]["apogee_shutter"],
        )

        return shutter_command

    async def expose(
        self,
        command: HALCommandType,
        exp_time: float,
        exp_type: str = "dark",
    ):
        """Exposes APOGEE."""

        expose_command = await self._send_command(
            command,
            f"expose time={exp_time:.1f} object={exp_type}",
            time_limit=exp_time + config['timeouts']['expose']
        )

        return expose_command

    async def _send_command(self, command: HALCommandType, cmd_str: str, **kwargs):
        """Sends a command to the MCP."""

        move_cmd = await command.send_command("apogee", cmd_str, **kwargs)
        if move_cmd.status.did_fail:
            if move_cmd.status == CommandStatus.TIMEDOUT:
                raise HALError(f"apogee {cmd_str} timed out.")
            else:
                raise HALError(f"apogee {cmd_str} failed.")

        return move_cmd


class APOGEEGangHelper:
    def __init__(self, actor: HALActor):

        self.actor = actor
        self.flag: APOGEEGang = APOGEEGang.UNKNWON

        actor.models["mcp"]["apogeeGang"].register_callback(self._update_flag)

    async def _update_flag(self, value: list):
        """Callback to update the gang connector flag."""

        value = value or [0]
        self.flag = APOGEEGang(int(value[0]))

    def get_position(self):
        """Return the position of the gang connector."""

        return self.flag

    def at_podium(self):
        """Return True if the gang connector is on the podium."""

        pos = self.get_position()
        ok = pos & APOGEEGang.AT_PODIUM
        return ok

    def at_cartridge(self):
        """Returns True if the gang connector is at the cartridge."""

        ok = self.get_position() == self.flag.AT_CART

        return ok


class APOGEEGang(enum.Flag):
    """Flags for the ``mcp.apogeeGang`` keyword."""

    # Temporary, the situation with the gang connector switches is not clear.

    UNKNWON = 0
    AT_PODIUM = 4
    AT_CART = 17
    DENSE_NO_FPI = 12
    DENSE_FPI = 28
    PODIUM_FPI = 20

    # DISCONNECTED = 1
    # AT_CART = 2
    # POIDUM = 4
    # PODIUM_DENSE = 12
    # PODIUM_SPARSE = 20
    # PODIUM_1M = 36
