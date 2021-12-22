#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: apogee.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import enum

from hal import config
from hal.actor import HALActor, HALCommandType

from . import HALHelper


__all__ = ["APOGEEHelper"]


class APOGEEHelper(HALHelper):
    """APOGEE instrument helper."""

    def __init__(self, actor: HALActor):

        super().__init__(actor)

        self.gang_helper = APOGEEGangHelper(actor)

    async def shutter(self, command: HALCommandType, open=True):
        """Opens/closes the shutter."""

        position = "open" if open is True else "close"

        shutter_command = await self._send_command(
            command,
            "apogee",
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
            "apogee",
            f"expose time={exp_time:.1f} object={exp_type}",
            time_limit=exp_time + config["timeouts"]["expose"],
        )

        return expose_command


class APOGEEGangHelper:
    """Helper for the APOGEE gang connector."""

    def __init__(self, actor: HALActor):

        self.actor = actor
        self.flag: APOGEEGang = APOGEEGang.UNKNWON

        actor.models["mcp"]["apogeeGang"].register_callback(self._update_flag)

    async def _update_flag(self, value: list):
        """Callback to update the gang connector flag."""

        value = value or [0]
        print(value)
        self.flag = APOGEEGang(int(value[0]))

    def get_position(self):
        """Return the position of the gang connector."""

        return self.flag

    def at_podium(self):
        """Return True if the gang connector is on the podium."""

        ok = (self.get_position() & APOGEEGang.AT_PODIUM) > 0
        return ok

    def at_cartridge(self):
        """Returns True if the gang connector is at the cartridge."""

        pos = self.get_position()
        ok = (pos == APOGEEGang.DISCONNECTED_FPI) or (pos == APOGEEGang.AT_FPS_FPI)
        return ok


class APOGEEGang(enum.Flag):
    """Flags for the ``mcp.apogeeGang`` keyword."""

    UNKNWON = 0
    DISCONNECTED = 1
    AT_CART = 2
    AT_PODIUM = 4
    PODIUM_DENSE = 12
    DISCONNECTED_FPI = 17
    AT_FPS_FPI = 18
    AT_PODIUM_SPARSE = 20
    AT_PODIUM_DENSE_FPI = 28
    AT_PODIUM_ONEM = 36
    AT_PODIUM_ONEM_FPI = 52
