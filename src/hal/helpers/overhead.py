#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2023-12-04
# @Filename: overhead.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import sys
import time
import warnings
from dataclasses import dataclass
from datetime import datetime

from typing import TYPE_CHECKING

import peewee
from sdssdb.peewee.sdss5db.opsdb import Overhead, database

from hal.exceptions import HALWarning


if TYPE_CHECKING:
    from hal.macros.macro import Macro


__all__ = ["OverheadHelper"]


@dataclass
class OverheadHelper:
    """Collects and records stage overheads."""

    macro: Macro
    stage: str
    macro_id: int | None = None

    def __post_init__(self) -> None:
        self.elapsed: float | None = None

        self.start_time: float | None = None
        self.end_time: float | None = None

        self.success: bool = True

        if database.connected:
            database.become_admin()

    async def start(self):
        """Starts the timer."""

        self.elapsed = 0
        self.start_time = time.time()

    async def __aenter__(self):
        """Starts the timer."""

        await self.start()
        return self

    async def stop(self):
        """Stops the timer and records overheads."""

        if self.start_time is None:
            raise ValueError("Timer not started")

        self.end_time = time.time()
        self.elapsed = round(time.time() - self.start_time, 2)

        if self.macro.cancelled or self.macro.failed:
            self.success = False

        await self.emit_keywords()

        # Cannot run in executor or the database will not be connected.
        self.update_database()

        return

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Stops the timer and records the overhead."""

        if exc_type is not None:
            self.success = False
        else:
            self.success = True

        await self.stop()

        # __aexit__ will re-raise the exception if the return value is None/False.
        return self.success

    async def emit_keywords(self):
        """Emits the overhead as a keyword."""

        command = self.macro.command
        stage_full = f"{self.macro.name}.{self.stage}"

        if self.elapsed is None:
            command.warning(f"Overhead was not recorded for stage {stage_full}.")
            return

        command.debug(
            stage_duration=[
                self.macro.name,
                self.stage if self.stage else '""',
                self.elapsed,
            ]
        )

    def _get_datetime(self, timestamp: float | None):
        """Converts a timestamp to a datetime object."""

        if timestamp is None:
            return None

        if sys.version_info >= (3, 11):
            from datetime import UTC

            return datetime.fromtimestamp(timestamp, tz=UTC)

        return datetime.utcfromtimestamp(timestamp)

    @staticmethod
    def get_next_macro_id():  # pragma: no cover
        """Returns the next ``macro_id`` value."""

        if not database.connected:
            warnings.warn(
                "Failed connecting to DB. Overhead cannot be recorded.",
                HALWarning,
            )
            return

        try:
            macro_id_last = Overhead.select(peewee.fn.MAX(Overhead.macro_id)).scalar()
        except Exception as err:
            warnings.warn(f"Failed getting macro_id: {err}", HALWarning)
            return

        return (macro_id_last or 0) + 1

    def update_database(self):
        """Updates the database with the overhead."""

        command = self.macro.command

        if not database.connected:
            command.warning("Failed connecting to DB. Overhead cannot be recorded.")
            return

        with database.atomic():
            try:
                actor = self.macro.actor
                configuration = actor.helpers.jaeger.configuration
                cid = configuration.configuration_id if configuration else None

                start_time_dt = self._get_datetime(self.start_time)
                end_time_dt = self._get_datetime(self.end_time)

                Overhead.insert(
                    configuration_id=cid,
                    macro_id=self.macro_id,
                    macro=self.macro.name,
                    stage=self.stage,
                    start_time=start_time_dt,
                    end_time=end_time_dt,
                    elapsed=self.elapsed,
                    success=self.success,
                ).execute()

            except Exception as err:
                command.warning(f"Failed creating overhead record: {err}")
