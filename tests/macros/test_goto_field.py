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

from hal.actor.actor import HALActor
from hal.exceptions import MacroError
from hal.macros.goto_field import GotoFieldAPOMacro


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

    # Concurrent stages duration
    assert command.replies[-2].message["stage_duration"][1] == "slew:reconfigure"

    # Entire macro duration
    assert command.replies[-1].message["stage_duration"][0] == "goto_field"
    assert command.replies[-1].message["stage_duration"][1] == '""'
    assert isinstance(command.replies[-1].message["stage_duration"][2], float)


async def test_goto_field_auto_hartmann(
    actor: HALActor,
    goto_field_macro: GotoFieldAPOMacro,
    mocker: MockerFixture,
):
    """Confirms that --with-hartmann behaves correctly."""

    mocker.patch.object(goto_field_macro, "run")

    cmd = await actor.invoke_mock_command("goto-field --auto --with-hartmann")
    await cmd
    # goto_field_macro.cancel()

    # await asyncio.sleep(0.1)

    assert cmd.status.did_succeed
    assert "boss_hartmann" in goto_field_macro.stages

    await asyncio.sleep(0.1)  # Small delay to let the command really finish.

    # Try again, now without the hartmann and confirm that it is not included
    # in the stages.
    cmd = await actor.invoke_mock_command("goto-field --auto")
    await cmd

    assert cmd.status.did_succeed
    assert "boss_hartmann" not in goto_field_macro.stages


async def test_goto_field_guider_time(
    actor: HALActor,
    goto_field_macro: GotoFieldAPOMacro,
    mocker: MockerFixture,
):
    # Do not run the prepare and cleanup stages.
    mocker.patch.object(goto_field_macro, "prepare")
    mocker.patch.object(goto_field_macro, "cleanup")

    mocker.patch.object(goto_field_macro, "_guide_preconditions")

    mocker.patch.object(actor.helpers.cherno, "is_guiding", return_value=False)

    # Wrap goto_field.reset() but still call it.
    reset_mock = mocker.patch.object(
        goto_field_macro,
        "reset",
        wraps=goto_field_macro.reset,
    )

    guide_mock = mocker.patch.object(actor.helpers.cherno, "guide")

    cmd = await actor.invoke_mock_command("goto-field -s guide --guider-time 10")
    await cmd

    reset_mock.assert_called_once_with(
        mocker.ANY,
        mocker.ANY,
        guider_time=10,
        fixed_rot=mocker.ANY,
        fixed_altaz=mocker.ANY,
        fvc_alt=mocker.ANY,
        fvc_az=mocker.ANY,
        fvc_rot=mocker.ANY,
        keep_offsets=mocker.ANY,
    )

    guide_mock.assert_called_once_with(
        mocker.ANY,
        exposure_time=10,
        wait_time=mocker.ANY,
        wait=False,
    )
