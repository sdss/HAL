#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest
from black import os

from clu.testing import setup_test_actor
from sdsstools import read_yaml_file

import hal
from hal.actor import HALActor


config_path = os.path.join(os.path.dirname(hal.__file__), "etc/hal.yml")


@pytest.fixture
async def actor():

    config = read_yaml_file(config_path)
    config["actor"].pop("tron_host")
    config["actor"].pop("tron_port")

    hal_actor = HALActor.from_config(config)
    hal_actor = await setup_test_actor(hal_actor)  # type: ignore

    yield hal_actor

    # Clear replies in preparation for next test.
    hal_actor.mock_replies.clear()
