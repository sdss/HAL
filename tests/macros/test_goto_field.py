#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: test_goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio

import pytest
from pytest_mock import MockerFixture

from hal.exceptions import MacroError


pytestmark = [pytest.mark.asyncio]


@pytest.fixture()
async def goto_field_macro(actor, command, mocker):
    macro = actor.helpers.macros["goto_field"]
    macro.reset(command=command)

    actor.models["jaeger"]["configuration_loaded"].value = [
        123,
        1234,
        12345,
        10,
        20,
        0.0,
        None,
        None,
        None,
        False,
    ]

    actor.models["tcc"]["axePos"].value = [100, 60, 0]

    mocker.patch.object(
        actor.helpers.ffs,
        "all_closed",
        return_value=True,
    )

    yield macro


async def test_goto_field_fails_tcc(goto_field_macro, mocker: MockerFixture):
    mocker.patch.object(goto_field_macro, "_all_lamps_off", return_value=True)

    # This causes the slew stage to fail immediately since the first thing it does
    # is sleep for a bit.
    mocker.patch.object(asyncio, "sleep", side_effect=MacroError)
    await goto_field_macro.run()

    command = goto_field_macro.command

    # Macros don't finish commands.
    assert not command.status.is_done
    assert not goto_field_macro.running

    reply_codes = [reply.flag for reply in command.actor.mock_replies]
    assert "e" in reply_codes

    assert command.replies[-1].message["stage_duration"][1] == "slew:reconfigure"
