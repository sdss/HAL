#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-05-30
# @Filename: test_command_auto_pilot.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hal.helpers.jaeger import Configuration
from hal.macros.auto_pilot import AutoPilotMacro


if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from hal.actor import HALActor


def _auto_pilot_run_once(macro: AutoPilotMacro):
    async def run_once():
        result = await AutoPilotMacro.run(macro)
        macro.cancelled = True
        return result

    return run_once


@pytest.fixture()
def mock_auto_pilot(
    actor: HALActor,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
):
    macro = actor.helpers.macros["auto_pilot"]
    assert isinstance(macro, AutoPilotMacro)

    mocker.patch.object(actor.helpers.apogee, "get_exposure_state", return_value="idle")
    mocker.patch.object(actor.helpers.boss, "get_exposure_state", return_value="idle")
    monkeypatch.setattr(macro.system_state, "exposure_time_remaining", 0.0)

    monkeypatch.setattr(
        actor.helpers.jaeger,
        "configuration",
        Configuration(
            actor=actor,
            design_id=1,
            configuration_id=1,
            loaded=True,
        ),
    )

    goto_field_macro = actor.helpers.macros["goto_field"]
    mocker.patch.object(goto_field_macro, "run")

    mocker.patch.object(actor.helpers.cherno, "is_guiding", return_value=True)
    mocker.patch.object(actor.helpers.cherno, "guiding_at_rms", return_value=True)

    expose_macro = actor.helpers.macros["expose"]
    mocker.patch.object(expose_macro, "run")

    mocker.patch.object(macro, "run", side_effect=_auto_pilot_run_once(macro))


async def test_command_auto_pilot(actor: HALActor, mock_auto_pilot):
    cmd = await actor.invoke_mock_command("auto-pilot")
    await cmd

    assert cmd.status.did_succeed
