#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-26
# @Filename: auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

import click

from hal.macros.auto_pilot import AutoPilotMacro
from hal.macros.expose import ExposeMacro

from . import hal_command_parser


if TYPE_CHECKING:
    from .. import HALCommandType


__all__ = ["auto_pilot"]


@hal_command_parser.command(name="auto-pilot", aliases=["auto"])
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
    "--pause",
    is_flag=True,
    help="Pauses the execution of the macro. The current exposures will complete.",
)
@click.option(
    "--resume",
    is_flag=True,
    help="Resumes the execution of the macro.",
)
@click.option(
    "--count",
    type=int,
    default=1,
    help="Number of exposures per design.",
)
@click.option(
    "--preload-ahead",
    type=float,
    default=None,
    help="Preload the next design this many seconds before the exposure completes.",
)
@click.option(
    "--add-hartmann",
    is_flag=True,
    default=False,
    help="Take a Hartmann during the next goto-field (will not repeat Hartmanns).",
)
@click.option(
    "--remove-hartmann",
    is_flag=True,
    default=False,
    help="Removes a previously scheduled Hartmann.",
)
async def auto_pilot(
    command: HALCommandType,
    stop: bool = False,
    now: bool = False,
    modify: bool = False,
    pause: bool = False,
    resume: bool = False,
    count: int = 1,
    preload_ahead: float | None = None,
    add_hartmann: bool = False,
    remove_hartmann: bool = False,
):
    """Starts the auto-pilot mode."""

    assert command.actor

    expose_macro = command.actor.helpers.macros["expose"]
    assert isinstance(expose_macro, ExposeMacro)

    macro = command.actor.helpers.macros["auto_pilot"]
    assert isinstance(macro, AutoPilotMacro)

    if (stop or modify or pause or resume) and not macro.running:
        return command.fail(
            "I'm afraid I cannot do that Dave. The auto pilot mode is not running."
        )

    if macro.running and (add_hartmann or remove_hartmann):
        macro.hartmann = False if remove_hartmann else True
        if macro.hartmann:
            return command.finish("Scheduled a Hartmann for the next goto-field.")
        else:
            return command.finish("Removed any previously scheduled Hartmanns.")

    if pause and resume:
        return command.fail("--pause and --resume are incompatible Dave.")

    if pause:
        await expose_macro._pause()
        return command.finish()

    if resume:
        await expose_macro._resume()
        return command.finish()

    if stop is True:
        if now is True:
            command.warning(auto_pilot_message="Stopping auto-pilot mode NOW.")
            macro.cancel(now=True)
        else:
            command.warning(auto_pilot_message="Stopping auto-pilot after this stage.")
            macro.cancel(now=False)

        return command.finish()

    if modify is True:
        # For now the only option we can modify is the count of exposures.
        macro.config["count"] = count

        # Also modify active expose macro, if any is running.
        if expose_macro.running:
            expose_macro.expose_helper.update_params(
                count_boss=count,
                count_apogee=count,
            )
            expose_macro.expose_helper.refresh()

        return command.finish()

    # From this point on this is a new macro, so it should not be already running.
    if macro.running:
        return command.fail(
            "I'm afraid I cannot do that Dave. The auto mode is already running."
        )

    macro.reset(command, count=count, preload_ahead_time=preload_ahead)
    if add_hartmann:
        macro.hartmann = True
    else:
        macro.hartmann = False

    result: bool = True
    while True:
        # Reset the macro (stages and such) but keep the current config.
        macro.reset(command, reset_config=False)

        # Run the auto loop until the command is cancelled.
        if not await macro.run():
            result = False
            break

        await asyncio.sleep(0.1)

        if macro.cancelled:
            # Cancelled macros return result=True
            break

    if result is False:
        return command.fail()

    return command.finish()
