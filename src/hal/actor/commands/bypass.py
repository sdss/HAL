#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-14
# @Filename: bypass.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from clu.parsers.click import CluGroup

from . import hal_command_parser


if TYPE_CHECKING:
    from .. import HALCommandType


__all__ = ["bypass"]


@hal_command_parser.group(cls=CluGroup)
def bypass():
    """Enable/disable bypasses."""

    pass


@bypass.command()
@click.argument("BYPASSES", type=str, nargs=-1)
async def enable(command: HALCommandType, bypasses: list[str]):
    """Enables a series of bypasses"""

    for bypass in bypasses:
        if bypass not in command.actor.helpers._available_bypasses:
            return command.fail(f"Invalid bypass name {bypass}.")

    for bypass in bypasses:
        command.actor.helpers.bypasses.add(bypass)

    return command.finish(bypasses=list(command.actor.helpers.bypasses))


@bypass.command()
@click.argument("BYPASSES", type=str, nargs=-1)
async def disable(command: HALCommandType, bypasses: list[str]):
    """Disabless a series of bypasses"""

    for bypass in bypasses:
        if bypass not in command.actor.helpers._available_bypasses:
            return command.fail(f"Invalid bypass name {bypass}.")

    for bypass in bypasses:
        if bypass in command.actor.helpers.bypasses:
            command.actor.helpers.bypasses.remove(bypass)

    return command.finish(bypasses=list(command.actor.helpers.bypasses))
