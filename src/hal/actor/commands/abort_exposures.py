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

from clu.parsers.click import unique

from hal.macros.expose import ExposeMacro

from . import hal_command_parser


if TYPE_CHECKING:
    from hal.actor import HALCommandType


__all__ = ["abort_exposures"]


async def wait_until_idle(command: HALCommandType):
    """Waits until all cameras are idle."""

    while True:
        await asyncio.sleep(0.5)

        if command.actor.helpers.apogee.is_exposing():
            continue

        if command.actor.helpers.boss.is_exposing(reading_ok=False):
            continue

        break


@hal_command_parser.command(name="abort-exposures")
@unique()
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
            return command.fail(f"Unknown error while aborting {instrument} exposure.")
        else:
            continue

    command.info("Waiting until cameras are idle.")
    await wait_until_idle(command)

    return command.finish(text="Exposures have been aborted.")
