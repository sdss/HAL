#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-04-01
# @Filename: test_auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture

from hal import config
from hal.macros.auto import AutoModeMacro


if TYPE_CHECKING:
    from hal.actor.actor import HALActor
    from hal.macros.auto import AutoModeMacro
    from hal.macros.macro import Macro


@pytest.fixture
def mock_auto_macro(mocker: MockerFixture, actor: HALActor):
    macro = actor.helpers.macros["auto"]
    orig_run = macro.run

    macro.run = mocker.AsyncMock()

    yield actor.helpers.macros["auto"]

    macro.run = orig_run


def test_auto_macro(actor: HALActor):
    macro = actor.helpers.macros["auto"]
    assert isinstance(macro, AutoModeMacro)


async def test_auto_command(actor: HALActor, mock_auto_macro: AutoModeMacro):
    async def stop_loop():
        await asyncio.sleep(0.2)
        mock_auto_macro.cancelled = True

    asyncio.create_task(stop_loop())

    cmd = actor.invoke_mock_command("auto")
    await cmd

    assert cmd.status.did_succeed
    mock_auto_macro.run.assert_called()


@pytest.mark.parametrize(
    "design_mode,wait_time", [("dark_time", 737), ("bright_time", 567)]
)
async def test_auto_expose_time(
    actor: HALActor,
    mock_auto_macro: AutoModeMacro,
    mocker: MockerFixture,
    design_mode: str,
    wait_time: int,
):
    expose_macro: Macro = actor.helpers.macros["expose"]
    mocker.patch.object(expose_macro, "reset")
    mocker.patch.object(expose_macro, "run")
    mocker.patch.object(expose_macro, "wait_until_complete", return_value=True)

    cherno_helper = mock_auto_macro.helpers.cherno
    mocker.patch.object(cherno_helper, "guiding_at_rms", return_value=True)

    conf_mock = mocker.patch.object(mock_auto_macro.helpers.jaeger, "configuration")
    conf_mock.design_mode = design_mode

    preload_mock = mocker.patch.object(mock_auto_macro, "_preload_design")

    await mock_auto_macro.expose()

    preload_mock.assert_called()
    preload_mock.assert_called_with(
        wait_time,
        config["macros"]["auto"]["preload_ahead_time"],
    )
