#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
from contextlib import suppress
from time import time

from hal import config
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["GotoFieldMacro"]


class GotoFieldMacro(Macro):
    """Go to field macro."""

    name = "goto_field"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = [
        ("slew", "reconfigure"),
        "boss_hartmann",
        ("fvc", "boss_arcs"),
        "boss_flat",
        "acquire",
        "guide",
    ]
    __CLEANUP__ = ["cleanup"]

    _lamps_task: asyncio.Task | None = None

    async def prepare(self):
        """Check configuration and run pre-slew checks."""

        self._lamps_task = None

        if "reconfigure" in self._flat_stages:
            configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
            last_seen = configuration_loaded.last_seen

            if last_seen is None:
                self.command.warning("The age of the loaded configuration is unknown.")
            elif time() - last_seen > 3600:  # One hour
                raise MacroError("Configuration is too old. Load a new configuration.")

        # Start closing the FFS if they are open but do not block.
        await self._close_ffs(wait=False)

        # Stop the guider.
        # TODO: create a Cherno helper to group these commands and monitor if the
        # guider is running.
        await self.send_command("cherno", "stop")

        await self.helpers.tcc.axis_stop(self.command)

        # Ensure the APOGEE shutter is closed.
        await self.helpers.apogee.shutter(
            self.command,
            open=False,
            shutter="apogee",
        )

        # If lamps are needed, turn them on now but do not wait for them to warm up.
        if "boss_hartmann" in self._flat_stages or "boss_arcs" in self._flat_stages:
            self._lamps_task = asyncio.create_task(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    ["HgCd", "Ne"],
                    True,
                    turn_off_others=True,
                )
            )
        elif "boss_flat" in self._flat_stages:
            self._lamps_task = asyncio.create_task(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    ["ff"],
                    True,
                    turn_off_others=True,
                )
            )
        else:
            await self.helpers.lamps.all_off(self.command)

    async def _close_ffs(self, wait: bool = True):
        """Closes the FFS."""

        if not self.helpers.ffs.all_closed():
            self.command.info("Closing FFS")
            task = self.helpers.ffs.close(self.command)

            if wait:
                await task
            else:
                asyncio.create_task(task)

    async def slew(self):
        """Slew to field."""

        configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
        ra, dec, pa = configuration_loaded[3:6]

        if any([ra is None, dec is None, pa is None]):
            raise MacroError("Unknown RA/Dec/PA coordinates for field.")

        await self.helpers.tcc.goto_position(
            self.command,
            where={"ra": ra, "dec": dec, "rot": pa},
        )

    async def reconfigure(self):
        """Reconfigures the FPS."""

        self.command.info("Reconfiguring FPS array.")

        await self.send_command("jaeger", "configuration reverse")
        await self.send_command("jaeger", "configuration execute")

    async def boss_hartmann(self):
        """Takes the hartmann sequence."""

        # First check that the FFS are closed and lamps on. We don't care for how long.
        await self._close_ffs()

        if "slew" not in self._flat_stages and "reconfigure" not in self._flat_stages:
            self.command.info("Waiting 10 seconds for the lamps to warm-up.")
            await asyncio.sleep(10)

        lamp_status = self.helpers.lamps.list_status()
        if lamp_status["Ne"][0] is not True or lamp_status["HgCd"][0] is not True:
            raise MacroError("Lamps are not on for Hartmann. This should not happen.")

        # Run hartmann and adjust the collimator but ignore residuals.
        self.command.info("Running hartmann collimate.")
        await self.send_command(
            "hartmann",
            "collimate ignoreResiduals",
            time_limit=config["timeouts"]["hartmann"],
        )

        # Now check if there are residuals that require modifying the blue ring.
        sp1Residuals = self.actor.models["hartmann"]["sp1Residuals"][2]
        if sp1Residuals != "OK":
            raise MacroError(
                "Please adjust the blue ring and run goto-field again. "
                "The collimator has been adjusted."
            )

    async def boss_arcs(self):
        """Takes BOSS arcs."""

        await self._close_ffs()

        # Check lamps. Use HgCd since if it's on Ne should also be.
        lamp_status = self.helpers.lamps.list_status()

        if lamp_status["HgCd"][3] is False:
            if self._lamps_task is not None:
                # Lamps have been commanded on but are not warmed up yet.
                self.command.info("Waiting for lamps to warm up.")
                await self._lamps_task
            else:
                self.command.warning("Arc lamps are not on. Turning them on.")
                await self.helpers.lamps.turn_lamp(
                    self.command,
                    ["HgCd", "Ne"],
                    True,
                    turn_off_others=True,
                )

        self.command.info("Taking BOSS arc.")

        arc_time = self.config["arc_time"]

        await self.helpers.boss.expose(
            self.command,
            arc_time,
            exp_type="arc",
            readout=True,
            read_async=True,
        )

    async def boss_flat(self):
        """Takes the BOSS flat."""

        self.command.info("Taking BOSS flat.")

        await self._close_ffs()

        pretasks = []

        if "boss_arcs" in self._flat_stages or "boss_hartmann" in self._flat_stages:
            pretasks.append(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    ["ff"],
                    True,
                    turn_off_others=True,
                )
            )
        else:
            if self._lamps_task and not self._lamps_task.done():
                await self._lamps_task

        if self.helpers.boss.readout_pending:  # Readout from the arc.
            pretasks.append(self.helpers.boss.readout(self.command))

        self.command.info("Preparing lamps and reading pending exposures.")
        await asyncio.gather(*pretasks)

        # Now take the flat. Do not read it yet.
        flat_time = self.config["flat_time"]

        await self.helpers.boss.expose(
            self.command,
            flat_time,
            exp_type="flat",
            readout=True,
            read_async=True,
        )

        # We are done with lamps at this point.
        await self.helpers.lamps.all_off(self.command)

    async def fvc(self):
        """Run the FVC loop."""

        self.command.info("Halting the axes.")
        await self.helpers.tcc.axis_stop(self.command, axis="rot")

        await asyncio.sleep(3)

        self.command.info("Running FVC loop.")
        fvc_command = await self.send_command(
            "jaeger",
            "fvc loop",
            time_limit=config["timeouts"]["fvc"],
            raise_on_fail=False,
        )

        # fvc loop should never fail unless an uncaught exception.
        if fvc_command.status.did_fail:
            raise MacroError("FVC loop failed.")

    async def _set_guider_offset(self):
        """Sets the guider offset."""

        offset = self.config["guider_offset"]
        if offset is not None:
            offset = " ".join(map(str, offset))
            self.command.info(f"Setting guide offset to {offset}.")
            await self.send_command("cherno", f"offset {offset}")

    async def acquire(self):
        """Acquires the field."""

        self.command.info("Re-slewing to field.")
        await self.slew()

        if not self.helpers.tcc.check_axes_status("Tracking"):
            raise MacroError("Axes must be tracking for acquisition.")

        if not self.helpers.ffs.all_open():
            self.command.info("Opening FFS")
            await self.helpers.ffs.open(self.command)

        guider_time = self.config["guider_time"]

        self.command.info("Acquiring field.")
        await self.send_command(
            "cherno",
            f"acquire -t {guider_time} --full",
            time_limit=guider_time + 60.0,
        )

    async def guide(self):
        """Starts the guide loop."""

        if "acquire" not in self._flat_stages:
            self.command.info("Re-slewing to field.")
            await self.slew()

        if not self.helpers.tcc.check_axes_status("Tracking"):
            raise MacroError("Axes must be tracking for guiding.")

        if not self.helpers.ffs.all_open():
            self.command.info("Opening FFS")
            await self.helpers.ffs.open(self.command)

        guider_time = self.config["guider_time"]

        self.command.info("Starting guide loop.")

        with suppress(Exception):
            asyncio.shield(self.send_command("cherno", f"acquire -c -t {guider_time}"))

    async def cleanup(self):
        """Turns off all lamps."""

        if self._lamps_task is not None and not self._lamps_task.done():
            self._lamps_task.cancel()

        await self.helpers.lamps.all_off(self.command, force=True)

        # Read any pending BOSS exposure.
        if self.helpers.boss.readout_pending:
            await self.helpers.boss.readout(self.command)
