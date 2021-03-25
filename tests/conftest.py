#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: conftest.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from clu.testing import setup_test_actor

from hal.actor import HALActor


@pytest.fixture
async def actor():

    hal_actor = HALActor(
        name="test_actor",
        host="localhost",
        port=19980,
        log_dir=False,
    )
    hal_actor = await setup_test_actor(hal_actor)  # type: ignore

    yield hal_actor

    # Clear replies in preparation for next test.
    hal_actor.mock_replies.clear()
