#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from clu import CluError, CommandStatus

from hal.exceptions import HALError


if TYPE_CHECKING:
    from hal.actor import HALActor, HALCommandType


class HALHelper:
    """A helper class to control an actor or piece of hardware."""

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

        if self.actor.tron is None or self.actor.tron.connected() is False:
            raise HALError("Not connected to Tron. Cannot send commands.")

        cmd = await command.send_command(target, cmd_str, **kwargs)
        if raise_on_fail and cmd.status.did_fail:
            if cmd.status == CommandStatus.TIMEDOUT:
                raise HALError(f"{target} {cmd_str} timed out.")
            else:
                raise HALError(f"{target} {cmd_str} failed.")

        return cmd


from .apogee import *
from .boss import *
from .ffs import *
from .lamps import *
from .scripts import *
from .tcc import *
