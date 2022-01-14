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
    "--count",
    "-c",
    type=int,
    default=1,
    help="How many exposures to take. If exposing APOGEE, the last dither pair or "
    "exposure will finish as the BOSS readout begins.",
)
@click.option(
    "--count-apogee",
    type=int,
    help="How many APOGEE exposures to take. Overrides --count.",
)
@click.option(
    "--count-boss",
    type=int,
    help="How many BOSS exposures to take. Overrides --count.",
)
@click.option(
    "--apogee/--no-apogee",
    " /-A",
    default=True,
    help="Expose APOGEE.",
)
@click.option(
    "--boss/--no-boss",
    " /-B",
    default=True,
    help="Expose BOSS.",
)
@click.option(
    "--single",
    "-S",
    is_flag=True,
    help="Take a single APOGEE exposure instead of a dither pair.",
)
@click.option(
    "-b",
    "--boss-exposure-time",
    type=float,
    help="BOSS exposure time in seconds.",
)
@click.option(
    "-a",
    "--apogee-exposure-time",
    type=float,
    help="APOGEE exposure time in seconds. If not passed, matches the BOSS exposure.",
)
@click.option(
    "--initial-apogee-dither",
    type=str,
    help="Initial APOGEE dither position.",
)
@click.option(
    "--with-fpi/--without-fpi",
    default=True,
    help="Open the FPI shutter.",
)
async def expose(
    command: HALCommandType,
    macro: Macro,
    stages: list[StageType],
    count: int = 1,
    count_apogee: int | None = None,
    count_boss: int | None = None,
    apogee: bool = True,
    boss: bool = True,
    single: bool = False,
    boss_exposure_time: float | None = None,
    apogee_exposure_time: float | None = None,
    initial_apogee_dither: str | None = None,
    with_fpi: bool = True,
):
    """Take science exposures."""

    if boss is False and "expose_boss" in stages:
        stages.remove("expose_boss")

    if apogee is False and "expose_apogee" in stages:
        stages.remove("expose_apogee")

    macro.reset(
        command,
        stages,
        count=count,
        count_apogee=count_apogee,
        count_boss=count_boss,
        apogee=apogee,
        boss=boss,
        apogee_single=single,
        boss_exposure_time=boss_exposure_time,
        apogee_exposure_time=apogee_exposure_time,
        initial_apogee_dither=initial_apogee_dither,
        with_fpi=with_fpi,
    )

    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
