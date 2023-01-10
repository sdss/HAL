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

from hal.macros.expose import ExposeMacro

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
@click.option(
    "--modify",
    is_flag=True,
    help="Modify an ongoing auto loop.",
)
@click.option(
    "--count",
    type=int,
    default=1,
    help="Number of exposures per design.",
)
async def auto(
    command: HALCommandType,
    stop: bool = False,
    now: bool = False,
    modify: bool = False,
    count: int = 1,
):
    """Starts the auto mode."""

    assert command.actor

    macro = command.actor.helpers.macros["auto"]

    if macro.running and (not stop and not modify):
        return command.fail(
            "I'm afraid I cannot do that Dave. The auto mode is already running."
        )

    if stop is True:
        if macro.running is False:
            return command.finish("Auto mode is not running.")
        elif now is True:
            command.warning(auto_mode_message="Cancelling auto mode NOW.")
            macro.cancel(now=True)
        else:
            command.warning(auto_mode_message="Cancelling auto after stage completes.")
            macro.cancel(now=False)

        return command.finish()

    if modify is True:
        if macro.running is False:
            return command.finish("Auto mode is not running.")

        # For now the only option we can modify is the count of exposures.
        macro.config["count"] = count

        # Also modify active expose macro, if any is running.
        expose_macro = command.actor.helpers.macros["expose"]
        assert isinstance(expose_macro, ExposeMacro)
        if expose_macro.running:
            expose_macro.expose_helper.update_params(count_boss=count)

        return command.finish()

    result: bool = True

    while True:
        # Run the auto loop until the command is cancelled.
        macro.reset(command, count=count)
        if not await macro.run():
            result = False
            break

        if macro.cancelled:
            # Cancelled macros return result=True
            break

    if result is False:
        return command.fail()

    return command.finish()
