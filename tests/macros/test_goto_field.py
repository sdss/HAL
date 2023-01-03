#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: test_goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import pytest


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
    ]

    actor.models["tcc"]["axePos"].value = [100, 60, 0]

    mocker.patch.object(
        actor.helpers.ffs,
        "all_closed",
        return_value=True,
    )

    yield macro


async def test_goto_field_fails_tcc(goto_field_macro):
    await goto_field_macro.run()

    # Macros don't finish commands.
    assert not goto_field_macro.command.status.is_done
    assert not goto_field_macro.running

    reply_codes = [reply.flag for reply in goto_field_macro.command.actor.mock_replies]
    assert "e" in reply_codes
