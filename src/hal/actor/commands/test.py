#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-12-11
# @Filename: test.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from . import hal_command_parser, stages


if TYPE_CHECKING:
    from hal.macros import Macro

    from .. import HALCommandType


__all__ = ["test"]


@hal_command_parser.command()
@stages("test")
async def test(command: HALCommandType, macro: Macro):
    """Runs the test macro."""

    result = await macro.run()

    if result is False:
        return command.fail()

    return command.finish()
