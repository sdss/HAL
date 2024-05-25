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
from hal.macros.auto_pilot import AutoPilotMacro


if TYPE_CHECKING:
    from hal.actor.actor import HALActor
    from hal.macros.macro import Macro


@pytest.fixture
def mock_auto_pilot_macro(mocker: MockerFixture, actor: HALActor):
    macro = actor.helpers.macros["auto_pilot"]
    orig_run = macro.run

    async def cancel_macro():
        # Cancel macro after one iteration.
        macro.cancelled = True
        return True

    macro.run = mocker.AsyncMock(side_effect=cancel_macro)
    macro.command = Command(actor=actor)

    yield actor.helpers.macros["auto_pilot"]

    macro.run = orig_run


def test_auto_pilot_macro(actor: HALActor):
    macro = actor.helpers.macros["auto_pilot"]
    assert isinstance(macro, AutoPilotMacro)


async def test_auto_pilot_command(
    actor: HALActor,
    mock_auto_pilot_macro: AutoPilotMacro,
    mocker: MockerFixture,
):
    mock_auto_pilot_macro.reset = mocker.AsyncMock()

    cmd = actor.invoke_mock_command("auto-pilot")
    await cmd

    assert cmd.status.did_succeed

    mock_auto_pilot_macro.run.assert_called()

    calls = [
        mocker.call(cmd, count=1, preload_ahead_time=None),
        mocker.call(cmd, reset_config=False),
    ]
    mock_auto_pilot_macro.reset.assert_has_calls(calls)  # type: ignore

    assert mock_auto_pilot_macro.config["count"] == 1
    assert mock_auto_pilot_macro.config["preload_ahead_time"] == 300


@pytest.mark.parametrize(
    "observatory,design_mode,exptime,wait_time",
    [
        ("APO", "dark_time", 900, 617),
        ("APO", "bright_time", 730, 447),
        ("LCO", "dark_time", 900, 604),
        ("LCO", "bright_time", 900, 604),
    ],
)
async def test_auto_pilot_expose_time(
    actor: HALActor,
    mock_auto_pilot_macro: AutoPilotMacro,
    mocker: MockerFixture,
    observatory: str,
    design_mode: str,
    exptime: float,
    wait_time: int,
):
    expose_macro: Macro = actor.helpers.macros["expose"]
    reset_mock = mocker.patch.object(expose_macro, "reset")
    mocker.patch.object(expose_macro, "run")
    mocker.patch.object(expose_macro, "wait_until_complete", return_value=True)

    cherno_helper = mock_auto_pilot_macro.helpers.cherno
    mocker.patch.object(cherno_helper, "guiding_at_rms", return_value=True)

    conf_mock = mocker.patch.object(
        mock_auto_pilot_macro.helpers.jaeger,
        "configuration",
    )
    conf_mock.design_mode = design_mode

    mocker.patch.object(mock_auto_pilot_macro, "_wait_integration_done")
    preload_mock = mocker.patch.object(
        mock_auto_pilot_macro,
        "_wait_and_preload_design",
    )

    mock_auto_pilot_macro.command.actor.observatory = observatory
    await mock_auto_pilot_macro.expose()

    preload_mock.assert_called()
    preload_mock.assert_called_with(
        delay=wait_time,
        preload_ahead_time=config["macros"]["auto_pilot"]["preload_ahead_time"],
    )

    reset_mock.assert_called_with(
        mocker.ANY,
        count_boss=1,
        boss_exptime=exptime,
        apogee_exptime=exptime,
    )


async def test_auto_pilot_macro_preload_ahead(
    actor: HALActor,
    mock_auto_pilot_macro: AutoPilotMacro,
    mocker: MockerFixture,
):
    mock_auto_pilot_macro.reset = mocker.AsyncMock()
    cmd = actor.invoke_mock_command("auto-pilot --preload-ahead 100")
    await cmd

    assert cmd.status.did_succeed
    calls = [
        mocker.call(cmd, count=1, preload_ahead_time=100),
        mocker.call(cmd, reset_config=False),
    ]
    mock_auto_pilot_macro.reset.assert_has_calls(calls)  # type: ignore
