#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-25
# @Filename: lamps.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import StageHelper


if TYPE_CHECKING:
    from .. import Macro


VALID_LAMPS = ["FFS", "WHT", "UV", "FF", "HGCD", "NE"]
WARMUP = {"FF": 1.0, "HGCD": 120.0, "NE": 20.0, "WHT": 0.0, "UV": 0.0}


class LampsStage(StageHelper):
    """Turns on/off lamps and handles the FFS concurrently."""

    def __init__(self, warmup: dict[str, float] = {}, **lamps: dict[str, bool]):

        self.lamps = lamps

        self.warmup = WARMUP.copy()
        self.warmup.update(warmup)

    async def run(self, macro: Macro):
        """Runs the stage."""

        pass
