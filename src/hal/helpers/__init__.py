#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING, cast

from clu import Command, CommandStatus

from hal import config
from hal.exceptions import HALError


if TYPE_CHECKING:
    from hal.actor import HALActor, HALCommandType


class HALHelper:
    """A helper class to control an actor or piece of hardware."""

    name: str | None = None

    def __init__(self, actor: HALActor):
        self.actor = actor

    async def _send_command(
        self,
        command: HALCommandType,
        target: str,
        cmd_str: str,
        raise_on_fail: bool = True,
        **kwargs,
    ):
        """Sends a command to a target."""

        bypasses = self.actor.helpers.bypasses

        # If the helper is bypassed, just returns a fake done command.
        if (self.name and self.name in bypasses) or ("all" in bypasses):
            command.warning(f"Bypassing command '{target} {cmd_str}'")
            cmd = Command()
            cmd.set_status(CommandStatus.DONE)
            return cmd

        if self.actor.tron is None or self.actor.tron.connected() is False:
            raise HALError("Not connected to Tron. Cannot send commands.")

        cmd = await command.send_command(target, cmd_str, **kwargs)
        if raise_on_fail and cmd.status.did_fail:
            if cmd.status == CommandStatus.TIMEDOUT:
                raise HALError(f"Command '{target} {cmd_str}' timed out.")
            else:
                raise HALError(f"Command '{target} {cmd_str}' failed.")

        return cast(Command, cmd)


class SpectrographHelper(HALHelper):
    """A helper class to control a spectrograph."""

    def __init__(self, actor: HALActor):
        super().__init__(actor)

        self._exposure_time_remaining_timer: asyncio.Task | None = None
        self._exposure_time_remaining: float = 0

    def is_exposing(self) -> bool:
        """Returns ``True`` if the spectrograph is exposing."""

        raise NotImplementedError()

    @property
    def exposure_time_remaining(self) -> float:
        """Returns the remaining exposure time in seconds."""

        if not self.is_exposing() or self._exposure_time_remaining <= 0.0:
            return 0.0

        return self._exposure_time_remaining

    async def _timer(self):
        """Updates the exposure time remaining."""

        try:
            while self._exposure_time_remaining > 0.0:
                await asyncio.sleep(0.1)
                self._exposure_time_remaining -= 0.1
        except asyncio.CancelledError:
            pass
        finally:
            self._exposure_time_remaining_timer = None
            self._exposure_time_remaining = 0.0


def get_default_exposure_time(observatory: str, design_mode: str | None = None):
    """Returns the default exposure time for the current design mode."""

    if design_mode is not None and "bright" in design_mode:
        return config["macros"]["expose"]["fallback"]["exptime"]["bright_design_mode"][observatory.upper()]  # fmt: skip  # noqa
    return config["macros"]["expose"]["fallback"]["exptime"]["default"]


from .apogee import *
from .boss import *
from .cherno import *
from .ffs import *
from .jaeger import *
from .lamps import *
from .overhead import *
from .scripts import *
from .tcc import *
