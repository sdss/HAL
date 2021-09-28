#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-26
# @Filename: tcc.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING


if TYPE_CHECKING:

    from clu import Command

    from hal.actor import HALActor


__all__ = ["TCC"]


@dataclass
class TCC:

    actor: HALActor
    is_slewing: bool = False

    async def goto_position(
        self,
        command: Command[HALActor],
        where: str | dict[str, float],
    ):
        """Executes the goto command.

        Parameters
        ----------
        command
            The actor command.
        where
            The name of the goto entry in the configuration file, or a tuple with the
            ``(alt, az, rot)`` in degrees.

        """

        assert command.actor

        config = command.actor.config

        if isinstance(where, str):
            if where not in config["goto"]:
                return command.fail(error=f"Cannot find goto position '{where}'.")
            alt = config["goto"][where]["alt"]
            az = config["goto"][where]["az"]
            rot = config["goto"][where]["rot"]
            where = {"alt": alt, "az": az, "rot": rot}

        if self.is_slewing:
            return command.fail(error="TCC is already slewing.")

        result = await self.axis_init(command)
        if result is False:
            return command.fail()

        # Even if this is already checked in axis_init(), let's check again that the
        # axes are ok, but if alt < limit, we only check az and alt because we won't
        # move in altitude.
        result = self.axes_are_clear()
        if not result:
            return command.fail(error="Some axes are not clear. Cannot continue.")

        # Now do the actual slewing.
        slew_result = await self.do_slew(command, where)
        axis_stop_result = await self.axis_stop(command)
        if slew_result is False or axis_stop_result is False:
            return command.fail(error=f"Failed going to position {where}.")

        return command.finish(text=f"At position {where}.")

    async def axis_init(self, command: Command[HALActor]) -> bool:
        """Executes TCC axis init or fails."""

        status = await self.actor.send_command("tcc", "axis status")
        if status.status.did_fail:
            command.error(error="'tcc status' failed. Is the TCC connected?")
            return False

        if self.check_stop_in() is True:
            command.error(
                error="Cannot tcc axis init because of bad axis status: "
                "Check stop buttons on Interlocks panel."
            )
            return False

        sem = await self.mcp_semaphore_ok(command)
        if sem is False:
            command.error(error="Failed getting the semaphore information.")
            return False

        if sem == "TCC:0:0" and self.axes_are_clear():
            command.info(
                text="Axes clear and TCC has semaphore. "
                "No axis init needed, so none sent."
            )
            return True

        command.info(text="Sending tcc axis init.")
        axis_init_cmd_str = "axis init"
        if self.below_alt_limit():
            command.warning(
                text="Altitude below interlock limit! Only initializing altitude "
                "and rotator: cannot move in az."
            )
            axis_init_cmd_str += " rot,alt"
        axis_init_cmd = await self.actor.send_command("tcc", axis_init_cmd_str)

        if axis_init_cmd.status.did_fail:
            command.error(error="Cannot slew telescope: failed tcc axis init.")
            command.error(error="Cannot slew telescope: check and clear interlocks?")
            return False

        return True

    async def axis_stop(self, command: Command[HALActor]) -> bool:
        """Issues an axis stop to the TCC."""

        axis_stop_cmd = await self.actor.send_command("tcc", "axis stop")

        if axis_stop_cmd.status.did_fail:
            command.error(
                error="Error: failed to cleanly stop telescope via tcc axis stop."
            )
            return False

        self.is_slewing = False
        return True

    def get_bad_axis_bits(self, axes=("az", "alt", "rot"), mask=None):
        """Return the bad status bits for the requested axes."""

        if mask is None:
            mask = self.actor.models["tcc"]["axisBadStatusMask"][0]

        return [(self.actor.models["tcc"][f"{axis}Stat"][3] & mask) for axis in axes]

    def check_stop_in(self, axes=("az", "alt", "rot")) -> bool:
        """Returns `True` if any stop bit is set in the ``<axis>Stat`` TCC keywords.

        The [az,alt,rot]Stat[3] bits show the exact status:
        http://www.apo.nmsu.edu/Telescopes/HardwareControllers/AxisControllers.html#25mStatusBits

        """
        try:
            # 0x2000 is "stop button in"
            return any(self.get_bad_axis_bits(axes=axes, mask=0x2000))
        except TypeError:
            # Some axisStat is unknown (and thus None)
            return False

    async def mcp_semaphore_ok(self, command: Command[HALActor]):
        """Returns the semaphore if the semaphore is owned by the TCC or nobody."""

        mcp_model = self.actor.models["mcp"]

        sem = mcp_model["semaphoreOwner"]
        if sem is None:
            sem_show_cmd = await self.actor.send_command("mcp", "sem.show")

            if sem_show_cmd.status.did_fail:
                command.error(error="Cannot get mcp semaphore. Is the MCP alive?")
                return False
            sem = mcp_model["semaphoreOwner"]

        if (
            (sem[0] != "TCC:0:0")
            and (sem[0] != "")
            and (sem[0] != "None")
            and (sem[0] is not None)
        ):
            command.error(
                error=f"Cannot axis init: Semaphore is owned by  {sem[0]}. "
                "If you are the owner (e.g., via MCP Menu), release it and try again. "
                "If you are not the owner, confirm that you can steal "
                "it from them, then issue: mcp sem.steal"
            )
            return False

        return sem

    def axes_are_clear(self, axes=("az", "alt", "rot")) -> bool:
        """Checks that no bits are set in any axis status field."""

        axes = [ax for ax in axes if ax != "alt" or self.below_alt_limit() is False]
        try:
            tcc_model = self.actor.models["tcc"]
            return all((tcc_model[f"{axis}Stat"][3] == 0) for axis in axes)
        except TypeError:
            # Some axisStat is unknown (and thus None)
            return False

    def below_alt_limit(self) -> bool:
        """Check if we are below the alt=18 limit that prevents init/motion in az."""

        limit = self.actor.config["goto"]["alt_limit"]
        return self.actor.models["tcc"]["axePos"][1] < limit

    async def do_slew(
        self,
        command,
        coords: dict[str, float],
        keep_offsets=False,
        offset=False,
    ) -> bool:
        """Correctly handle a slew command, given what parse_args had received."""

        tcc_model = self.actor.models["tcc"]

        # NOTE: TBD: We should limit which offsets are kept.
        keep_args = "/keep=(obj,arc,gcorr,calib,bore)" if keep_offsets else ""

        slew_cmd = None
        if not offset:

            if "ra" in coords and "dec" in coords and "rot" in coords:
                ra = coords["ra"]
                dec = coords["dec"]
                rot = coords["rot"]

                command.info(
                    text="Slewing to (ra, dec, rot) == "
                    f"({ra:.4f}, {dec:.4f}, {rot:g})"
                )
                if keep_args:
                    command.warning(text="keeping all offsets")

                slew_cmd = self.actor.send_command(
                    "tcc",
                    f"track {ra}, {dec} icrs /rottype=object/rotang={rot:g}"
                    f"/rotwrap=mid {keep_args}",
                )

            elif "az" in coords and "alt" in coords and "rot" in coords:
                alt = coords["alt"]
                az = coords["az"]
                rot = coords["rot"]

                command.info(
                    text="Slewing to (az, alt, rot) == "
                    f"({az:.4f}, {alt:.4f}, {rot:.4f})"
                )

                slew_cmd = self.actor.send_command(
                    "tcc", f"track {az:f}, {alt:f} mount/rottype=mount/rotangle={rot:f}"
                )

            else:

                command.error(error="Not enough coordinates information provided.")
                return False

        else:

            if "alt" not in coords or "az" not in coords:
                command.error(error="Not alt/az offsets provided.")
                return False

            # In arcsec
            alt = coords["alt"] or 0.0
            az = coords["az"] or 0.0
            rot = coords["rot"] or 0.0

            command.info(text=f"Offseting alt={alt:.3f}, az={az:.3f}")

            slew_cmd = self.actor.send_command(
                "tcc",
                f"offset guide {az/3600.:g},{alt/3600.:g},{rot/3600.:g} /computed",
            )

        # "tcc track" in the new TCC is only Done successfully when all requested
        # axes are in the "tracking" state. All other conditions mean the command
        # failed, and the appropriate axisCmdState and axisErrCode will be set.
        # However, if an axis becomes bad during the slew, the TCC will try to
        # finish it anyway, so we need to explicitly check for bad bits.

        self.is_slewing = True
        await slew_cmd

        if slew_cmd.status.did_fail:
            str_axis_state = ",".join(tcc_model["axisCmdState"].value)
            str_axis_code = ",".join(tcc_model["axisErrCode"].value)
            command.error(
                error=f"tcc track command failed with axis states: {str_axis_state} "
                f"and error codes: {str_axis_code}"
            )
            command.error(
                error="Failed to complete slew: see TCC messages for details."
            )
            return False

        if self.axes_are_clear() is False:
            axis_bits = self.get_bad_axis_bits()
            command.error(
                error="TCC slew command ended with some bad bits set: "
                "0x{:x},0x{:x},0x{:x}".format(*axis_bits)
            )
            command.error(
                error="Failed to complete slew: see TCC messages for details."
            )
            return False

        self.is_slewing = False
        return True
