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
from hal.exceptions import HALError, MacroError
from hal.helpers.lamps import LampsHelper
from hal.macros import Macro


__all__ = ["GotoFieldMacro"]


class GotoFieldMacro(Macro):
    """Go to field macro."""

    name = "goto_field"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = [
        ("slew", "reconfigure"),
        "fvc",
        "reslew",
        "boss_flat",
        "boss_hartmann",
        "boss_arcs",
        "acquire",
        "guide",
    ]
    __CLEANUP__ = ["cleanup"]

    _lamps_task: asyncio.Task | None = None

    async def prepare(self):
        """Check configuration and run pre-slew checks."""

        self._lamps_task = None

        stages = self._flat_stages

        if "reconfigure" in stages:
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
        #       guider is running.
        await self.send_command("cherno", "stop")

        await self.helpers.tcc.axis_stop(self.command)

        # Ensure the APOGEE shutter is closed.
        await self.helpers.apogee.shutter(
            self.command,
            open=False,
            shutter="apogee",
        )

        do_fvc = "fvc" in stages
        do_flat = "boss_flat" in stages
        do_arcs = "boss_hartmann" in stages or "boss_arcs" in stages

        # If lamps are needed, turn them on now but do not wait for them to warm up.
        # Do not turn lamps if we are going to take an FVC image.
        if do_flat and not do_fvc:
            self._lamps_task = asyncio.create_task(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    ["ff"],
                    True,
                    turn_off_others=True,
                )
            )
        elif not do_flat and do_arcs:
            if do_fvc:
                lamps = ["HgCd"]
            else:
                lamps = ["HgCd", "Ne"]

            self._lamps_task = asyncio.create_task(
                self.helpers.lamps.turn_lamp(
                    self.command,
                    lamps,
                    True,
                    turn_off_others=True,
                )
            )
        else:
            await self._all_lamps_off()

    async def _close_ffs(self, wait: bool = True):
        """Closes the FFS."""

        if not self.helpers.ffs.all_closed():
            self.command.info("Closing FFS")
            task = self.helpers.ffs.close(self.command)

            if wait:
                await task
            else:
                asyncio.create_task(task)

    async def _all_lamps_off(self):
        """Turns all the lamps off after checking them."""

        # Check lamp status.
        command_off: bool = False
        lamp_status = self.helpers.lamps.list_status()
        for name, ls in lamp_status.items():
            if ls[1] is not False:
                self.command.warning(f"Lamp {name} is on, will turn off.")
                command_off = True

        if command_off:
            await self.helpers.lamps.all_off(self.command)

    async def slew(self):
        """Slew to field but keep the rotator at a fixed position."""

        configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
        ra, dec, pa = configuration_loaded[3:6]

        if any([ra is None, dec is None, pa is None]):
            raise MacroError("Unknown RA/Dec/PA coordinates for field.")

        result = self.actor.helpers.tcc.axes_are_clear()
        if not result:
            raise HALError("Some axes are not clear. Cannot continue.")

        # The fixed position at which to slew for the FVC loop.
        alt = self.config["fvc_alt"]
        az = self.config["fvc_az"]
        rot = self.config["fvc_rot"]

        if self.config["fixed_rot"] is False:
            self.command.info("Slewing to field RA/Dec/PA.")
            await self.actor.helpers.tcc.goto_position(
                self.command,
                {"ra": ra, "dec": dec, "rot": pa},
                rotwrap="nearest",
            )
        else:
            if self.config["fixed_altaz"]:
                self.command.info("Slewing to field with fixed rotator angle.")
                track_command = f"track {az}, {alt} mount /rota={rot} /rottype=mount"

            else:
                self.command.info("Slewing to field with fixed alt/az/rot position.")
                track_command = f"track {ra}, {dec} icrs /rota={rot} /rottype=mount"

            slew_result = await self.actor.helpers.tcc.do_slew(
                self.command,
                track_command=track_command,
            )

            if slew_result is False:
                raise HALError("Failed slewing to position.")

            self.command.info(text="Position reached.")

        self.command.info("Halting the rotator.")
        await self.helpers.tcc.axis_stop(self.command, axis="rot")

    async def reslew(self):
        """Re-slew to field."""

        configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
        ra, dec, pa = configuration_loaded[3:6]

        if any([ra is None, dec is None, pa is None]):
            raise MacroError("Unknown RA/Dec/PA coordinates for field.")

        self.command.info("Re-slewing to field.")

        await self.actor.helpers.tcc.goto_position(
            self.command,
            {"ra": ra, "dec": dec, "rot": pa},
            rotwrap="nearest",
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

        # Check lamps. Depending on the other stages HgCd may be on but Ne not. Loop
        # over each on of the lamps and if it's not on, turn it on. If any of them is
        # not on wait for 10 seconds, which is enough for the Hartmanns.
        lamp_status = self.helpers.lamps.list_status()

        wait: int = 0
        for lamp in ["HgCd", "Ne"]:
            if lamp_status[lamp][0] is False:
                self.command.warning(f"Turning {lamp} on.")
                asyncio.create_task(
                    self.helpers.lamps.turn_lamp(
                        self.command,
                        [lamp],
                        True,
                        turn_off_others=False,
                    )
                )

                if lamp == "HgCd":
                    wait = 10 if wait < 10 else wait
                else:
                    wait = 5 if wait < 5 else wait

        if wait > 0:
            self.command.info(f"Waiting {wait} seconds for the lamps to warm-up.")
            await asyncio.sleep(wait)

        if self.helpers.boss.readout_pending:  # Potential readout from the flat.
            await self.helpers.boss.readout(self.command)

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

        if "boss_arcs" not in self._flat_stages:
            await self._all_lamps_off()

    async def boss_arcs(self):
        """Takes BOSS arcs."""

        await self._close_ffs()

        # Check lamps. Depending on the other stages HgCd may be on. Loop over each
        # lamp and make sure they are turned on. If they are on but not fully warmed,
        # wait until they are.
        lamp_status = self.helpers.lamps.list_status()

        wait: float = 0.0
        for lamp in ["HgCd", "Ne"]:
            if lamp_status[lamp][0] is False:
                self.command.warning(f"Turning {lamp} on.")
                asyncio.create_task(
                    self.helpers.lamps.turn_lamp(
                        self.command,
                        [lamp],
                        True,
                        turn_off_others=False,
                    )
                )
                if LampsHelper.WARMUP[lamp] > wait:
                    wait = LampsHelper.WARMUP[lamp]
            elif lamp_status[lamp][3] is False:
                elapsed = lamp_status[lamp][2]
                wait_lamp = LampsHelper.WARMUP["HgCd"] - elapsed
                if wait < wait_lamp:
                    wait = wait_lamp

        if wait > 0:
            self.command.info(f"Waiting {wait} seconds for the lamps to warm-up.")
            await asyncio.sleep(wait)

        if self.helpers.boss.readout_pending:
            self.command.info("Waiting for BOSS to read out.")
            await self.helpers.boss.readout(self.command)

        self.command.info("Taking BOSS arc.")

        arc_time = self.config["arc_time"]

        await self.helpers.boss.expose(
            self.command,
            arc_time,
            exp_type="arc",
            readout=True,
            read_async=True,
        )

        await self._all_lamps_off()

    async def boss_flat(self):
        """Takes the BOSS flat."""

        self.command.info("Taking BOSS flat.")

        await self._close_ffs()

        lamp_status = self.helpers.lamps.list_status()
        if lamp_status["ff"][3] is False:
            if self._lamps_task and not self._lamps_task.done():
                # Lamps have been commanded on but are not warmed up yet.
                await self._lamps_task
            else:
                self.command.debug("Preparing FF lamps.")
                await self.helpers.lamps.turn_lamp(
                    self.command,
                    ["ff"],
                    True,
                    turn_off_others=True,
                )

        # Now take the flat. Do not read it yet.
        flat_time = self.config["flat_time"]

        self.command.debug("Starting BOSS flat exposure.")

        await self.helpers.boss.expose(
            self.command,
            flat_time,
            exp_type="flat",
            readout=True,
            read_async=True,
        )

        await self._all_lamps_off()

    async def fvc(self):
        """Run the FVC loop."""

        if "slew" in self._flat_stages:
            self.command.info("Halting the rotator.")
            await self.helpers.tcc.axis_stop(self.command, axis="rot")

        self.command.info("Running FVC loop.")
        fvc_command = await self.send_command(
            "jaeger",
            "fvc loop",
            time_limit=config["timeouts"]["fvc"],
            raise_on_fail=False,
        )

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

        pretasks = []

        if "reslew" not in self._flat_stages:
            self.command.info("Re-slewing to field.")
            pretasks.append(self.reslew())

        if not self.helpers.ffs.all_open():
            self.command.info("Opening FFS")
            pretasks.append(self.helpers.ffs.open(self.command))

        # Open FFS and re-slew at the same time.
        await asyncio.gather(*pretasks)

        # A bit of delay to make sure the axis status keyword is updated.
        await asyncio.sleep(1)

        if not self.helpers.tcc.check_axes_status("Tracking"):
            raise MacroError("Axes must be tracking for acquisition.")

        guider_time = self.config["guider_time"]
        n_acquisition = self.config["n_acquisition"]

        self.command.info("Acquiring field.")
        await self.send_command(
            "cherno",
            f"acquire -t {guider_time} --count {n_acquisition} --full",
        )

    async def guide(self):
        """Starts the guide loop."""

        if "acquire" not in self._flat_stages:
            self.command.info("Re-slewing to field.")
            await self.reslew()

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
