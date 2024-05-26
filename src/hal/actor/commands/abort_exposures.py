#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-05-26
# @Filename: abort_exposures.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from . import hal_command_parser


if TYPE_CHECKING:

    from .. import HALCommandType


__all__ = ["abort_exposures"]


@hal_command_parser.command(name="abort-exposures")
async def abort_exposures(command: HALCommandType):
    """Aborts ongoing exposures.."""

    if command.actor.observatory == "APO":
        return command.fail("abort-exposures is not supported for APO.")

    tasks = [
        command.actor.helpers.apogee.abort(command),
        command.actor.helpers.boss.abort(command),
    ]

    return command.finish()
