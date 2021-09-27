#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: __main__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

import click
from click_default_group import DefaultGroup

from clu.tools import cli_coro
from sdsstools.daemonizer import DaemonGroup

from hal.actor import HALActor


@click.group(cls=DefaultGroup, default="actor", default_if_no_args=True)
@click.option(
    "-c",
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the user configuration file.",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Debug mode.",
)
@click.pass_context
def hal(ctx, config_file, verbose):
    """HAL"""

    ctx.obj = {"verbose": verbose, "config_file": config_file}


@hal.group(cls=DaemonGroup, prog="hal-actor", workdir=os.getcwd())
@click.pass_context
@cli_coro
async def actor(ctx):
    """Runs the actor."""

    default_config_file = os.path.join(os.path.dirname(__file__), "etc/hal.yml")
    config_file: str = ctx.obj["config_file"] or default_config_file

    hal_obj = HALActor.from_config(config_file)

    if ctx.obj["verbose"]:
        hal_obj.log.sh.setLevel(0)

    await hal_obj.start()
    await hal_obj.run_forever()


if __name__ == "__main__":
    hal()
