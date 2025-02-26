#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os

from typing import ClassVar

from clu.legacy import LegacyActor

from hal import __version__
from hal.actor.commands import hal_command_parser


__all__ = ["HALActor", "ActorHelpers"]


class HALActor(LegacyActor):
    """HAL actor."""

    _instance: ClassVar[HALActor | None] = None
    parser = hal_command_parser

    def __init__(self, *args, **kwargs):
        schema = kwargs.pop("schema", None)
        schema = schema or os.path.join(os.path.dirname(__file__), "../etc/schema.json")

        self.observatory = os.environ.get("OBSERVATORY", "APO")

        if self.observatory == "APO":
            kwargs["models"] += ["tcc", "mcp", "boss"]
        elif self.observatory == "LCO":
            kwargs["models"] += ["yao", "lcolamps"]

        super().__init__(*args, schema=schema, **kwargs)

        self.version = __version__

        self.helpers = ActorHelpers(self)

        HALActor._instance = self

        instruments = self.config["enabled_instruments"]
        self.log.info(f"Enabled instruments: {instruments!r}")

    @staticmethod
    def get_instance():
        """Returns the current instance.

        Note that this class is not a proper singleton; if called multiple times
        it will re-initialise and the instance will change. This is an easy way
        to get the instance when needed.

        """

        return HALActor._instance


class ActorHelpers:
    """State helpers."""

    def __init__(self, actor: HALActor):
        from hal.helpers import (
            APOGEEHelper,
            BOSSHelper,
            ChernoHelper,
            FFSHelper,
            HALHelper,
            JaegerHelper,
            LampsHelperAPO,
            LampsHelperLCO,
            Scripts,
            TCCHelper,
        )
        from hal.macros import all_macros

        self.actor = actor
        self.observatory = actor.observatory

        self.apogee = APOGEEHelper(actor)
        self.boss = BOSSHelper(actor)
        self.cherno = ChernoHelper(actor)
        self.jaeger = JaegerHelper(actor)

        if self.observatory == "APO":
            self.ffs = FFSHelper(actor)
            self.lamps = LampsHelperAPO(actor)
            self.tcc = TCCHelper(actor)
        else:
            self.ffs = None
            self.lamps = LampsHelperLCO(actor)
            self.tcc = None

        self.bypasses: set[str] = set(actor.config["bypasses"])
        self._available_bypasses = ["all"]
        self._available_bypasses += [
            helper.name
            for helper in HALHelper.__subclasses__()
            if helper.name is not None
        ]

        self.scripts = Scripts(actor, actor.config["scripts"][self.observatory])

        self.macros = {
            macro.name: macro
            for macro in all_macros
            if macro.observatory is None
            or macro.observatory.lower() == self.observatory.lower()
        }
