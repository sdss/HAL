#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: ffs.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import enum

from clu import CommandStatus

from hal import config
from hal.actor import HALActor, HALCommandType
from hal.exceptions import HALError


__all__ = ["FFSHelper"]


class FFSHelper:
    """Command and keeps track of the Flat-Field Screens status."""

    TIMEOUT: float = config["timeouts"]["ffs"]

    def __init__(self, actor: HALActor):

        self.actor = actor

    def get_values(self):
        """Returns the FFS status flags."""

        values = self.actor.models["mcp"]["ffsStatus"].value
        if len(values) == 0:
            return [FFSStatus.UNKNWON] * 8

        return [FFSStatus(value) for value in values]

    def all_closed(self):
        """Returns `True` fi all the petals are closed."""

        return all([x == FFSStatus.CLOSED for x in self.get_values()])

    def all_open(self):
        """Returns `True` fi all the petals are open."""

        return all([x == FFSStatus.OPEN for x in self.get_values()])

    async def open(self, command: HALCommandType):
        """Open all the petals."""

        if self.all_open():
            return

        return await self._send_command(command, "ffs.open")

    async def close(self, command: HALCommandType):
        """Close all the petals."""

        if self.all_closed():
            return

        return await self._send_command(command, "ffs.close")

    async def _send_command(self, command: HALCommandType, cmd_str: str):
        """Sends a command to the MCP."""

        move_cmd = await command.send_command("mcp", cmd_str, time_limit=self.TIMEOUT)
        if move_cmd.status.did_fail:
            if move_cmd.status == CommandStatus.TIMEDOUT:
                raise HALError(f"mcp {cmd_str} timed out.")
            else:
                raise HALError(f"mcp {cmd_str} failed.")

        return move_cmd


class FFSStatus(enum.Enum):
    """FFS status flags."""

    UNKNWON = "00"
    CLOSED = "01"
    OPEN = "10"
    INVALID = "11"
