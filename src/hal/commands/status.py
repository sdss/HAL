#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-27
# @Filename: status.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from clu import Command

from . import hal_command_parser


if TYPE_CHECKING:

    from hal.actor import HALActor


__all__ = ["status"]


@hal_command_parser.command()
async def status(command: Command[HALActor]):
    """Outputs the status of the system."""

    await Command("script list", parent=command).parse()

    return command.finish(text="Alles ist gut.")
