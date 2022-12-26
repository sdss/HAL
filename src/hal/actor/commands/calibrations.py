#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: calibrations.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros import Macro

    from .. import HALCommandType


@hal_command_parser.group()
def calibrations():
    """Performs camera and telescope calibrations."""

    pass


@calibrations.command(name="apogee-dome-flat")
@stages("apogee_dome_flat")
async def apogee_dome_flat(command: HALCommandType, macro: Macro):
    """Runs the APOGEE dome flat sequence."""

    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
