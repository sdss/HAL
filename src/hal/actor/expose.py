#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-01-13
# @Filename: expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from hal.macros.macro import StageType

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros import Macro

    from . import HALCommandType


__all__ = ["expose"]


@hal_command_parser.command(name="goto-field", cancellable=True)
@stages("expose", reset=False)
async def expose(command: HALCommandType, macro: Macro, stages: list[StageType]):
    """Execute the go-to-field macro."""

    macro.reset(command, stages)
    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
