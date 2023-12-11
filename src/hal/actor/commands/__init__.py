#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-26
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import functools

from typing import TYPE_CHECKING

import click

from clu import Command
from clu.parsers.click import command_parser, coro_helper

from hal.macros.macro import StageType, flatten


if TYPE_CHECKING:
    from hal.actor.actor import HALActor


hal_command_parser = command_parser


def stages(macro_name: str, reset: bool = True):
    """A decorator that adds ``--stages`` and ``--list-stages`` options.

    If ``reset=True`` resets the macro with the list of stages to run and passes
    the command and macro to the callback. If ``reset=False`` it does not reset
    the macro and, in addition to command and macro, also passes the list of
    stages. The latter is useful when additional options need to be passsed to
    the macro at reset.

    """

    def _split_stages(ctx, param, values):
        if values is None:
            return None

        _stages = [c.strip() for c in values.split(",")]

        return _stages

    def decorator(f):
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
        @functools.wraps(f)
        async def wrapper(
            command: Command[HALActor],
            *args,
            list_stages: bool = False,
            stages: list[StageType] | None = None,
            **kwargs,
        ):
            if macro_name not in command.actor.helpers.macros:
                raise click.BadArgumentUsage(f"Invalid macro {macro_name}")

            macro = command.actor.helpers.macros[macro_name]

            if list_stages is True:
                macro.list_stages(command=command, only_all=True)
                return command.finish()

            if stages is not None:
                for stage in stages:
                    if stage not in flatten(macro.__STAGES__ + macro.__CLEANUP__):
                        raise click.BadArgumentUsage(f"Invalid stage {stage}")

            if reset:
                macro.reset(command, stages)
                return await coro_helper(f, command, macro, *args, **kwargs)
            else:
                return await coro_helper(f, command, macro, stages, *args, **kwargs)

        return functools.update_wrapper(wrapper, f)

    return decorator


from .auto import *
from .bypass import *
from .calibrations import *
from .expose import *
from .goto import *
from .goto_field import *
from .script import *
from .status import *
from .test import *
