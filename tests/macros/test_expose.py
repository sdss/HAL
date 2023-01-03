#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-01-02
# @Filename: test_expose.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from hal.actor.actor import HALActor


@pytest.fixture
def mock_expose_macro(mocker, actor: HALActor):
    macro = actor.helpers.macros["expose"]
    orig_run = macro.run

    macro.run = mocker.AsyncMock()

    yield

    macro.run = orig_run


@pytest.fixture
def macro(mock_expose_macro, actor: HALActor):
    yield actor.helpers.macros["expose"]


async def test_expose_command(actor: HALActor, macro):
    cmd = actor.invoke_mock_command("expose")
    await cmd

    assert cmd.status.did_succeed
    macro.run.assert_called()

    assert macro.expose_helper.params.count_boss == 1
    assert macro.expose_helper.params.count_apogee == 1

    assert len(macro.expose_helper.boss_exps) == 1
    assert len(macro.expose_helper.apogee_exps) == 2


async def test_expose_command_count_2(actor: HALActor, macro):
    await actor.invoke_mock_command("expose -c 2")

    assert len(macro.expose_helper.boss_exps) == 2
    assert len(macro.expose_helper.apogee_exps) == 4


async def test_expose_command_count_2_no_pairs(actor: HALActor, macro):
    await actor.invoke_mock_command("expose -c 2 --no-pairs")

    assert len(macro.expose_helper.boss_exps) == 2
    assert len(macro.expose_helper.apogee_exps) == 2

    assert macro.expose_helper.boss_exps[0].exptime == 900
    assert macro.expose_helper.boss_exps[1].exptime == 900
    assert macro.expose_helper.apogee_exps[0].exptime == 980
    assert macro.expose_helper.apogee_exps[1].exptime == 917


async def test_expose_command_count_2_exptime(actor: HALActor, macro):
    await actor.invoke_mock_command("expose -c 2 -b 400")

    assert len(macro.expose_helper.boss_exps) == 2
    assert len(macro.expose_helper.apogee_exps) == 4

    assert macro.expose_helper.boss_exps[0].exptime == 400
    assert macro.expose_helper.apogee_exps[0].exptime == 240
    assert macro.expose_helper.apogee_exps[2].exptime == 209


async def test_expose_command_apogee_exptime(actor: HALActor, macro):
    await actor.invoke_mock_command("expose -a 1000")

    assert len(macro.expose_helper.boss_exps) == 1
    assert len(macro.expose_helper.apogee_exps) == 2

    assert macro.expose_helper.params.readout_matching is False

    assert macro.expose_helper.boss_exps[0].exptime == 1000
    assert macro.expose_helper.apogee_exps[0].exptime == 1000
    assert macro.expose_helper.apogee_exps[1].exptime == 1000


async def test_expose_command_count_apogee_boss(actor: HALActor, macro):
    await actor.invoke_mock_command("expose --count-apogee 2 --count-boss 1")

    assert len(macro.expose_helper.boss_exps) == 1
    assert len(macro.expose_helper.apogee_exps) == 4

    assert macro.expose_helper.params.readout_matching is False

    assert macro.expose_helper.boss_exps[0].exptime == 900
    assert macro.expose_helper.apogee_exps[0].exptime == 900


async def test_expose_command_fails_exposure_time(actor: HALActor, macro):
    cmd = actor.invoke_mock_command("expose -t 900 -b 400")
    await cmd

    assert cmd.status.did_fail
    macro.run.assert_not_called()


async def test_expose_command_fails_count(actor: HALActor, macro):
    cmd = actor.invoke_mock_command("expose -c 2 --count-apogee 3")
    await cmd

    assert cmd.status.did_fail
    macro.run.assert_not_called()


async def test_expose_command_fails_reads(actor: HALActor, macro):
    cmd = actor.invoke_mock_command("expose --reads 40 -a 500")
    await cmd

    assert cmd.status.did_fail
    macro.run.assert_not_called()


async def test_expose_command_no_boss(actor: HALActor, macro):
    cmd = actor.invoke_mock_command("expose -B")
    await cmd

    assert cmd.status.did_succeed
    macro.run.assert_called()

    assert "expose_boss" not in macro._flat_stages
    assert macro.expose_helper.params.readout_matching is False


async def test_expose_command_no_apogee(actor: HALActor, macro):
    cmd = actor.invoke_mock_command("expose -A")
    await cmd

    assert cmd.status.did_succeed
    macro.run.assert_called()

    assert "expose_apogee" not in macro._flat_stages
    assert macro.expose_helper.params.readout_matching is False
