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

import numpy

from hal import config
from hal.exceptions import HALError, MacroError
from hal.helpers.lamps import LampsHelperAPO, LampsHelperLCO
from hal.macros import Macro


__all__ = ["GotoFieldAPOMacro"]


class _GotoFieldBaseMacro(Macro):
    """Go to field macro."""

    name = "goto_field"

    __PRECONDITIONS__ = ["prepare"]
    __STAGES__ = [
        ("slew", "reconfigure"),
        "fvc",
        ("reslew", "lamps"),
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

        stages = self.flat_stages

        if "reconfigure" in stages:
            configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
            last_seen = configuration_loaded.last_seen

            if last_seen is None:
                self.command.warning("The age of the loaded configuration is unknown.")
            elif time() - last_seen > 3600:  # One hour
                raise MacroError("Configuration is too old. Load a new configuration.")

        do_fvc = "fvc" in stages
        do_flat = "boss_flat" in stages
        do_arcs = "boss_hartmann" in stages or "boss_arcs" in stages

        # Stop the guider.
        # TODO: this will probably be different at LCO.
        if do_fvc or do_flat or do_arcs:
            if self.observatory == "APO":
                assert self.helpers.tcc

                await self.helpers.cherno.stop_guiding(self.command)
                await self.helpers.tcc.axis_stop(self.command)

            else:
                if "slew" in stages:
                    await self.helpers.cherno.stop_guiding(self.command)

        # Ensure the APOGEE shutter is closed but don't wait for it.
        asyncio.create_task(
            self.helpers.apogee.shutter(
                self.command,
                open=False,
                shutter="apogee",
            )
        )

        # Reset cherno offsets.
        self.command.debug("Resetting cherno offsets.")
        await self.helpers.cherno.reset_offsets(self.command)

        # Start closing the FFS if they are open but do not block. Only close the FFS
        # if we're going to do BOSS cals, otherwise it's about 20 seconds of lost time.
        if do_flat or do_arcs:
            await self._close_ffs(wait=False)

        # If lamps are needed, turn them on now but do not wait for them to warm up.
        # Do not turn lamps if we are going to take an FVC image. We add a delay
        # since the APOGEE shutter is closing and we don't want to start turning on
        # the lamps until it's fully closed.
        if self.observatory == "APO":
            if do_flat and not do_fvc:
                self._lamps_task = asyncio.create_task(
                    self.helpers.lamps.turn_lamp(
                        self.command,
                        ["ff"],
                        True,
                        turn_off_others=True,
                        delay=10,
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
                        delay=10,
                    )
                )
            else:
                await self._all_lamps_off(wait=False)

        else:
            await self._all_lamps_off(wait=False)

    async def slew(self):
        """Slew to field but keep the rotator at a fixed position."""

        raise NotImplementedError()

    async def reconfigure(self):
        """Reconfigures the FPS."""

        self.command.info("Reconfiguring FPS array.")

        # This is always safe. If it's already folded jaeger will return immediately.
        await self.send_command("jaeger", "configuration reverse")

        await self.send_command("jaeger", "configuration execute")

    async def fvc(self):
        """Run the FVC loop."""

        if "slew" in self.flat_stages and self.observatory == "APO":
            assert self.helpers.tcc

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

    async def reslew(self):
        """Re-slew to field."""

        raise NotImplementedError()

    async def lamps(self):
        """Ensures the correct lamps for calibrations are on."""

        cal_stages = ["boss_flat", "boss_hartmann", "boss_arcs"]
        if all([stage not in self.flat_stages for stage in cal_stages]):
            return

        # If we are going to take BOSS cals, start warming up lamps now (some may
        # already be on).
        if "boss_flat" in self.flat_stages:
            mode = "flat"
        elif "boss_hartmann" in self.flat_stages:
            mode = "hartmann"
        else:
            mode = "arcs"

        await self._ensure_lamps(mode)

    async def boss_flat(self):
        """Takes the BOSS flat."""

        self.command.info("Taking BOSS flat.")

        await self._ensure_lamps(mode="flat")

        # Now take the flat. Do not read it yet.
        flat_time = self.config["flat_time"][self.observatory]

        self.command.debug("Starting BOSS flat exposure.")

        await self.helpers.boss.expose(
            self.command,
            flat_time,
            exp_type="flat",
            readout=True,
            read_async=True,
        )

        ff_lamp = "ff" if self.observatory == "APO" else "TCS_FF"
        asyncio.create_task(self.helpers.lamps.turn_lamp(self.command, ff_lamp, False))

    async def boss_hartmann(self):
        """Takes the hartmann sequence."""

        await self._ensure_lamps(mode="hartmann")

        if self.helpers.boss.readout_pending:  # Potential readout from the flat.
            self.command.info("Waiting for BOSS to read out.")
            await self.helpers.boss.readout(self.command)

        # Run hartmann and adjust the collimator but ignore residuals.
        self.command.info("Running hartmann collimate.")

        if self.observatory == "APO":
            command_string = "collimate ignoreResiduals"
        else:
            command_string = "collimate --keep-lamps"

        await self.send_command(
            "hartmann",
            command_string,
            time_limit=config["timeouts"]["hartmann"],
        )

        # Now check if there are residuals that require modifying the blue ring.
        residuals_kw = "sp1Residuals" if self.observatory == "APO" else "sp2Residuals"
        residuals = self.actor.models["hartmann"][residuals_kw][2]
        if residuals != "OK":
            raise MacroError(
                "Please adjust the blue ring and run goto-field again. "
                "The collimator has been adjusted."
            )

        if "boss_arcs" not in self.flat_stages:
            await self._all_lamps_off(wait=False)

    async def boss_arcs(self):
        """Takes BOSS arcs."""

        await self._ensure_lamps(mode="arcs")

        if self.helpers.boss.readout_pending:
            self.command.info("Waiting for BOSS to read out.")
            await self.helpers.boss.readout(self.command)

        self.command.info("Taking BOSS arc.")

        arc_time = self.config["arc_time"][self.observatory]

        await self.helpers.boss.expose(
            self.command,
            arc_time,
            exp_type="arc",
            readout=True,
            read_async=True,
        )

        await self._all_lamps_off(wait=False)

    async def acquire(self):
        """Acquires the field."""

        if self.helpers.cherno.is_guiding():
            self.command.info("Already guiding.")
            return

        await self._guide_preconditions("acquire")

        acquisition_config = self.config["acquisition"][self.observatory]

        exposure_time = acquisition_config["exposure_time"]
        max_exposure_time = acquisition_config["max_exposure_time"]
        dynamic_exposure_time = acquisition_config["dynamic_exposure_time"]
        target_rms = acquisition_config["target_rms"]
        min_rms = acquisition_config["min_rms"]
        max_iterations = acquisition_config["max_iterations"]
        wait_time = acquisition_config["wait_time"]

        self.command.info("Acquiring field.")

        try:
            await self.helpers.cherno.acquire(
                self.command,
                exposure_time=exposure_time,
                max_exposure_time=max_exposure_time,
                dynamic_exposure_time=dynamic_exposure_time,
                target_rms=target_rms,
                max_iterations=max_iterations,
                wait_time=wait_time,
            )
        except HALError:
            # If we have exhausted the number of exposures and not reached
            # the target RMS, check if we reach the minimum RMS. If so, warn
            # but continue.
            if self.helpers.cherno.guiding_at_rms(min_rms, allow_not_guiding=True):
                self.command.warning(
                    f"Target RMS not reached but RMS < {min_rms} arcsec. "
                    "Will continue."
                )
            else:
                raise

    async def guide(self):
        """Starts the guide loop."""

        if self.helpers.cherno.is_guiding():
            self.command.info("Already guiding.")
            return

        await self._guide_preconditions("guide")

        guide_config = self.config["guide"][self.observatory]
        if self.config["guider_time"] is not None:
            exposure_time = self.config["guider_time"]
        else:
            exposure_time = guide_config["exposure_time"]

        self.command.info("Starting guide loop.")
        await self.helpers.cherno.guide(
            self.command,
            exposure_time=exposure_time,
            wait_time=guide_config["wait_time"],
            wait=False,
        )

    async def cleanup(self):
        """Turns off all lamps."""

        if self.observatory == "LCO":
            await asyncio.sleep(3)

        # If enough stages have run, mark this configuration as goto_complete.
        if self.helpers.jaeger.configuration is not None and self._is_goto_complete():
            self.helpers.jaeger.configuration.goto_complete = True

        if self._lamps_task is not None and not self._lamps_task.done():
            self._lamps_task.cancel()

        await self._all_lamps_off()

        # Read any pending BOSS exposure.
        if self.helpers.boss.readout_pending:
            await self.helpers.boss.readout(self.command)

    def _get_pointing(self):
        """Returns the configuration pointing."""

        configuration_loaded = self.actor.models["jaeger"]["configuration_loaded"]
        ra, dec, pa = configuration_loaded[3:6]

        if any([ra is None, dec is None, pa is None]):
            raise MacroError("Unknown RA/Dec/PA coordinates for field.")

        ra_off = self.config[f"slew_offsets.{self.observatory}.ra"]
        dec_off = self.config[f"slew_offsets.{self.observatory}.dec"]
        rot_off = self.config[f"slew_offsets.{self.observatory}.rot"]

        if ra_off is not None:
            ra += ra_off / numpy.cos(numpy.radians(dec))

        dec += dec_off or 0.0
        pa += rot_off or 0.0

        return ra, dec, pa

    async def _set_guider_offset(self):
        """Sets the guider offset."""

        offset = self.config["guider_offset"]
        if offset is not None:
            offset = " ".join(map(str, offset))
            self.command.info(f"Setting guide offset to {offset}.")
            await self.send_command("cherno", f"offset {offset}")

    def _is_goto_complete(self):
        """Determines whether we can mark the configuration as ``goto_complete```.

        The stage at which we mark the configuration as ``goto_complete`` depends
        on what stages we are running, but it is always after the last stage
        before acquisition.

        """

        for stage in self.flat_stages:
            if stage == "acquire" or stage == "guide":
                continue
            if not self.is_stage_done(stage):
                return False

        return True

    async def _close_ffs(self, wait: bool = True):
        """Closes the FFS."""

        pass

    async def _guide_preconditions(self, stage: str):
        """Tasks to be run before acquisition/guiding can start."""

        pass

    async def _all_lamps_off(self, wait: bool = True):
        """Turns all the lamps off after checking them."""

        raise NotImplementedError()

    async def _ensure_lamps(self, mode: str):
        """Ensures the lamps for flats/arcs/hartmann are on."""

        raise NotImplementedError()


class GotoFieldAPOMacro(_GotoFieldBaseMacro):
    """Goto field macro for APO."""

    observatory = "APO"

    async def slew(self):
        """Slew to field but keep the rotator at a fixed position."""

        assert self.helpers.tcc

        # Wait five seconds to give time for the axis stop we issued in Prepare to
        # take effect.
        await asyncio.sleep(5)

        ra, dec, pa = self._get_pointing()

        result = self.helpers.tcc.axes_are_clear()
        if not result:
            raise HALError("Some axes are not clear. Cannot continue.")

        # The fixed position at which to slew for the FVC loop.
        alt = self.config["fvc"]["alt"]
        az = self.config["fvc"]["az"]
        rot = self.config["fvc"]["rot"]
        keep_offsets = self.config["keep_offsets"]

        if self.config["fixed_rot"] is False:
            self.command.info("Slewing to field RA/Dec/PA.")
            await self.helpers.tcc.goto_position(
                self.command,
                {"ra": ra, "dec": dec, "rot": pa},
                rotwrap="middle",
                keep_offsets=keep_offsets,
            )
        else:
            if self.config["fixed_altaz"]:
                self.command.info("Slewing to field with fixed rotator angle.")
                track_command = f"track {az}, {alt} mount /rota={rot} /rottype=mount"

            else:
                self.command.info("Slewing to field with fixed alt/az/rot position.")
                track_command = f"track {ra}, {dec} icrs /rota={rot} /rottype=mount"

            slew_result = await self.helpers.tcc.do_slew(
                self.command,
                track_command=track_command,
                keep_offsets=keep_offsets,
            )

            if slew_result is False:
                raise HALError("Failed slewing to position.")

            self.command.info(text="Position reached.")

        self.command.info("Halting the rotator.")
        await self.helpers.tcc.axis_stop(self.command, axis="rot")

    async def reslew(self):
        """Re-slew to field."""

        assert self.helpers.tcc

        ra, dec, pa = self._get_pointing()

        self.command.info("Re-slewing to field.")

        # Start going to position asynchronously.
        await self.helpers.tcc.goto_position(
            self.command,
            {"ra": ra, "dec": dec, "rot": pa},
            rotwrap="nearest",
            keep_offsets=self.config["keep_offsets"],
        )

    async def _all_lamps_off(self, wait: bool = True):
        """Turns all the lamps off after checking them."""

        # Check lamp status.
        command_off: bool = False
        lamp_status = self.helpers.lamps.list_status()
        for name, ls in lamp_status.items():
            if ls[1] is not False:
                self.command.warning(f"Lamp {name} is on, will turn off.")
                command_off = True

        if command_off:
            task = asyncio.create_task(self.helpers.lamps.all_off(self.command))
            if wait:
                await task

    async def _ensure_lamps(self, mode: str):
        """Ensures the lamps for flats/arcs/hartmann are on."""

        assert isinstance(self.helpers.lamps, LampsHelperAPO)

        # Make sure FFS are closed.
        close_ffs = asyncio.create_task(self._close_ffs())

        # Check lamps. Depending on the other stages HgCd may be on but Ne not. Loop
        # over each on of the lamps and if it's not on, turn it on. If any of them is
        # not on wait for 10 seconds, which is enough for the Hartmanns.
        lamp_status = self.helpers.lamps.list_status()

        if mode == "flat":
            lamp_status = self.helpers.lamps.list_status()
            if lamp_status["ff"][3] is False:
                if self._lamps_task and not self._lamps_task.done():
                    # Lamps have been commanded on but are not warmed up yet.
                    await self._lamps_task
                else:
                    self.command.warning("Turning FF lamp on.")
                    await self.helpers.lamps.turn_lamp(
                        self.command,
                        ["ff"],
                        True,
                        turn_off_others=True,
                    )

        else:
            wait: float = 0
            for lamp in ["HgCd", "Ne"]:
                if lamp_status[lamp][0] is False:
                    self.command.warning(f"Turning {lamp} lamp on.")
                    asyncio.create_task(
                        self.helpers.lamps.turn_lamp(
                            self.command,
                            [lamp],
                            True,
                            turn_off_others=False,
                        )
                    )

                    # For hartmann we don't need to wait until the lamps have fully
                    # warmed up. For arcs we wait until they are.
                    if mode == "hartmann":
                        if lamp == "HgCd":
                            wait = 10 if wait < 10 else wait
                        else:
                            wait = 5 if wait < 5 else wait
                    else:
                        if LampsHelperAPO.WARMUP[lamp] > wait:
                            wait = LampsHelperAPO.WARMUP[lamp]

                elif mode == "arcs" and lamp_status[lamp][3] is False:
                    elapsed = lamp_status[lamp][2]
                    wait_lamp = LampsHelperAPO.WARMUP[lamp] - elapsed
                    if wait < wait_lamp:
                        wait = wait_lamp

            if wait > 0:
                # TODO: maybe here we should confirm that the lamps are turning on.
                # We don't want to await the tasks though, because in some cases we
                # are waiting less time than the full warm up time.
                self.command.info(f"Waiting {wait} seconds for the lamps to warm-up.")
                await asyncio.sleep(wait)

        # Ensure FFS have fully closed.
        await close_ffs

    async def _close_ffs(self, wait: bool = True):
        """Closes the FFS."""

        assert self.helpers.ffs

        if not self.helpers.ffs.all_closed():
            self.command.info("Closing FFS")
            task = self.helpers.ffs.close(self.command)

            if wait:
                await task
            else:
                asyncio.create_task(task)

    async def _guide_preconditions(self, stage: str):
        """Run guide preconditions."""

        assert self.helpers.ffs and self.helpers.tcc

        pretasks = []

        if (stage == "acquire" and "reslew" not in self.flat_stages) or (
            stage == "guide" and "acquire" not in self.flat_stages
        ):
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


class GotoFieldLCOMacro(_GotoFieldBaseMacro):  # pragma: no cover
    """Goto field macro for LCO."""

    observatory = "LCO"

    def __init__(self):
        super().__init__()

        self.screen_on: bool = False

    def _reset_internal(self, **opts):
        self.screen_on = False

        return super()._reset_internal(**opts)

    async def slew(self):
        """Slews the telescope."""

        do_flat = "boss_flat" in self.flat_stages
        do_arcs = "boss_hartmann" in self.flat_stages or "boss_arcs" in self.flat_stages
        do_screen = True if do_flat or do_arcs else False

        await self._slew_telescope(screen=do_screen)

    async def reslew(self):
        """Reslew to position after the FVC stage."""

        # No need for this at LCO.
        return

    async def _all_lamps_off(self, wait: bool = True):
        """Turns all the lamps off."""

        task = asyncio.create_task(self.helpers.lamps.all_off(self.command))
        if wait:
            await task

    async def _ensure_lamps(self, mode: str):
        """Makes sure the lamps are configured properly."""

        assert isinstance(self.helpers.lamps, LampsHelperLCO)

        if self._lamps_task and not self._lamps_task.done():
            # Lamps have been commanded on but are not warmed up yet.
            await self._lamps_task

        if mode == "flat":
            await self.helpers.lamps.turn_lamp(
                self.command,
                ["TCS_FF"],
                True,
                turn_off_others=True,
            )

        else:
            await self.helpers.lamps.turn_lamp(
                self.command,
                ["HeAr", "Ne"],
                True,
                turn_off_others=True,
            )

    async def _slew_telescope(self, screen: bool = False):
        """Slews the du Pont telescope."""

        ra, dec, pa = self._get_pointing()

        command_string = f"target {ra}, {dec} /posAngle={pa:.3f}"
        if screen:
            command_string += " /screen"

        self.command.info("Slewing to field RA/Dec/PA.")

        # The command times out when it gets there, so for now we ignore the failure.
        await self.send_command("lcotcc", command_string, raise_on_fail=False)

        self.screen_on = screen

    async def _remove_screen(self):
        """Ensures the screen is not in front of the telescope."""

        if self.screen_on:
            await self._slew_telescope(False)

    async def _guide_preconditions(self, stage: str):
        """Ensure the system is ready to guide/acquire."""

        await self._remove_screen()

    async def _close_ffs(self, wait: bool = True):
        return True
