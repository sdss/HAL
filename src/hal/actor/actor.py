#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os

from typing import TypeVar

from clu.legacy import LegacyActor

from hal import __version__


__all__ = ["HALActor", "ActorHelpers"]


T = TypeVar("T", bound="HALActor")


class HALActor(LegacyActor):
    """HAL actor."""

    def __init__(self, *args, **kwargs):

        schema = kwargs.pop("schema", None)
        schema = schema or os.path.join(os.path.dirname(__file__), "../etc/schema.json")

        super().__init__(*args, schema=schema, **kwargs)

        self.observatory = os.environ.get("OBSERVATORY", "APO")
        self.version = __version__

        self.helpers = ActorHelpers(self)


class ActorHelpers:
    """State helpers."""

    def __init__(self, actor: HALActor):

        from hal.helpers import (
            APOGEEHelper,
            BOSSHelper,
            FFSHelper,
            HALHelper,
            LampsHelper,
            Scripts,
            TCCHelper,
        )
        from hal.macros import all_macros

        self.actor = actor
        self.observatory = actor.observatory

        self.apogee = APOGEEHelper(actor)
        self.boss = BOSSHelper(actor)
        self.ffs = FFSHelper(actor)
        self.lamps = LampsHelper(actor)
        self.tcc = TCCHelper(actor)

        self.bypasses: set[str] = set(actor.config["bypasses"])
        self._available_bypasses = ["all"]
        self._available_bypasses += [
            helper.name
            for helper in HALHelper.__subclasses__()
            if helper.name is not None
        ]

        self.scripts = Scripts(actor, actor.config["scripts"][self.observatory])

        self.macros = {macro.name: macro for macro in all_macros}
