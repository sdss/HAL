#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from . import HALCommandType, hal_command_parser


__all__ = ["goto_field"]


@hal_command_parser.command(name="goto-field")
async def goto_field(command: HALCommandType):
    """Execute the go to field macro."""

    actor = command.actor

    goto_macro = actor.helpers.macros["goto_field"]
    goto_macro.reset(command=command)

    result = await goto_macro.run()

    if result is False:
        return command.fail()

    return command.finish()
