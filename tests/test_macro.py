#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: test_macro.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from hal.exceptions import MacroError


if TYPE_CHECKING:
    from hal.actor import HALCommandType
    from hal.macros import Macro


async def test_macro(actor, macro: Macro, command: HALCommandType):
    await macro.run()

    assert len(actor.mock_replies) == 13
    assert command.replies.get("stage_duration") == ["macro_test", "stage1", 0.0]


async def test_macro_stage_fails(actor, macro: Macro, mocker):
    stage2 = mocker.patch.object(macro, "stage2", side_effect=MacroError)
    cleanup = mocker.patch.object(macro, "cleanup")

    await macro.run()

    assert macro.running is False

    last_stage_status = actor.mock_replies[-2]["stage_status"]
    assert "stage2,failed" in last_stage_status
    assert "cleanup,finished" in last_stage_status

    stage2.assert_called()
    cleanup.assert_called()
