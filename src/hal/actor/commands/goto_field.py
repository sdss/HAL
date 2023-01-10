#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import click

from hal import config

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros import Macro
    from hal.macros.macro import StageType

    from .. import HALCommandType


__all__ = ["goto_field"]


@hal_command_parser.command(name="goto-field", cancellable=True)
@stages("goto_field", reset=False)
@click.option(
    "--auto",
    is_flag=True,
    help="Selects the stages based on the latest design loaded.",
)
@click.option(
    "--guider-time",
    type=float,
    default=config["macros"]["goto_field"]["guider_time"],
    show_default=True,
    help="Exposure time for guiding/acquisition.",
)
@click.option(
    "--fixed-rot/--no-fixed-rot",
    default=False,
    help="Slews to a fixed rot position for the FVC loop. If --no-fixed-rot then "
    "--fixed-altaz is ignored.",
)
@click.option(
    "--fixed-altaz/--no-fixed-altaz",
    default=False,
    help="Slews to a fixed alt/az position for the FVC loop.",
)
@click.option(
    "--alt",
    type=float,
    help="The fixed altitude angle to which to slew for the FVC loop. "
    "Requires --fixed-altaz to take effect.",
)
@click.option(
    "--az",
    type=float,
    help="The fixed azimuth angle to which to slew for the FVC loop. "
    "Requires --fixed-altaz to take effect.",
)
@click.option(
    "--rot",
    type=float,
    help="The fixed rotator angle to which to slew for the FVC loop.",
)
@click.option(
    "--keep-offsets/--no-keep-offsets",
    is_flag=True,
    default=True,
    help="Keep the guider offsets from the previous field.",
)
@click.option(
    "--with-hartmann",
    is_flag=True,
    help="Ensures the boss_hartmann stage is selected. Mostly relevant with --auto.",
)
async def goto_field(
    command: HALCommandType,
    macro: Macro,
    stages: list[StageType],
    guider_time: float,
    auto: bool = False,
    fixed_rot: bool = False,
    fixed_altaz: bool = False,
    alt: float | None = None,
    az: float | None = None,
    rot: float | None = None,
    keep_offsets: bool = True,
    with_hartmann: bool = False,
):
    """Execute the go-to-field macro."""

    assert command.actor

    jaeger_helper = command.actor.helpers.jaeger

    if stages is not None and auto is True:
        return command.fail("--auto cannot be used with custom stages.")
    elif auto is True:
        configuration = jaeger_helper.configuration

        # The jaeger helper marks if a configuration is a new field or not but
        # only if the previous configuration has been observed, which only works
        # in full HAL auto mode. For goto-field auto mode, we can only check if the
        # previous configuration has the same field_id, regardless of whether it
        # was observed or not.
        previous = jaeger_helper._previous[-1] if jaeger_helper._previous else None

        if configuration is None:
            return command.fail("No configuration loaded. Auto mode cannot be used.")
        elif configuration.cloned is True:
            stages = config["macros"]["goto_field"]["cloned_stages"]
        elif previous and previous.field_id == configuration.field_id:
            stages = config["macros"]["goto_field"]["repeat_field_stages"]
        elif configuration.is_rm_field is True:
            stages = config["macros"]["goto_field"]["rm_field_stages"]
        else:
            stages = config["macros"]["goto_field"]["new_field_stages"]

    if stages is not None and len(stages) == 0:
        return command.finish("No stages to run.")

    if with_hartmann and stages is not None and "boss_hartmann" not in stages:
        # Can be added at the end. Macro.reset() will order it.
        stages.append("boss_hartmann")

    macro.reset(
        command,
        stages,
        guider_time=guider_time,
        fixed_rot=fixed_rot,
        fixed_altaz=fixed_altaz,
        fvc_alt=alt,
        fvc_az=az,
        fvc_rot=rot,
        keep_offsets=keep_offsets,
    )
    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
