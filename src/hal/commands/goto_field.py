#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

from . import hal_command_parser


if TYPE_CHECKING:
    from clu import Command

    from hal.actor import HALActor

__all__ = ["goto_field"]


@hal_command_parser.command()
async def goto_field(command: Command[HALActor]):
    """Execute the go to field macro."""

    actor = command.actor
    assert actor

    goto_macro = actor.helpers.macros["goto_field"]
    goto_macro.reset(command=command)

    task = asyncio.create_task(goto_macro.run())
    await asyncio.sleep(6)
    goto_macro.cancel()
    result = await task

    if result:
        return command.finish()
    else:
        return command.fail()
