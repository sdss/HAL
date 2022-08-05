#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: ffs.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import enum

from typing import TYPE_CHECKING

from hal import config

from . import HALHelper


if TYPE_CHECKING:
    from hal.actor import HALCommandType


__all__ = ["FFSHelper"]


class FFSHelper(HALHelper):
    """Command and keeps track of the Flat-Field Screens status."""

    TIMEOUT: float = config["timeouts"]["ffs"]

    name = "ffs"

    def get_values(self):
        """Returns the FFS status flags."""

        values = self.actor.models["mcp"]["ffsStatus"].value
        if len(values) == 0 or all([value is None for value in values]):
            return [FFSStatus.UNKNWON] * 8

        return [FFSStatus(value) for value in values]

    def all_closed(self):
        """Returns `True` if all the petals are closed."""

        return all([x == FFSStatus.CLOSED for x in self.get_values()])

    def all_open(self):
        """Returns `True` if all the petals are open."""

        return all([x == FFSStatus.OPEN for x in self.get_values()])

    async def open(self, command: HALCommandType):
        """Open all the petals."""

        if self.all_open():
            return

        return await self._send_command(command, "mcp", "ffs.open")

    async def close(self, command: HALCommandType):
        """Close all the petals."""

        if self.all_closed():
            return

        return await self._send_command(command, "mcp", "ffs.close")


class FFSStatus(enum.Enum):
    """FFS status flags."""

    UNKNWON = "00"
    CLOSED = "01"
    OPEN = "10"
    INVALID = "11"
