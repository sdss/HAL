#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: goto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from clu.parsers.click import cancellable

from . import hal_command_parser


if TYPE_CHECKING:
    from clu import Command

    from hal.actor import HALActor


__all__ = ["gotoStow"]


async def goto_position(command: Command[HALActor], name: str):
    """Go to position."""

    assert command.actor
    return await command.actor.helpers.tcc.goto_position(command, name)


@hal_command_parser.command(name="gotoStow")
@cancellable()
async def gotoStow(command: Command[HALActor]):
    """Send the telescope to (120, 30, 0)."""

    return await goto_position(command, "stow")


@hal_command_parser.command(name="gotoAll60")
@cancellable()
async def gotoAll60(command: Command[HALActor]):
    """Send the telescope to (60, 60, 60)."""

    return await goto_position(command, "all_60")


@hal_command_parser.command(name="gotoStow60")
@cancellable()
async def gotoStow60(command: Command[HALActor]):
    """Send the telescope to (121, 60, 0)."""

    return await goto_position(command, "stow_60")


@hal_command_parser.command(name="gotoInstrumentChange")
@cancellable()
async def gotoInstrumentChange(command: Command[HALActor]):
    """Send the telescope to (121, 90, 0)."""

    return await goto_position(command, "instrument_change")
