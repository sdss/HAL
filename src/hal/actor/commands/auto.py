#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-26
# @Filename: auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from . import hal_command_parser


if TYPE_CHECKING:

    from .. import HALCommandType


__all__ = ["auto"]


@hal_command_parser.command(name="auto")
@click.option(
    "--stop",
    is_flag=True,
    help="Stops the auto mode loop after the next stage completes. "
    "For an immediate stop use with --now.",
)
@click.option(
    "--now",
    is_flag=True,
    help="Along with --stop, cancels the auto mode loop immediately.",
)
async def auto(command: HALCommandType, stop: bool = False, now: bool = False):
    """Starts the auto mode."""

    assert command.actor

    macro = command.actor.helpers.macros["auto"]

    if macro.running and stop is False:
        return command.fail("Auto mode is already running.")

    if stop is True:
        if macro.running is False:
            return command.finish("Auto mode is not running.")
        elif now is True:
            command.warning(text="Cancelling auto mode NOW.")
            macro.cancel(now=True)
        else:
            command.warning(text="Cancelling auto mode after stage completes.")
            macro.cancel(now=False)

        return command.finish()

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
