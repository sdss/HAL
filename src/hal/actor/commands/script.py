#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-27
# @Filename: script.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from . import hal_command_parser


if TYPE_CHECKING:
    from . import HALCommandType


__all__ = ["script"]


@hal_command_parser.group()
def script():
    """Tools to list and run scripts."""

    pass


@script.command(name="list")
async def list_(command: HALCommandType):
    """Returns a list of available scripts."""

    available_scripts = command.actor.helpers.scripts.list_scripts()
    return command.finish(available_scripts=available_scripts)


@script.command()
async def running(command: HALCommandType):
    """Returns a list of running scripts."""

    running_scripts = list(command.actor.helpers.scripts.running.keys())
    return command.finish(running_scripts=running_scripts)


@script.command()
@click.argument("SCRIPT", type=str)
async def get_steps(command: HALCommandType, script: str):
    """Lists the steps in the script."""

    try:
        steps = command.actor.helpers.scripts.get_steps(script)
    except Exception as err:
        return command.fail(error=err)

    for step in steps:
        if step[2] is None:
            command.info(text=f"{step[0]} {step[1]}")
        else:
            command.info(text=f"{step[2]} {step[0]} {step[1]}")

    return command.finish()


@script.command()
@click.argument("SCRIPT", type=str)
async def run(command: HALCommandType, script: str):
    """Runs a script."""

    try:
        result = await command.actor.helpers.scripts.run(script, command)
    except Exception as err:
        return command.fail(error=err)

    if result is True:
        return command.finish(text=f"Script {script} has been successfully executed.")
    else:
        return command.fail(error=f"Script {script} failed or was cancelled.")


@script.command()
@click.argument("SCRIPT", type=str)
async def cancel(command: HALCommandType, script: str):
    """Cancels the execution of a script."""

    try:
        await command.actor.helpers.scripts.cancel(script)
    except Exception as err:
        command.warning(text=f"Error found while trying to cancel {script}.")
        return command.fail(error=err)

    return command.finish(f"Script {script} has been scheduled for cancellation.")
