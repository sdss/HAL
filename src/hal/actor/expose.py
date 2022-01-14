#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from hal.macros.macro import StageType

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros import Macro

    from . import HALCommandType


__all__ = ["expose"]


@hal_command_parser.command(cancellable=True)
@stages("expose", reset=False)
@click.option(
    "--initial-apogee-dither",
    type=str,
    help="Initial APOGEE dither position.",
)
@click.option("--with-fpi/--without-fpi", default=True, help="Open the FPI shutter.")
async def expose(
    command: HALCommandType,
    macro: Macro,
    stages: list[StageType],
    initial_apogee_dither: str | None = None,
    with_fpi: bool = True,
):
    """Take science exposures."""

    macro.reset(
        command,
        stages,
        initial_apogee_dither=initial_apogee_dither,
        with_fpi=with_fpi,
    )

    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
