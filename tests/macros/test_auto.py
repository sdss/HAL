#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-04-01
# @Filename: test_auto.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pytest_mock import MockerFixture

from clu.command import Command

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

    async def cancel_macro():
        # Cancel macro after one iteration.
        macro.cancelled = True
        return True

    macro.run = mocker.AsyncMock(side_effect=cancel_macro)
    macro.command = Command(actor=actor)

    yield actor.helpers.macros["auto"]

    macro.run = orig_run


def test_auto_macro(actor: HALActor):
    macro = actor.helpers.macros["auto"]
    assert isinstance(macro, AutoModeMacro)


async def test_auto_command(
    actor: HALActor,
    mock_auto_macro: AutoModeMacro,
    mocker: MockerFixture,
):
    mock_auto_macro.reset = mocker.AsyncMock()

    cmd = actor.invoke_mock_command("auto")
    await cmd

    assert cmd.status.did_succeed

    mock_auto_macro.run.assert_called()
    mock_auto_macro.reset.assert_called_with(cmd, count=1, preload_ahead_time=None)

    assert mock_auto_macro.config["count"] == 1
    assert mock_auto_macro.config["preload_ahead_time"] == 300


@pytest.mark.parametrize(
    "observatory,design_mode,wait_time",
    [
        ("APO", "dark_time", 617),
        ("APO", "bright_time", 447),
        ("LCO", "dark_time", 604),
        ("LCO", "bright_time", 604),
    ],
)
async def test_auto_expose_time(
    actor: HALActor,
    mock_auto_macro: AutoModeMacro,
    mocker: MockerFixture,
    observatory: str,
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

    mock_auto_macro.command.actor.observatory = observatory
    await mock_auto_macro.expose()

    preload_mock.assert_called()
    preload_mock.assert_called_with(
        wait_time,
        config["macros"]["auto"]["preload_ahead_time"],
    )


async def test_auto_macro_preload_ahead(
    actor: HALActor,
    mock_auto_macro: AutoModeMacro,
    mocker: MockerFixture,
):
    mock_auto_macro.reset = mocker.AsyncMock()
    cmd = actor.invoke_mock_command("auto --preload-ahead 100")
    await cmd

    assert cmd.status.did_succeed
    mock_auto_macro.reset.assert_called_with(cmd, count=1, preload_ahead_time=100)
