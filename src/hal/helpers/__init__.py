#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from clu import CommandStatus

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
        **kwargs,
    ):
        """Sends a command to a target."""

        cmd = await command.send_command(target, cmd_str, **kwargs)
        if cmd.status.did_fail:
            if cmd.status == CommandStatus.TIMEDOUT:
                raise HALError(f"{target} {cmd_str} timed out.")
            else:
                raise HALError(f"{target} {cmd_str} failed.")

        return cmd


from .apogee import *
from .ffs import *
from .scripts import *
from .tcc import *
