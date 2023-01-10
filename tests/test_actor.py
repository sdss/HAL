#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: test_hal.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import pytest

from hal import __version__


pytestmark = [pytest.mark.asyncio]


async def test_version(actor):
    await actor.invoke_mock_command("version")

    assert len(actor.mock_replies) == 2
    assert actor.mock_replies[-1]["version"] == __version__
