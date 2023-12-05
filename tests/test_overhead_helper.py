#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-12-05
# @Filename: test_overhead_helper.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import time

from typing import TYPE_CHECKING

import pytest
import sdssdb.peewee.sdss5db.opsdb
from pytest_mock import MockerFixture

from hal.helpers.overhead import OverheadHelper


if TYPE_CHECKING:
    from hal.actor import HALCommandType
    from hal.macros.macro import Macro


@pytest.fixture()
def overhead_helper(macro: Macro):
    """Returns an ``OverheadHelper`` instance."""

    stage = "stage1"

    yield OverheadHelper(macro, stage)


async def test_overhead_helper(
    overhead_helper: OverheadHelper,
    command: HALCommandType,
):
    assert isinstance(overhead_helper, OverheadHelper)

    assert overhead_helper.macro is not None
    assert overhead_helper.elapsed is None

    async with overhead_helper:
        await asyncio.sleep(0.5)

    assert overhead_helper.elapsed is not None and overhead_helper.elapsed > 0.4
    assert overhead_helper.start_time is not None
    assert overhead_helper.end_time is not None
    assert overhead_helper.success is True

    assert len(command.replies) == 3
    assert command.replies[-1].message["stage_duration"][0] == "macro_test"


async def test_overhead_helper_timer_not_started(
    overhead_helper: OverheadHelper,
    mocker: MockerFixture,
):
    mocker.patch.object(time, "time", return_value=None)

    with pytest.raises(ValueError):
        async with overhead_helper:
            await asyncio.sleep(0.1)


async def test_overhead_helper_inner_fails(overhead_helper: OverheadHelper):
    with pytest.raises(RuntimeError):
        async with overhead_helper:
            await asyncio.sleep(0.1)
            raise RuntimeError("test error")

    assert overhead_helper.success is False


async def test_overhead_helper_emit_elapsed_none(overhead_helper: OverheadHelper):
    overhead_helper.elapsed = None
    await overhead_helper.emit_keywords()

    command = overhead_helper.macro.command

    assert command.replies[-1].message_code == "w"
    assert "Overhead was not recorded" in command.replies[-1].message["text"]


async def test_overhead_helper_update_database_connect_fails(
    overhead_helper: OverheadHelper,
    mocker: MockerFixture,
):
    db = mocker.patch.object(sdssdb.peewee.sdss5db.opsdb, "database")
    type(db).connected = mocker.PropertyMock(return_value=False)

    assert overhead_helper.update_database() is None

    command = overhead_helper.macro.command
    assert "Failed connecting to DB" in command.replies[-1].message["text"]


async def test_overhead_helper_update_database_indert_fails(
    overhead_helper: OverheadHelper,
    mocker: MockerFixture,
):
    mocker.patch.object(
        sdssdb.peewee.sdss5db.opsdb.Overhead,
        "insert",
        side_effect=RuntimeError,
    )

    assert overhead_helper.update_database() is None

    command = overhead_helper.macro.command
    assert "Failed creating overhead record" in command.replies[-1].message["text"]
