#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-05-26
# @Filename: abort_exposures.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

from . import hal_command_parser


if TYPE_CHECKING:
    from hal.actor import HALCommandType
    from hal.macros.expose import ExposeMacro


__all__ = ["abort_exposures"]


@hal_command_parser.command(name="abort-exposures")
async def abort_exposures(command: HALCommandType):
    """Aborts ongoing exposures.."""

    expose_macro = command.actor.helpers.macros["expose"]
    assert isinstance(expose_macro, ExposeMacro)

    if expose_macro.running:
        command.warning("Cancelling the expose macro.")
        expose_macro.cancel(now=True)

    command.warning("Aborting ongoing exposures.")

    tasks = [
        command.actor.helpers.apogee.abort(command),
        command.actor.helpers.boss.abort(command),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for iresult, result in enumerate(results):
        instrument = ["APOGEE", "BOSS"][iresult]
        if isinstance(result, Exception):
            return command.fail(f"Failed to abort {instrument} exposure: {result!s}")
        elif result is not True:
            return command.fail(f"Unkown error while aborting {instrument} exposure.")
        else:
            continue

    return command.finish(text="Exposures have been aborted.")
