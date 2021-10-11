#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-27
# @Filename: status.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from clu import Command

from . import hal_command_parser


if TYPE_CHECKING:

    from hal.actor import HALActor


__all__ = ["status"]


@hal_command_parser.command()
@click.option("--full", is_flag=True, help="Outputs additional information.")
async def status(command: Command[HALActor], full: bool = False):
    """Outputs the status of the system."""

    actor = command.actor
    assert actor

    await Command("script list", parent=command).parse()

    macros = actor.helpers.macros
    command.info(running_macros=[macro for macro in macros if macros[macro].running])

    if full:
        command.info(macros=sorted(list(macros)))
        for macro_name in sorted(macros):
            macros[macro_name].list_stages(command, level="d")
            macros[macro_name].output_stage_status(command, level="d")

    return command.finish(text="Alles ist gut.")
