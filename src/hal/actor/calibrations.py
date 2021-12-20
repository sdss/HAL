#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-16
# @Filename: calibrations.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from . import HALCommandType, hal_command_parser


@hal_command_parser.group()
def calibrations():
    """Performs camera and telescope calibrations."""

    pass


@calibrations.command(name="apogee-dome-flat")
async def apogee_dome_flat(command: HALCommandType):
    """Runs the APOGEE dome flat sequence."""

    actor = command.actor

    apogee_dome_flat = actor.helpers.macros["apogee_dome_flat"]
    apogee_dome_flat.reset(command=command)

    result = await apogee_dome_flat.run()

    if result is False:
        return command.fail()

    return command.finish()
