#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-12-20
# @Filename: lamps.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import time

from hal import HALCommandType, config
from hal.exceptions import HALError

from . import HALHelper


__all__ = ["LampsHelper"]


class LampsHelper(HALHelper):
    """Control for lamps."""

    LAMPS = ["ff", "HgCd", "Ne"]
    WARMUP = config["lamp_warmup"].copy()

    def _command_one(self, command: HALCommandType, lamp: str, state: bool):
        """Commands one lamp."""

        state_str = "on" if state is True else "off"

        return self._send_command(
            command,
            "mcp",
            f"{lamp.lower()}_{state_str}",
            time_limit=config["timeouts"]["lamps"],
        )

    async def all_off(
        self,
        command: HALCommandType,
        wait: bool = True,
        force: bool = False,
    ):
        """Turn off all the lamps."""

        tasks = []
        for lamp in self.LAMPS:
            tasks.append(self.turn_lamp(command, lamp, False, wait=wait, force=force))

        commands = asyncio.gather(*tasks)

        if wait:
            await commands

    def list_status(self) -> dict[str, tuple[bool, bool, float]]:
        """Returns a dictionary with the state of the lamps.

        For each lamp the first value in the returned tuple is whether the
        lamp has been commanded on. The second value is whether the lamps is
        actually on. The final value is how long since it changed states.

        """

        state = {}
        for lamp in self.LAMPS:
            commanded_key = f"{lamp}LampCommandedOn"
            commanded_on = self.actor.models["mcp"][commanded_key][0]
            if commanded_on is None:
                raise HALError(f"Failed getting {commanded_key}.")
            if lamp in ["wht", "UV"]:
                state[lamp] = (bool(commanded_on), bool(commanded_on), 0.0)
            else:
                lamp_key = f"{lamp}Lamp"
                lamp_state = self.actor.models["mcp"][lamp_key]
                if any([lv is None for lv in lamp_state]):
                    raise HALError(f"Failed getting {lamp_key}.")
                last_seen = lamp_state.last_seen
                if sum(lamp_state.value) == 4:
                    lamp_state = True
                elif sum(lamp_state.value) == 0:
                    lamp_state = False
                else:
                    raise HALError(f"Failed determining state for lamp {lamp}.")
                state[lamp] = (bool(commanded_on), lamp_state, time.time() - last_seen)

        return state

    async def turn_lamp(
        self,
        command: HALCommandType,
        lamps: str | list[str],
        state: bool,
        wait: bool = True,
        wait_for_warmup: bool = False,
        turn_off_others: bool = False,
        force: bool = False,
    ):
        """Turns a lamp on or off.

        Parameters
        ----------
        command
            The command that issues the lamp switching.
        lamp
            Name of the lamp(s) to turn on or off.
        wait
            Whether to wait until the MCP confirms the lamp has been commanded.
        wait_for_warmup
            Whether to block until the lamp has warmed up (if the lamp is
            being turned on).
        turn_off_others
            Turn off all other lamps.
        force
            If `True`, send the on/off command regardless of status.

        """

        if isinstance(lamps, str):
            lamps = [lamps]

        for lamp in lamps:
            if lamp not in self.LAMPS:
                raise HALError(f"Invalid lamp {lamp}.")

        current_status = self.list_status()

        tasks = []
        for ll in self.LAMPS:
            if ll in lamps:
                if force is False and current_status[ll][0] is state:
                    pass
                else:
                    tasks.append(self._command_one(command, ll, state))
            else:
                if turn_off_others is True:
                    if current_status[ll][0] is not False or force is True:
                        tasks.append(self._command_one(command, ll, False))

        await asyncio.gather(*tasks)

        if wait is False:
            await asyncio.sleep(1)
            return

        done_lamps: list[bool] = [False] * len(lamps)
        warmed: list[bool] = [False] * len(lamps)
        while True:

            if all(done_lamps):
                if state is False or wait_for_warmup is False:
                    return
                elif all(warmed):
                    return

            for i, lamp in enumerate(lamps):
                new_status = self.list_status()
                # Index 1 is if the lamp is actually on/off, not only commanded.
                if new_status[lamp][1] is state:
                    done_lamps[i] = True
                    if wait_for_warmup:
                        # Index 2 is the elapsed time since it was completely on/off.
                        elapsed = new_status[lamp][2]
                        if elapsed >= self.WARMUP[lamp]:
                            warmed[i] = True

            await asyncio.sleep(1)
