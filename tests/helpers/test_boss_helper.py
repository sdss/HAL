#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2024-05-21
# @Filename: test_boss_helper.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

from typing import TYPE_CHECKING

import pytest
import pytest_mock

from clu import Command


if TYPE_CHECKING:
    from hal.actor.actor import HALActor


async def sleeper(*args, **kwargs):
    await asyncio.sleep(1)


class MockKey:
    def __init__(self, value):
        self.value = value if isinstance(value, (list, tuple)) else [value]


async def test_is_exposing(actor: HALActor, monkeypatch: pytest.MonkeyPatch):
    boss_helper = actor.helpers.boss

    monkeypatch.setitem(actor.models["boss"], "exposureState", MockKey("idle"))

    assert not boss_helper.is_exposing()
    assert not boss_helper.readout_pending


async def test_time_remaining(
    actor: HALActor,
    monkeypatch: pytest.MonkeyPatch,
    mocker: pytest_mock.MockerFixture,
):
    boss_helper = actor.helpers.boss

    mocker.patch.object(boss_helper, "_expose_boss_icc", side_effect=sleeper)

    monkeypatch.setitem(actor.models["boss"], "exposureState", MockKey("idle"))

    command = Command("", actor=actor)
    expose_task = asyncio.create_task(boss_helper.expose(command, 1))

    await asyncio.sleep(0.2)
    monkeypatch.setitem(actor.models["boss"], "exposureState", MockKey("exposing"))

    assert (
        boss_helper.exposure_time_remaining > 0
        and boss_helper.exposure_time_remaining < 1
    )

    await expose_task
    assert boss_helper.exposure_time_remaining == 0
