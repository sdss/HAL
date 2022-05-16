#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: boss.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

from hal import HALCommandType, config
from hal.exceptions import HALError

from . import HALHelper


if TYPE_CHECKING:
    from hal.actor import HALActor


__all__ = ["BOSSHelper"]


class BOSSHelper(HALHelper):
    """Control for BOSS spectrograph."""

    __readout_task: asyncio.Task | None = None

    name = "boss"

    def __init__(self, actor: HALActor):
        super().__init__(actor)

    @property
    def readout_pending(self):
        """True if an exposure readout is pending."""

        return self.__readout_task is not None and not self.__readout_task.done()

    def is_exposing(self):
        """Returns `True` if the BOSS spectrograph is currently exposing."""

        exposure_state = self.actor.models["boss"]["exposureState"]

        if exposure_state is None or None in exposure_state.value:
            raise ValueError("Unknown BOSS exposure state.")

        state = exposure_state.value[0].lower()
        if state in ["idle", "aborted"]:
            return False
        else:
            return True

    async def expose(
        self,
        command: HALCommandType,
        exp_time: float = 0.0,
        exp_type: str = "science",
        readout: bool = True,
        read_async: bool = False,
    ):
        """Exposes BOSS. If ``readout=False``, does not read the exposure."""

        if self.is_exposing():
            raise HALError("BOSS is already exposing.")

        if self.readout_pending is True:
            raise HALError("Cannot expose BOSS. A readout is pending.")

        timeout = (
            exp_time
            + config["timeouts"]["expose"]
            + config["timeouts"]["boss_flushing"]
        )

        command_parts = [f"exposure {exp_type}"]

        if exp_type != "bias":
            command_parts.append(f"itime={round(exp_time, 1)}")

        if readout is False or read_async is True:
            command_parts.append("noreadout")
        else:
            timeout += config["timeouts"]["boss_readout"]

        command_string = " ".join(command_parts)

        await self._send_command(command, "boss", command_string, time_limit=timeout)

        if readout is True and read_async is True:
            # We use a _send_command because readout cannot await on itself.
            self.__readout_task = asyncio.create_task(
                self._send_command(
                    command,
                    "boss",
                    "exposure readout",
                    time_limit=25.0 + config["timeouts"]["boss_readout"],
                )
            )
            return

    async def readout(self, command: HALCommandType):
        """Reads a pending readout."""

        command.debug("Reading pending BOSS exposure.")

        if not self.readout_pending or self.__readout_task is None:
            self.__readout_task = asyncio.create_task(
                self._send_command(
                    command,
                    "boss",
                    "exposure readout",
                    time_limit=25.0 + config["timeouts"]["boss_readout"],
                )
            )

        await self.__readout_task
        self.__readout_task = None
