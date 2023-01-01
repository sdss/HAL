#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-31
# @Filename: test_expose_helper.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import asyncio

import pytest

from clu.command import Command

from hal.macros.expose import ApogeeExposure, BossExposure, ExposeHelper, ExposeMacro


@pytest.fixture
def macro():
    yield ExposeMacro()


@pytest.fixture
def command(mocker):
    command = Command()
    command.write = mocker.MagicMock()

    yield command


@pytest.fixture
def default_params():
    params = {
        "count_apogee": 1,
        "count_boss": 1,
        "boss_exptime": 900,
        "apogee_exptime": 900,
        "pairs": True,
        "dither": True,
        "readout_matching": True,
        "initial_apogee_dither": "A",
    }

    yield params


@pytest.fixture
def expose_helper(macro, command, default_params):
    macro.reset(command, **default_params)

    yield macro.expose_helper


def _check_exposures(helper, boss_expected=None, apogee_expected=None):
    boss_exps = helper.boss_exps
    apogee_exps = helper.apogee_exps

    if boss_expected:
        assert len(boss_expected) == len(boss_exps)
        for ii, boss_exp in enumerate(boss_exps):
            assert boss_exp.exptime == boss_expected[ii][0]
            assert boss_exp.actual_exptime == boss_expected[ii][1]
            assert boss_exp.read_sync == boss_expected[ii][2]

    if apogee_expected:
        assert len(apogee_expected) == len(apogee_exps)
        for ii, apogee_exp in enumerate(apogee_exps):
            assert apogee_exp.exptime == apogee_expected[ii][0]
            assert apogee_exp.dither_position == apogee_expected[ii][1]


async def test_expose_helper(expose_helper, command):
    """Basic test of ExposeHelper."""

    assert isinstance(expose_helper, ExposeHelper)

    assert len(expose_helper.apogee_exps) == 2
    assert len(expose_helper.boss_exps) == 1

    await expose_helper.start()
    await asyncio.sleep(0.1)

    assert len(command.write.mock_calls) == 4


async def test_expose_helper_defaults(expose_helper):
    """Tests exposures with defaults (count=1)."""

    # BOSS: single exposure. Do not wait for readout, so only the flushing.
    boss_expected = [[900, 917, False]]

    # APOGEE: two exposures (dither set) with readout matching.
    apogee_expected = [[459, "A"], [459, "B"]]

    _check_exposures(
        expose_helper,
        boss_expected=boss_expected,
        apogee_expected=apogee_expected,
    )


async def test_expose_helper_yield(expose_helper):
    """Test yield methods with default settings."""

    boss_exps = []
    for exp in expose_helper.yield_boss():
        boss_exps.append(exp)

    assert len(boss_exps) == 2
    assert boss_exps[-1] is None

    apogee_exps = []
    for exp in expose_helper.yield_apogee():
        apogee_exps.append(exp)

    assert len(apogee_exps) == 3
    assert apogee_exps[-1] is None


async def test_expose_helper_count_2(macro, command, default_params):
    """Tests exposure with defaults and count=2."""

    default_params["count_apogee"] = 2
    default_params["count_boss"] = 2

    macro.reset(command, **default_params)

    boss_expected = [[900, 980, True], [900, 917, False]]
    apogee_expected = [[490, "A"], [490, "B"], [459, "B"], [459, "A"]]

    _check_exposures(
        macro.expose_helper,
        boss_expected=boss_expected,
        apogee_expected=apogee_expected,
    )


async def test_expose_helper_count_2_modify(expose_helper):
    """Tests exposure with defaults and count=2 (modifying up from count=1)."""

    expose_helper.params.count_apogee = 2
    expose_helper.params.count_boss = 2
    expose_helper.refresh()

    boss_expected = [[900, 980, True], [900, 917, False]]
    apogee_expected = [[490, "A"], [490, "B"], [459, "B"], [459, "A"]]

    _check_exposures(
        expose_helper,
        boss_expected=boss_expected,
        apogee_expected=apogee_expected,
    )


async def test_expose_helper_increase_after_started(expose_helper: ExposeHelper):
    """Tests modifying the sequence after started."""

    # Start with a count of 2
    expose_helper.params.count_apogee = 2
    expose_helper.params.count_boss = 2
    expose_helper.refresh()

    # Assume we are in the second BOSS exposure and 3/4 APOGEE exposure.
    yield_boss = expose_helper.yield_boss()
    _ = next(yield_boss)
    boss_exp_2 = next(yield_boss)

    yield_apogee = expose_helper.yield_apogee()
    _ = next(yield_apogee)
    _ = next(yield_apogee)
    apogee_exp_3 = next(yield_apogee)

    assert isinstance(boss_exp_2, BossExposure)

    assert boss_exp_2.actual_exptime == 917
    assert boss_exp_2.read_sync is False
    assert expose_helper.n_boss == 2

    assert isinstance(apogee_exp_3, ApogeeExposure)
    assert expose_helper.n_apogee == 3

    # Increase count to 3.
    expose_helper.params.count_apogee = 3
    expose_helper.params.count_boss = 3
    expose_helper.refresh()

    boss_expected = [[900, 980, True], [900, 980, True], [900, 917, False]]
    apogee_expected = [
        [490, "A"],
        [490, "B"],
        [459, "B"],
        [459, "A"],
        [459, "A"],
        [459, "B"],
    ]

    _check_exposures(
        expose_helper,
        boss_expected=boss_expected,
        apogee_expected=apogee_expected,
    )

    # Comfirm that the actual exposure time for the ongoing exposure has changed.
    assert boss_exp_2.actual_exptime == 980
    assert boss_exp_2.read_sync is True


async def test_expose_helper_decrease_after_started(expose_helper: ExposeHelper):
    """Tests modifying the sequence after started."""

    # Start with a count of 3
    expose_helper.params.count_apogee = 3
    expose_helper.params.count_boss = 3
    expose_helper.refresh()

    # Assume we are on the seconds BOSS exposure and APOGEE 3/4
    expose_helper.n_apogee = 3
    expose_helper.n_boss = 2

    # Modify to count of 2.
    expose_helper.params.count_apogee = 2
    expose_helper.params.count_boss = 2
    expose_helper.refresh()

    boss_expected = [[900, 980, True], [900, 917, False]]
    apogee_expected = [[490, "A"], [490, "B"], [490, "B"], [490, "A"]]

    _check_exposures(
        expose_helper,
        boss_expected=boss_expected,
        apogee_expected=apogee_expected,
    )
