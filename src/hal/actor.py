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
from hal.tools.tcc import TCC

from .commands import hal_command_parser


__all__ = ["HALActor"]


class HALActor(LegacyActor):
    """HAL actor."""

    parser = hal_command_parser

    def __init__(self, *args, **kwargs):

        schema = kwargs.pop("schema", None)
        schema = schema or os.path.join(os.path.dirname(__file__), "etc/schema.json")

        super().__init__(*args, **kwargs)

        self.observatory = os.environ.get("OBSERVATORY", "APO")
        self.version = __version__

        self.helpers = ActorHelpers(self)


class ActorHelpers:
    """State helpers."""

    def __init__(self, actor: HALActor):

        self.tcc = TCC(actor)
