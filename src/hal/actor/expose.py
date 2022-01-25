#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import click

from hal import config
from hal.macros.macro import StageType, flatten

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
    help="How many exposures to take. If exposing APOGEE and APOGEE exposure time "
    "is not explicitely defined, the last APOGEE exposure will finish as the "
    "BOSS readout begins.",
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
    "--pairs/--no-pairs",
    " /-P",
    default=True,
    help="Do dither pairs or single exposures. If --pairs, the exposure time for "
    "APOGEE refers to each dither and --counts refers to dither pairs.",
)
@click.option(
    "--disable-dithering",
    is_flag=True,
    help="If set, the dither position will not change between exposures.",
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
    "-r",
    "--reads",
    type=int,
    help="Number of APOGEE reads. Incompatible with --apogee-exposure-time.",
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
    stages: list[StageType] | None,
    count: int = 1,
    count_apogee: int | None = None,
    count_boss: int | None = None,
    apogee: bool = True,
    boss: bool = True,
    pairs: bool = True,
    disable_dithering: bool = False,
    boss_exposure_time: float | None = None,
    apogee_exposure_time: float | None = None,
    reads: int | None = None,
    initial_apogee_dither: str | None = None,
    with_fpi: bool = True,
):
    """Take science exposures."""

    if reads is not None and apogee_exposure_time is not None:
        return command.fail("--reads and --apogee-exposure-time are incompatible.")

    if reads is not None:
        apogee_exposure_time = reads * config["durations"]["apogee_read"]

    selected_stages = cast(list[StageType], stages or flatten(macro.__STAGES__.copy()))

    if boss is False and "expose_boss" in selected_stages:
        selected_stages.remove("expose_boss")

    if apogee is False and "expose_apogee" in selected_stages:
        selected_stages.remove("expose_apogee")

    macro.reset(
        command,
        selected_stages,
        count=count,
        count_apogee=count_apogee,
        count_boss=count_boss,
        apogee=apogee,
        boss=boss,
        pairs=pairs,
        disable_dithering=disable_dithering,
        boss_exposure_time=boss_exposure_time,
        apogee_exposure_time=apogee_exposure_time,
        initial_apogee_dither=initial_apogee_dither,
        with_fpi=with_fpi,
    )

    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
