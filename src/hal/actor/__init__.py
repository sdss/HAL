#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import functools

import click

from clu import Command
from clu.parsers.click import command_parser, coro_helper

from hal.actor.actor import HALActor
from hal.macros.macro import flatten


hal_command_parser = command_parser

HALCommandType = Command[HALActor]


def stages(macro_name: str):
    """A decorator that adds ``--stages`` and ``--list-stages`` options."""

    def _split_stages(ctx, param, values):

        if values is None:
            return None

        _stages = [c.strip() for c in values.split(",")]

        return _stages

    def decorator(f):
        @functools.wraps(f)
        @click.option(
            "--list-stages",
            is_flag=True,
            help="List the stages for this macro.",
        )
        @click.option(
            "-s",
            "--stages",
            type=str,
            metavar="<stages>",
            callback=_split_stages,
            help="Comma-separated list of stages to execute.",
        )
        async def wrapper(
            command: Command[HALActor],
            *args,
            list_stages: bool = False,
            stages: list[str] | None = None,
            **kwargs,
        ):

            if macro_name not in command.actor.helpers.macros:
                raise click.BadArgumentUsage(f"Invalid macro {macro_name}")

            macro = command.actor.helpers.macros[macro_name]

            if stages is not None:
                for stage in stages:
                    if stage not in flatten(macro.__STAGES__ + macro.__CLEANUP__):
                        raise click.BadArgumentUsage(f"Invalid stage {stage}")

            macro.reset(command, stages)

            if list_stages is True:
                macro.list_stages(command=command)
                return command.finish()

            return await coro_helper(f, command, macro, *args, **kwargs)

        return functools.update_wrapper(wrapper, f)

    return decorator


from .calibrations import *
from .goto import *
from .goto_field import *
from .script import *
from .status import *
