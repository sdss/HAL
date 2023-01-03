#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: test_apogee_dome_flat.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.asyncio]


async def test_apogee_dome_flat_gang_not_at_cart(actor, command):
    macro = actor.helpers.macros["apogee_dome_flat"]
    macro.reset(command=command)

    await macro.run()

    # Macros don't finish commands.
    assert not macro.command.status.is_done
    assert not macro.running

    reply_codes = [reply.flag for reply in actor.mock_replies]
    assert "e" in reply_codes


async def test_apogee_dome_flat_succeeds(actor, command, mocker):
    mocker.patch.object(
        actor.helpers.apogee.gang_helper,
        "at_cartridge",
        return_value=True,
    )

    mocker.patch.object(
        actor.helpers.ffs,
        "all_closed",
        return_value=True,
    )

    macro = actor.helpers.macros["apogee_dome_flat"]
    macro.reset(command=command)

    await macro.run()

    assert not macro.running

    reply_codes = [reply.flag for reply in actor.mock_replies]
    assert "e" not in reply_codes
