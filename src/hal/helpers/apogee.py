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

    async def shutter(
        self,
        command: HALCommandType,
        open: bool = True,
        shutter: str = "apogee",
        force: bool = False,
    ):
        """Opens/closes the shutter.

        Parameters
        ----------
        command
            The command instance to use to command the shutter.
        open
            If `True`, opens the shutter, otherwise closes it.
        shutter
            The shutter to query. Can be ``apogee`` or ``fpi``.
        force
            If `True`, sends the command to the shutter even if it reports to
            already be in that position.

        Returns
        -------
        shutter_command
            The command sent to the shutter after been awaited for completion or
            `None` if the shutter is already at that position.

        """

        position = "open" if open is True else "close"

        if force is False:
            current_position = self.get_shutter_position(shutter)
            if current_position is None and current_position == open:
                return None

        if shutter == "apogee":
            shutter_command = await self._send_command(
                command,
                "apogee",
                f"shutter {position}",
                time_limit=config["timeouts"]["apogee_shutter"],
            )

        elif shutter == "fpi":
            shutter_command = await self._send_command(
                command,
                "apogeefpi",
                position,
                time_limit=config["timeouts"]["apogee_shutter"],
            )

        else:
            raise ValueError(f"Invalid shutter {shutter}.")

        return shutter_command

    def get_shutter_position(self, shutter: str = "apogee") -> bool | None:
        """Returns the shutter status.

        Parameters
        ----------
        shutter
            The shutter to query. Can be ``apogee`` or ``fpi``.

        Returns
        -------
        shutter_status
            `True` if the shutter is open, `False` if closed, `None` if unknown.

        """

        shutter = shutter.lower()

        if shutter == "apogee":
            limit_switch = self.actor.models["apogee"]["shutterLimitSwitch"]
            if limit_switch is None or None in limit_switch.value:
                return None
            if limit_switch.value[0] is False and limit_switch.value[1] is True:
                return False
            elif limit_switch.value[1] is False and limit_switch.value[0] is True:
                return True
            else:
                return None

        elif shutter == "fpi":
            shutter_position = self.actor.models["apogeefpi"]["shutter_position"]
            if (
                shutter_position is None
                or shutter_position.value[0] is None
                or shutter_position.value[0] == "?"
            ):
                return None
            elif shutter_position.value[0].lower() == "closed":
                return False
            elif shutter_position.value[0].lower() == "open":
                return True
            else:
                return None

        else:
            raise ValueError(f"Invalid shutter {shutter}.")

    def get_dither_position(self) -> str | None:
        """Returns the dither position or `None` if unknown."""

        position = self.actor.models["apogee"]["ditherPosition"]
        if position is None or None in position.value:
            return None

        return position.value[1]

    def is_exposing(self):
        """Returns `True` if APOGEE is exposing or stopping."""

        exposure_state = self.actor.models["apogee"]["exposureState"]

        if exposure_state.value is None or None in exposure_state.value:
            raise ValueError("Unknown APOGEE exposure state.")

        state = exposure_state.value[0].lower()
        if state in ["exposing", "stopping"]:
            return True
        else:
            return False

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
