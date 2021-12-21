#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import os

import pytest

from clu import Command
from clu.testing import setup_test_actor
from sdsstools import read_yaml_file

import hal
from hal.actor import HALActor
from hal.helpers import HALHelper
from hal.macros import Macro


config_path = os.path.join(os.path.dirname(hal.__file__), "etc/hal.yml")


@pytest.fixture(autouse=True)
def mock_send_command(mocker):

    HALHelper._send_command = mocker.AsyncMock()
    Macro.send_command = mocker.AsyncMock()


@pytest.fixture
async def actor():

    config = read_yaml_file(config_path)

    hal_actor = HALActor.from_config(config)
    hal_actor = await setup_test_actor(hal_actor)  # type: ignore

    yield hal_actor

    # Clear replies in preparation for next test.
    hal_actor.mock_replies.clear()


@pytest.fixture
def command(actor):

    yield Command(actor=actor)


@pytest.fixture
def macro(actor: HALActor, command: Command[HALActor]):
    class MacroTest(Macro):

        name = "macro_test"

        __STAGES__ = ["stage1", "stage2"]
        __CLEANUP__ = ["cleanup"]

        async def stage1(self):
            pass

        async def stage2(self):
            pass

        async def cleanup(self):
            pass

    actor.helpers.macros["macro_test"] = MacroTest()
    actor.helpers.macros["macro_test"].reset(command=command)

    yield actor.helpers.macros["macro_test"]
