#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: boss.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from hal import HALCommandType, config
from hal.exceptions import HALError

from . import HALHelper


if TYPE_CHECKING:
    from hal.actor import HALActor


__all__ = ["BOSSHelper"]


class BOSSHelper(HALHelper):
    """Control for BOSS spectrograph."""

    __readout_pending: bool = False

    def __init__(self, actor: HALActor):
        super().__init__(actor)

    @property
    def readout_pending(self):
        """True if an exposure readout is pending."""

        return self.__readout_pending

    async def expose(
        self,
        command: HALCommandType,
        exp_time: float = 0.0,
        exp_type: str = "object",
        readout: bool = True,
    ):
        """Exposes BOSS. If ``readout=False``, does not read the exposure."""

        if self.readout_pending is True:
            raise HALError(
                "Cannot expose. The camera is exposing or a readout is pending."
            )

        command_parts = [f"exposure {exp_type}"]

        if exp_type != "bias":
            command_parts.append(f"itime={round(exp_time, 1)}")

        if readout is False:
            command_parts.append("noreadout")

        command_string = " ".join(command_parts)

        timeout = (
            exp_time
            + config["timeouts"]["expose"]
            + config["timeouts"]["boss_flushing"]
        )

        if readout is True:
            timeout += config["timeouts"]["boss_readout"]

        command.debug(f"Taking BOSS {exp_type} exposure.")

        self.__readout_pending = True
        await self._send_command(command, "boss", command_string, time_limit=timeout)

        self.__readout_pending = not readout

    async def readout(self, command: HALCommandType):
        """Reads a pending readout."""

        if not self.readout_pending:
            raise HALError("No pending readout.")

        command.debug("Reading pending BOSS exposure.")

        await self._send_command(
            command,
            "boss",
            "exposure readout",
            time_limit=25.0 + config["timeouts"]["boss_readout"],
        )
