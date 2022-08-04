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
from hal.macros.macro import StageType

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros import Macro

    from . import HALCommandType


__all__ = ["goto_field"]


@hal_command_parser.command(name="goto-field", cancellable=True)
@stages("goto_field", reset=False)
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
async def goto_field(
    command: HALCommandType,
    macro: Macro,
    stages: list[StageType],
    guider_time: float,
    fixed_rot: bool = False,
    fixed_altaz: bool = False,
    alt: float | None = None,
    az: float | None = None,
    rot: float | None = None,
):
    """Execute the go-to-field macro."""

    macro.reset(
        command,
        stages,
        guider_time=guider_time,
        fixed_rot=fixed_rot,
        fixed_altaz=fixed_altaz,
        fvc_alt=alt,
        fvc_az=az,
        fvc_rot=rot,
    )
    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
