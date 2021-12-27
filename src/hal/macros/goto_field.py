#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: goto_field.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
from time import time

from hal import config
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["GotoFieldMacro"]


class GotoFieldMacro(Macro):
    """Go to field macro."""

    name = "goto_field"
    __STAGES__ = [
        "prepare",
        ("slew", "reconfigure"),
        "boss_hartmann",
        "fvc",
        "boss_arcs",
        "boss_flat",
        "acquire",
        "guide",
    ]
    __CLEANUP__ = ["cleanup"]

    async def prepare(self):
        """Check configuration and run pre-slew checks."""

        all_stages = list(self.stage_status.keys())

        if "reconfigure" in all_stages:

            configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
            last_seen = configuration_loaded.last_seen

            if last_seen is None:
                self.command.warning("The age of the loaded configuration is unknown.")
            elif time() - last_seen > 3600:  # One hour
                raise MacroError("Configuration is too old. Load a new configuration.")

        # Start closing the FFS if they are open but do not block.
        await self._close_ffs(wait=False)

        # If lamps are needed, turn them on now but do not wait for them to warm up.
        if "boss_hartmann" in self.stages or "boss_arcs" in self.stages:
            await self.helpers.lamps.turn_lamp(
                self.command,
                ["HgCd", "Ne"],
                True,
                turn_off_others=True,
            )
        elif "boss_flat" in self.stages:
            await self.helpers.lamps.turn_lamp(
                self.command,
                ["ff"],
                True,
                turn_off_others=True,
            )

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

        if self.actor.models["jaeger"]["folded"][0] is not True:
            self.command.warning("FPS is not folded. Unwinding.")
            await self.send_command("jaeger", "explode 5")
            await self.send_command("jaeger", "unwind")

        await self.send_command("jaeger", "configuration execute")

    async def boss_hartmann(self):
        """Takes the hartmann sequence."""

        self.command.info("Running hartmann collimate.")

        # First check that the FFS are closed and lamps on. We don't care for how long.
        await self._close_ffs()

        lamp_status = self.helpers.lamps.list_status()
        if lamp_status["Ne"][0] is not True or lamp_status["HgCd"][0] is not True:
            await self.helpers.lamps.turn_lamp(
                self.command,
                ["HgCd", "Ne"],
                True,
                turn_off_others=True,
                wait_for_warmup=False,
            )

        # Run hartmann and adjust the collimator but ignore residuals.
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

        self.command.info("Taking BOSS arc.")

        await self._close_ffs()

        # This won't wait if the lamps are already on and warmed up.
        self.command.debug("Waiting for lamps to warm up.")
        await self.helpers.lamps.turn_lamp(
            self.command,
            ["HgCd", "Ne"],
            True,
            turn_off_others=True,
            wait_for_warmup=True,
        )

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

        pretasks = [
            self.helpers.lamps.turn_lamp(
                self.command,
                ["ff"],
                True,
                turn_off_others=True,
                wait_for_warmup=True,
            )
        ]
        if self.helpers.boss.readout_pending:  # Readout from the arc.
            pretasks.append(self.helpers.boss.readout(self.command))

        self.command.debug("Preparing lamps and reading pending exposures.")
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
        await self.helpers.lamps.all_off(self.command, wait=False)

    async def fvc(self):
        """Run the FVC loop."""

        self.command.info("Halting the axes.")
        await self.helpers.tcc.axis_stop(self.command, axis="rot")

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

        # Check RMS to determine whether to continue or not.
        fvc_rms = self.actor.models["jaeger"]["fvc_rms"][0]
        if fvc_rms > self.config["fvc_rms_threshold"]:
            raise MacroError(f"FVC loop failed. RMS={fvc_rms}.")

        self.command.info("Re-slewing to field.")
        await self.slew()

    async def _set_guider_offset(self):
        """Sets the guider offset."""

        offset = self.config["guider_offset"]
        if offset is not None:
            offset = " ".join(map(str, offset))
            self.command.info(f"Setting guide offset to {offset}.")
            await self.send_command("cherno", f"offset {offset}")

    async def acquire(self):
        """Acquires the field."""

        if not self.helpers.tcc.check_axes_status("Tracking"):
            raise MacroError("Axes must be tracking for acquisition.")

        if not self.helpers.ffs.all_open():
            self.command.info("Opening FFS")
            await self.helpers.ffs.open(self.command)

        await self._set_guider_offset()

        guider_time = self.config["guider_time"]

        self.command.info("Acquiring field.")
        await self.send_command(
            "cherno",
            f"acquire -t {guider_time} --full",
            time_limit=guider_time + 60.0,
        )

    async def guide(self):
        """Starts the guide loop."""

        if not self.helpers.tcc.check_axes_status("Tracking"):
            raise MacroError("Axes must be tracking for guiding.")

        if not self.helpers.ffs.all_open():
            self.command.info("Opening FFS")
            await self.helpers.ffs.open(self.command)

        if "acquire" not in self.stage_status:
            await self._set_guider_offset()

        guider_time = self.config["guider_time"]

        self.command.info("Starting guide loop.")
        asyncio.create_task(self.send_command("cherno", f"acquire -c -t {guider_time}"))

    async def cleanup(self):
        """Turns off all lamps."""

        await self.helpers.lamps.all_off(self.command, wait=False, force=True)

        # Read any pending BOSS exposure.
        if self.helpers.boss.readout_pending:
            await self.helpers.boss.readout(self.command)
