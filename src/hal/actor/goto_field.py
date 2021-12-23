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
async def goto_field(
    command: HALCommandType,
    macro: Macro,
    stages: list[str],
    guider_time: float,
):
    """Execute the go-to-field macro."""

    macro.reset(command, stages, guider_time=guider_time)
    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
