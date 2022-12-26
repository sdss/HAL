#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-26
# @Filename: auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from . import hal_command_parser


if TYPE_CHECKING:

    from .. import HALCommandType


__all__ = ["auto"]


@hal_command_parser.command(name="auto")
async def auto(command: HALCommandType):
    """Starts the auto mode."""

    assert command.actor

    macro = command.actor.helpers.macros["auto"]

    result: bool = True

    while True:
        # Run the auto loop until the command is cancelled.

        macro.reset(command)
        if not await macro.run():
            result = False
            break

        if macro.cancelled:
            # Cancelled macros return result=True
            break

    if result is False:
        return command.fail()

    return command.finish()
