#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-05-29
# @Filename: test_command_abort_exposures.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hal.exceptions import HALError


if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from hal.actor import HALActor


@pytest.mark.parametrize("observatory", ["LCO", "APO"])
async def test_abort_exposures(
    actor: HALActor,
    mocker: MockerFixture,
    monkeypatch: pytest.MonkeyPatch,
    observatory: str,
):
    apogee = actor.helpers.apogee
    boss = actor.helpers.boss

    expose_macro = actor.helpers.macros["expose"]
    monkeypatch.setattr(expose_macro, "_running", True)
    cancel_mock = mocker.patch.object(expose_macro, "cancel")

    monkeypatch.setattr(actor, "observatory", observatory)

    mocker.patch.object(apogee, "is_exposing", side_effect=[True, True, False, False])
    mocker.patch.object(boss, "is_exposing", side_effect=[True, True, False])

    cmd = await actor.invoke_mock_command("abort-exposures")
    await cmd

    assert cmd.status.did_succeed
    cancel_mock.assert_called_once()


async def test_abort_exposures_no_exposure_to_abort(
    actor: HALActor,
    mocker: MockerFixture,
):
    apogee = actor.helpers.apogee
    boss = actor.helpers.boss

    mocker.patch.object(apogee, "is_exposing", side_effect=[False, False])
    mocker.patch.object(boss, "is_exposing", side_effect=[False, False])

    cmd = await actor.invoke_mock_command("abort-exposures")
    await cmd

    assert cmd.status.did_succeed


async def test_abort_exposures_abort_fails(actor: HALActor, mocker: MockerFixture):
    apogee = actor.helpers.apogee
    boss = actor.helpers.boss

    mocker.patch.object(apogee, "is_exposing", side_effect=[True, False])
    mocker.patch.object(boss, "is_exposing", side_effect=[True, False])

    mocker.patch.object(apogee, "abort", side_effect=HALError("abort failed"))

    cmd = await actor.invoke_mock_command("abort-exposures")
    await cmd

    assert cmd.status.did_fail
    error = cmd.replies[-1].message["error"]
    assert "Failed to abort" in error


async def test_abort_exposures_abort_fails_unknown(
    actor: HALActor,
    mocker: MockerFixture,
):
    apogee = actor.helpers.apogee
    boss = actor.helpers.boss

    mocker.patch.object(apogee, "is_exposing", return_value=True)
    mocker.patch.object(boss, "is_exposing", return_value=True)

    mocker.patch.object(boss, "abort", return_value=False)

    cmd = await actor.invoke_mock_command("abort-exposures")
    await cmd

    assert cmd.status.did_fail
    error = cmd.replies[-1].message["error"]
    assert "Unknown error" in error
