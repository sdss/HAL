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

from hal.macros.auto import AutoModeMacro


if TYPE_CHECKING:
    from hal.actor.actor import HALActor


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


async def test_expose_command(actor: HALActor, mock_auto_macro):
    async def stop_loop():
        await asyncio.sleep(0.2)
        mock_auto_macro.cancelled = True

    asyncio.create_task(stop_loop())

    cmd = actor.invoke_mock_command("auto")
    await cmd

    assert cmd.status.did_succeed
    mock_auto_macro.run.assert_called()
