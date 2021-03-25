#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os

from clu.legacy import LegacyActor

from hal import __version__

from .commands import hal_command_parser


__all__ = ["HALActor"]


class HALActor(LegacyActor):
    """HAL actor."""

    parser = hal_command_parser

    def __init__(self, *args, **kwargs):

        if "schema" not in kwargs:
            kwargs["schema"] = os.path.join(
                os.path.dirname(__file__),
                "etc/schema.json",
            )

        super().__init__(*args, **kwargs)

        self.observatory = os.environ.get("OBSERVATORY", "APO")
        self.version = __version__
