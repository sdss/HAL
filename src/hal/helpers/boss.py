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

from hal import config
from hal.exceptions import HALError

from . import HALHelper


if TYPE_CHECKING:
    from hal.actor import HALActor, HALCommandType


__all__ = ["BOSSHelper"]


class BOSSHelper(HALHelper):
    """Control for BOSS spectrograph."""

    __readout_pending: bool = False
    __readout_task: asyncio.Task | None = None

    name = "boss"

    def __init__(self, actor: HALActor):
        super().__init__(actor)

    @property
    def readout_pending(self):
        """True if an exposure readout is pending."""

        return (
            self.__readout_pending
            and self.__readout_task
            and not self.__readout_task.done()
        )

    def clear_readout(self):
        """Clears any pending readouts."""

        self.__readout_pending = False

    def get_exposure_state(self):
        """Returns the exposure state."""

        if self.actor.observatory == "APO":
            exposure_state = self.actor.models["boss"]["exposureState"]

            if exposure_state is None or None in exposure_state.value:
                raise ValueError("Unknown BOSS exposure state.")

            return exposure_state.value[0].lower()

        else:
            exposure_state = self.actor.models["yao"]["sp2_status_names"]

            if exposure_state is None or None in exposure_state.value:
                raise ValueError("Unknown BOSS exposure state.")

            return exposure_state

    def is_exposing(self):
        """Returns `True` if the BOSS spectrograph is currently exposing."""

        state = self.get_exposure_state()

        if self.actor.observatory == "APO":
            if state in ["idle", "aborted"]:
                return False
        else:
            if "IDLE" in state.value and "READOUT_PENDING" not in state.value:
                return False

        return True

    def is_reading(self):
        """Returns `True` if the camera is reading."""

        state = self.get_exposure_state()

        if self.actor.observatory == "APO":
            if state in ["reading", "prereading"]:
                return True
        else:
            if "READING" in state.value or "READOUT_PENDING" not in state.value:
                return True

        return False

    async def expose(
        self,
        command: HALCommandType,
        exp_time: float = 0.0,
        exp_type: str = "science",
        readout: bool = True,
        read_async: bool = False,
    ):
        """Exposes BOSS. If ``readout=False``, does not read the exposure."""

        if self.readout_pending is not False:
            raise HALError(
                "Cannot expose. The camera is exposing or a readout is pending."
            )

        if self.actor.observatory == "APO":
            await self._expose_boss_icc(
                command,
                exp_time=exp_time,
                exp_type=exp_type,
                readout=readout,
                read_async=read_async,
            )
        else:
            await self._expose_yao(
                command,
                exp_time=exp_time,
                exp_type=exp_type,
                readout=readout,
                read_async=read_async,
            )

    async def _expose_boss_icc(
        self,
        command: HALCommandType,
        exp_time: float = 0.0,
        exp_type: str = "science",
        readout: bool = True,
        read_async: bool = False,
    ):
        """Expose using ``bossICC``."""

        timeout = (
            exp_time
            + config["timeouts"]["expose"]
            + config["timeouts"]["boss_icc_flushing"]
        )

        command_parts = [f"exposure {exp_type}"]

        if exp_type != "bias":
            command_parts.append(f"itime={round(exp_time, 1)}")

        if readout is False or read_async is True:
            command_parts.append("noreadout")
        else:
            timeout += config["timeouts"]["boss_icc_readout"]

        command_string = " ".join(command_parts)

        await self._send_command(command, "boss", command_string, time_limit=timeout)

        self.__readout_pending = True

        if readout is True and read_async is True:
            # We use a _send_command because readout cannot await on itself.
            self.__readout_task = asyncio.create_task(
                self._send_command(
                    command,
                    "boss",
                    "exposure readout",
                    time_limit=25.0 + config["timeouts"]["boss_icc_readout"],
                )
            )
            return

        self.__readout_pending = not readout

    async def _expose_yao(
        self,
        command: HALCommandType,
        exp_time: float = 0.0,
        exp_type: str = "science",
        readout: bool = True,
        read_async: bool = False,
    ):
        """Expose using ``yao``."""

        timeout = exp_time + config["timeouts"]["expose"]

        if exp_type == "science":
            exp_type = "object"

        command_parts = [f"expose --{exp_type}"]

        if exp_type != "bias":
            command_parts.append(f"{round(exp_time, 1)}")

        if readout is False or read_async is True:
            command_parts.append("--no-readout")
        else:
            timeout += config["timeouts"]["boss_yao_readout"]

        command_string = " ".join(command_parts)

        await self._send_command(command, "yao", command_string, time_limit=timeout)

        self.__readout_pending = True

        if readout is True and read_async is True:
            # We use a _send_command because readout cannot await on itself.
            self.__readout_task = asyncio.create_task(
                self._send_command(
                    command,
                    "yao",
                    "read",
                    time_limit=25.0 + config["timeouts"]["boss_yao_readout"],
                )
            )
            return

        self.__readout_pending = not readout

    async def readout(self, command: HALCommandType):
        """Reads a pending readout."""

        if self.readout_pending is False:
            raise HALError("No pending readout.")

        command.debug("Reading pending BOSS exposure.")

        if self.readout_pending and self.__readout_task:
            await self.__readout_task

        else:
            await self._send_command(
                command,
                "boss",
                "exposure readout",
                time_limit=25.0 + config["timeouts"]["boss_readout"],
            )

        self.clear_readout()
