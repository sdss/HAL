#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-01-21
# @Filename: actor.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import os
from collections import deque

from typing import TypeVar

from sdssdb.peewee.sdss5db import targetdb

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

        # A double ended queue to store the last two fields. Elements are tuples
        # with the format (field_id, is_cloned, is_rm_or_aqmes)
        self.field_queue = deque(maxlen=2)
        self.models["jaeger"]["configuration_loaded"].register_callback(
            self._configuration_loaded
        )

    def _configuration_loaded(self, key):
        """Processes a new configuration."""

        design_id = key.value[1]
        field_id = key.value[2]
        is_cloned = key.value[9]
        is_rm = False

        if design_id is None or design_id < 0 or field_id is None or field_id < 0:
            self.field_queue.append((field_id, is_cloned, False))
            return

        if targetdb.database.connected is False:
            self.write("w", {"error": "Database is disconnected. Trying to reconnect."})
            if not targetdb.database.connect():
                self.write("w", {"error": "Cannot connect to database."})
                return

        design_mode_label = (
            targetdb.Design.select(targetdb.Design.design_mode)
            .where(targetdb.Design.design_id == design_id)
            .scalar()
        )
        if design_mode_label is None:
            self.write(
                "w",
                {"error": f"Cannot find design_mode_label for design {design_id}"},
            )
            return
        elif design_mode_label in ["dark_monit", "dark_rm"]:
            is_rm = True

        self.write(
            "d",
            {
                "text": f"Detected new configuration with design_id={design_id} "
                f"and field_id={field_id}."
            },
        )

        self.field_queue.append((field_id, is_cloned, is_rm))


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
