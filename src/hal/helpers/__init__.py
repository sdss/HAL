#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from clu import Command, CommandStatus

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


from .apogee import *
from .boss import *
from .cherno import *
from .ffs import *
from .jaeger import *
from .lamps import *
from .overhead import *
from .scripts import *
from .tcc import *
