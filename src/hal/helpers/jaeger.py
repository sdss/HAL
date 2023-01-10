#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2022-12-25
# @Filename: jaeger.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from typing import TYPE_CHECKING

from sdssdb.peewee.sdss5db import targetdb

from hal.helpers import HALHelper


if TYPE_CHECKING:
    from hal.actor import HALActor, HALCommandType


__all__ = ["JaegerHelper"]


@dataclass
class Configuration:
    """Stores information about a configuration."""

    actor: HALActor
    design_id: int
    configuration_id: int | None = None
    field_id: int | None = None
    cloned: bool = False
    preloaded: bool = False
    is_rm_field: bool = False
    new_field: bool = True
    observed: bool = False
    goto_complete: bool = False

    def __post_init__(self):
        if self.design_id is None or self.design_id < 0:
            return

        if self.check_db():
            self.set_field_id()

    def warn(self, message: str):
        """Warns users."""

        assert self.actor
        self.actor.write("w", error=message)

    def check_db(self):
        """Checks the database connection or tries to recreate it."""

        if targetdb.database.connected is False:
            self.warn("Cannot connect to database. Reconnecting.")

            if not targetdb.database.connect():
                self.warn(
                    "Cannot connect to database. "
                    "Field information may be incomplete.",
                )
                return False

        return True

    def set_field_id(self):
        """Finds the field_id for a design and whether it's RM/AQMES."""

        if self.field_id is None:
            try:
                self.field_id = targetdb.Design.get_by_id(self.design_id).field.field_id
            except Exception as err:
                self.warn(f"Failed getting field_id: {err}")
                return

        # Determine if a field is RM/AQMES. Worst case, just assume it is not.
        self.is_rm_field = False

        try:
            design_mode_label = (
                targetdb.Design.select(targetdb.Design.design_mode)
                .where(targetdb.Design.design_id == self.design_id)
                .scalar()
            )
            if design_mode_label is None:
                self.warn(f"Cannot find design_mode_label for design {self.design_id}")
            elif design_mode_label in ["dark_monit", "dark_rm"]:
                self.is_rm_field = True
        except Exception as err:
            self.warn(f"Failed determining RM/AQMES: {err}")

        return


class JaegerHelper(HALHelper):
    """Helper to interact with jaeger."""

    name = "jaeger"

    def __init__(self, actor: HALActor):
        super().__init__(actor)

        # A queue of previously loaded configurations. Really we
        # only care about the last one, but who knows?
        self._previous: deque[Configuration] = deque(maxlen=10)

        self.configuration: Configuration | None = None
        self.preloaded: Configuration | None = None

        self.model = self.actor.models["jaeger"]
        self.model["configuration_loaded"].register_callback(self._configuration_loaded)
        self.model["design_preloaded"].register_callback(self._design_preloaded)

    def warn(self, message: str):
        """Warns users."""

        self.actor.write("w", error=message)

    async def load_from_queue(self, command: HALCommandType, preload: bool = False):
        """(Pre-)Loads a design from the queue."""

        verb = "preload" if preload else "load"

        cmd = await self._send_command(
            command,
            "jaeger",
            f"configuration {verb} --epoch-delay 600",
            raise_on_fail=False,
        )

        if cmd.status.did_fail:
            self.warn("Failed loading design from the queue.")
            return False

        return True

    async def from_preloaded(self, command: HALCommandType):
        """Loads a preloaded design."""

        if self.preloaded is None:
            self.warn(
                "No active preloaded design. Will try to load a "
                "preloaded design but it will likely fail.",
            )

        await self._send_command(
            command,
            "jaeger",
            "configuration load --from-preloaded",
        )

    async def _configuration_loaded(self, key):
        """Processes a new configuration loaded."""

        current = self.configuration

        configuration_id = key.value[0]
        design_id = key.value[1]
        field_id = key.value[2]
        is_cloned = key.value[9]

        # First check if we had already preloaded this design.
        if self.preloaded and self.preloaded.design_id == design_id:
            new = self.preloaded

            new.preloaded = False
            new.configuration_id = configuration_id
            new.cloned = is_cloned
        else:
            new = Configuration(
                self.actor,
                design_id,
                configuration_id=configuration_id,
                field_id=field_id,
                cloned=is_cloned,
                preloaded=False,
            )

        user_message = (
            f"Found configuration with design_id={design_id}, field_id={field_id}."
        )

        if current:
            if current.observed and current.field_id == new.field_id:
                new.new_field = False
                user_message += " This is a repeat field design."

            self._previous.append(current)

        self.configuration = new
        self.preloaded = None

        self.actor.write("d", text=user_message)

    async def _design_preloaded(self, key):
        """Processes a new preloaded design."""

        design_id = key[0]

        # design_preloaded=-999 is output when the design is actually loaded.
        if design_id < 0:
            self.preloaded = None
            return

        # Wait for a tiny bit since the preloaded_is_cloned key is emitted at the
        # same time as design_preloaded and we want to be sure it has updated.
        # Worst case, it's not critical because when the real configuration is loaded
        # that will be updated.
        await asyncio.sleep(0.5)

        cloned = self.model["preloaded_is_cloned"].value[0]

        self.preloaded = Configuration(
            self.actor,
            design_id,
            cloned=cloned,
            preloaded=True,
        )
