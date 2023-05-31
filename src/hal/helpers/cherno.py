#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-25
# @Filename: cherno.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
from enum import Flag
from time import time

from typing import TYPE_CHECKING

from clu.legacy.tron import TronKey

from hal.helpers import HALHelper


if TYPE_CHECKING:
    from hal.actor import HALActor, HALCommandType


__all__ = ["ChernoHelper", "GuiderStatus"]


class GuiderStatus(Flag):
    """Maskbits with the guider status."""

    IDLE = 1 << 0
    EXPOSING = 1 << 1
    PROCESSING = 1 << 2
    CORRECTING = 1 << 3
    STOPPING = 1 << 4
    FAILED = 1 << 5
    WAITING = 1 << 6
    UNKNOWN = 1 << 10

    NON_IDLE = EXPOSING | PROCESSING | CORRECTING | STOPPING | WAITING | UNKNOWN


class ChernoHelper(HALHelper):
    """Helper to interact with cherno."""

    name = "cherno"

    def __init__(self, actor: HALActor):
        super().__init__(actor)

        self.status = GuiderStatus.UNKNOWN

        self.model = actor.models["cherno"]
        self.model["guider_status"].register_callback(self._guider_status)

    async def _guider_status(self, key: TronKey):
        """Updates the internal guider status."""

        self.status = GuiderStatus(int(key.value[0], 16))

        if self.status.value == 0:
            self.status = GuiderStatus.UNKNOWN

    def is_guiding(self):
        """Returns `True` if the guider is not idle."""

        return bool(self.status & GuiderStatus.NON_IDLE)

    def guiding_at_rms(
        self,
        rms: float,
        max_age: float = 120,
        allow_not_guiding: bool = False,
    ):
        """Checks that the guider has reached a given RMS."""

        if not self.is_guiding() and allow_not_guiding is False:
            return False

        guide_rms = self.model["guide_rms"]

        if guide_rms and guide_rms.value and guide_rms.value[3]:
            last_seen = guide_rms.last_seen
            age = time() - last_seen
            if age > max_age:
                return False

            return guide_rms.value[3] <= rms
        else:
            return False

    async def wait_for_rms(self, rms: float, max_wait: float | None = None):
        """Blocks until a given RMS is reached."""

        elapsed = 0.0
        while True:
            if self.guiding_at_rms(rms):
                return True
            await asyncio.sleep(5)
            elapsed += 5
            if max_wait and elapsed > max_wait:
                raise asyncio.TimeoutError()

    async def acquire(
        self,
        command: HALCommandType,
        exposure_time: float = 15,
        target_rms: float | None = None,
        wait: bool | None = None,
        max_iterations: int | None = None,
    ):
        """Runs the acquisition command.

        Parameters
        ----------
        command
            The command to use to send the acquisition command.
        exposure_time
            The exposure time to use.
        target_rms
            The RMS to be reached by the acquisition command. If not specified,
            acquisition will be run in continuous mode.
        wait
            Whether to wait for the acquisition to be complete. If `None`, it will
            block only if ``target_rms`` has been defined.
        max_iterations
            Maximum number of iterations before failing.

        """

        block = True if (target_rms and wait is None) or wait is True else False

        command_str = "acquire -c" if target_rms is None else f"acquire -r {target_rms}"
        command_str += f" -t {exposure_time}"

        if max_iterations:
            command_str += f" -x {max_iterations}"

        if block:
            await self._send_command(command, "cherno", command_str)
        else:
            asyncio.create_task(self._send_command(command, "cherno", command_str))

        return

    async def guide(
        self,
        command: HALCommandType,
        exposure_time: float = 15,
        wait: bool = False,
    ):
        """Start the guide loop."""

        coro = self._send_command(command, "cherno", f"guide -t {exposure_time}")

        if wait:
            await coro
        else:
            asyncio.shield(asyncio.create_task(coro))

    async def stop_guiding(self, command: HALCommandType):
        """Stops the guide loop."""

        await self._send_command(command, "cherno", "stop")
