#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: goto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from hal.exceptions import HALError

from . import hal_command_parser


if TYPE_CHECKING:
    from . import HALCommandType


__all__ = ["gotoStow"]


async def goto_position(command: HALCommandType, name: str):
    """Go to position."""

    try:
        assert command.actor.helpers.tcc, "TCC helper not available."
        await command.actor.helpers.tcc.goto_position(command, name)
    except HALError as err:
        return command.fail(f"Goto position failed with error: {err}")

    return command.finish()


@hal_command_parser.command(name="gotoStow", cancellable=True)
async def gotoStow(command: HALCommandType):
    """Send the telescope to (120, 30, 0)."""

    return await goto_position(command, "stow")


@hal_command_parser.command(name="gotoAll60", cancellable=True)
async def gotoAll60(command: HALCommandType):
    """Send the telescope to (60, 60, 60)."""

    return await goto_position(command, "all_60")


@hal_command_parser.command(name="gotoStow60", cancellable=True)
async def gotoStow60(command: HALCommandType):
    """Send the telescope to (121, 60, 0)."""

    return await goto_position(command, "stow_60")


@hal_command_parser.command(name="gotoInstrumentChange", cancellable=True)
async def gotoInstrumentChange(command: HALCommandType):
    """Send the telescope to (121, 90, 0)."""

    return await goto_position(command, "instrument_change")
