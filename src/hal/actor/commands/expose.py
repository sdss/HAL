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
from hal.helpers import get_default_exposure_time
from hal.macros.macro import StageType, flatten

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros.expose import ExposeMacro

    from .. import HALCommandType


__all__ = ["expose"]


@hal_command_parser.command()
@stages("expose", reset=False)
@click.option(
    "--stop",
    is_flag=True,
    help="Cancels an ongoing expose macro. Does not abort the ongoing exposures.",
)
@click.option(
    "--modify",
    "-m",
    is_flag=True,
    help="Modify a running expose macro. The parameters of the previous expose command "
    "are NOT remembered; all flags must be passed again.",
)
@click.option(
    "--pause",
    is_flag=True,
    help="Pauses the execution of the macro. The current exposures will complete.",
)
@click.option(
    "--resume",
    is_flag=True,
    help="Resumes the execution of the macro.",
)
@click.option(
    "--count",
    "-c",
    type=int,
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
    "-t",
    "--exposure-time",
    type=float,
    help="Exposure time, in seconds.",
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
    help="APOGEE exposure time in seconds. Disables readout matching.",
)
@click.option(
    "-r",
    "--reads",
    type=int,
    help="Number of APOGEE reads. Incompatible with --apogee-exposure-time.",
)
@click.option(
    "-d",
    "--disable-readout-matching",
    is_flag=True,
    help="Does not try to match exposure times so that the last BOSS readout starts "
    "as APOGEE finishes exposing.",
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
    macro: ExposeMacro,
    stages: list[StageType] | None,
    stop: bool = False,
    modify: bool = False,
    pause: bool = False,
    resume: bool = False,
    count: int = 1,
    count_apogee: int | None = None,
    count_boss: int | None = None,
    apogee: bool = True,
    boss: bool = True,
    pairs: bool = True,
    disable_dithering: bool = False,
    exposure_time: float | None = None,
    boss_exposure_time: float | None = None,
    apogee_exposure_time: float | None = None,
    reads: int | None = None,
    initial_apogee_dither: str | None = None,
    with_fpi: bool = True,
    disable_readout_matching: bool = False,
):
    """Take science exposures."""

    if (stop or modify or pause or resume) and not macro.running:
        return command.fail("No expose macro currently running.")

    # Check incompatible options.
    if exposure_time and (boss_exposure_time or apogee_exposure_time or reads):
        return command.fail(
            "--exposure-time cannot be used with "
            "--apogee-exposure-time, --boss-exposure-time or --reads."
        )

    if count and (count_apogee or count_boss):
        return command.fail(
            "--count cannot be used with --count-apogee or --count-boss."
        )

    if reads is not None and apogee_exposure_time is not None:
        return command.fail("--reads and --apogee-exposure-time are incompatible.")

    if stop:
        macro.cancel()
        return command.finish("Expose macro has been cancelled")

    if pause and resume:
        return command.fail("--pause and --resume are incompatible.")

    # Handle pause/resume
    if pause:
        await macro._pause()
        return command.finish()

    if resume:
        await macro._resume()
        return command.finish()

    # Convert reads to exposure time.
    if reads is not None:
        apogee_exposure_time = reads * config["durations"]["apogee_read"]

    # Disable readout matching if we are providing exposure times or counts
    # for each instrument.
    if (apogee_exposure_time and boss_exposure_time) or (count_apogee and count_boss):
        disable_readout_matching = True

    # If nothing has been defined explicitely, revert to the defaults.
    if not exposure_time:
        if not boss_exposure_time and not apogee_exposure_time:
            design_mode: str | None = None
            assert command.actor.helpers.jaeger, "Jaeger helper not available."
            if command.actor.helpers.jaeger.configuration:
                design_mode = command.actor.helpers.jaeger.configuration.design_mode
            exposure_time = get_default_exposure_time(
                command.actor.observatory,
                design_mode,
            )
        elif apogee_exposure_time and not boss_exposure_time:
            boss_exposure_time = apogee_exposure_time
            disable_readout_matching = True

    if not count and not count_boss and not count_apogee:
        count = config["macros"]["expose"]["fallback"]["count"]

    if exposure_time:
        boss_exposure_time = exposure_time
        apogee_exposure_time = exposure_time

    if count:
        count_apogee = count_boss = count

    selected_stages = cast(list[StageType], stages or flatten(macro.__STAGES__.copy()))

    if boss is False and "expose_boss" in selected_stages:
        selected_stages.remove("expose_boss")

    if apogee is False and "expose_apogee" in selected_stages:
        selected_stages.remove("expose_apogee")

    if "expose_apogee" not in selected_stages or "expose_boss" not in selected_stages:
        disable_readout_matching = True

    initial_apogee_dither = (
        initial_apogee_dither
        or command.actor.helpers.apogee.get_dither_position()
        or "A"
    )

    params = dict(
        count_apogee=count_apogee,
        count_boss=count_boss,
        pairs=pairs,
        dither=not disable_dithering,
        boss_exptime=boss_exposure_time,
        apogee_exptime=apogee_exposure_time,
        readout_matching=not disable_readout_matching,
    )

    # Handle macro modification.
    if modify:
        command.warning("Modifying running expose macro.")
        macro.expose_helper.update_params(**params)
        macro.expose_helper.refresh()

        return command.finish()

    # From this point on this is a new macro, so it should not be already running.
    if macro.running:
        return command.fail("The expose macro is already running.")

    macro.reset(
        command,
        selected_stages,
        initial_apogee_dither=initial_apogee_dither,
        with_fpi=with_fpi,
        force=False,
        **params,
    )

    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
