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
from hal.actor import HALCommandType
from hal.exceptions import MacroError
from hal.macros import Macro


__all__ = ["GotoFieldMacro"]


class GotoFieldMacro(Macro[HALCommandType]):
    """Go to field macro."""

    name = "goto_field"
    __STAGES__ = [
        "prepare",
        ("slew", "reconfigure"),
        "boss_hartmann",
        "boss_arcs",
        "boss_flat",
        "fvc",
        "acquire",
        "guide",
    ]
    __CLEANUP__ = ["cleanup"]

    async def prepare(self):
        """Check configuration and run pre-slew checks."""

        all_stages = list(self.stage_status.keys())

        if "reconfigure" not in all_stages:
            return

        loaded_configuration = self.actor.models["jaeger"]["loaded_configuration"]
        if time() - loaded_configuration.last_seen > 3600:  # One hour
            raise MacroError("Configuration is too old. Load a new configuration.")

        # Start closing the FFS if they are open but do not block.
        await self._close_ffs(wait=False)

        # If lamps are needed, turn them on now but do not wait for them.
        if "boss_hartmann" in self.stages or "boss_arcs" in self.stages:
            asyncio.create_task(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    ["HgCd", "Ne"],
                    True,
                    turn_off_others=True,
                    wait_for_warmup=True,
                )
            )
        elif "boss_flat" in self.stages:
            asyncio.create_task(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    ["ff"],
                    True,
                    turn_off_others=True,
                    wait_for_warmup=True,
                )
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

        loaded_configuration = self.actor.models["jaeger"]["loaded_configuration"]
        ra, dec, pa = loaded_configuration[3:6]

        await self.helpers.tcc.goto_position(
            self.command,
            where={"ra": ra, "dec": dec, "rot": pa},
        )

    async def reconfigure(self):
        """Reconfigures the FPS."""

        self.command.info("Reconfiguring FPS array.")
        await self.send_command("jaeger", "configuration execute")

    async def boss_hartmann(self):
        """Takes the hartmann sequence."""

        # First check that the FFS are closed and lamps on. We don't care for how long.
        await self._close_ffs()

        lamp_status = self.helpers.lamps.list_status()
        if lamp_status["Ne"][0] is not True or lamp_status["HgCd"][0] is not True:
            raise MacroError(
                "Lamps are not on. Run the prepare stage or turn them on manually."
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

        await self._close_ffs()

        # This won't wait if the lamps are already on and warmed up.
        await self.helpers.lamps.turn_lamp(
            self.command,
            ["HgCd", "Ne"],
            True,
            turn_off_others=True,
            wait_for_warmup=True,
        )

        arc_time = config["macros"][self.name]["arc_time"]

        await self.helpers.boss.expose(
            self.command,
            arc_time,
            exp_type="arc",
            readout=False,
        )

    async def boss_flat(self):
        """Takes the BOSS flat."""

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

        self.command.info("Preparing lamps and reading BOSS exposures.")
        await asyncio.gather(*pretasks)

        # Now take the flat. Do not read it yet.
        flat_time = config["macros"][self.name]["flat_time"]

        await self.helpers.boss.expose(
            self.command,
            flat_time,
            exp_type="flat",
            readout=False,
        )

    async def fvc(self):
        """Run the FVC loop."""

        self.command.info("Halting the axes.")
        await self.helpers.tcc.axis_stop(self.command)

        fvc_command = await self.send_command(
            "jaeger",
            "fvc loop",
            time_limit=config["timeouts"]["fvc"],
            raise_on_fail=False,
        )
        if fvc_command.status.did_fail:
            fvc_rms = self.actor.models["jaeger"]["fvc_rms"][0]
            if fvc_rms <= 10.0:
                self.command.warning("FVC loop failed but RMS < 10 microns.")
            else:
                raise MacroError(f"FVC loop failed. RMS={fvc_rms}.")

        self.command.info("Re-slewing to field.")
        await self.slew()

    async def acquire(self):
        """Acquires the field."""

        if config["macros"][self.name]["offset"] is not None:
            offset = " ".join(config["macros"][self.name]["offset"])
            self.command.info("Setting guide offset.")
            await self.send_command("cherno", f"offset {offset}")

        guider_time = config["macros"][self.name]["guider_time"]

        self.command.info("Acquiring field.")
        await self.send_command(
            "cherno",
            f"acquire -t {guider_time} --full",
            time_limit=guider_time + 60.0,
        )

    async def guide(self):
        """Starts the guide loop."""

        offset = config["macros"][self.name]["offset"]
        if offset is not None and "acquire" not in self.stages:
            offset = " ".join(offset)
            self.command.info("Setting guide offset.")
            await self.send_command("cherno", f"offset {offset}")

        guider_time = config["macros"][self.name]["guider_time"]

        self.command.info("Starting guide loop.")
        asyncio.create_task(self.send_command("cherno", f"acquire -c -t {guider_time}"))

    async def cleanup(self):
        """Turns off all lamps."""

        await self.helpers.lamps.all_off(self.command, wait=True)

        # Read any pending BOSS exposure.
        if self.helpers.boss.readout_pending:
            await self.helpers.boss.readout(self.command)
