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

    LAMPS = ["ff", "wht", "UV", "HgCd", "Ne"]
    WARMUP = config["lamp_warmup"].copy()

    def _command_one(self, command: HALCommandType, lamp: str, state: bool):
        """Commands one lamp."""

        state_str = "on" if True else "off"

        return self._send_command(
            command,
            "mcp",
            f"{lamp.lower()}.{state_str}",
            time_limit=config["timeouts"]["lamps"],
        )

    async def all_off(self, command: HALCommandType, wait: bool = True):
        """Turn off all the lamps."""

        tasks = []
        for lamp in self.LAMPS:
            tasks.append(self._command_one(command, lamp, False))

        commands = asyncio.gather(*tasks)

        if wait:
            await commands

    def list_status(self) -> dict[str, tuple[bool, float]]:
        """Returns a dictionary with the state of the lamps.

        For each lamp the first value in the returned tuple is whether the
        lamp is on or off. The second value is how long since it changed
        states.

        """

        state = {}
        for lamp in self.LAMPS:
            if lamp in ["wht", "UV"]:
                lamp_state = self.actor.models["mcp"][f"{lamp}CommandedOn"][0]
                state[lamp] = (bool(lamp_state), 0.0)
            else:
                lamp_state = self.actor.models["mcp"][f"{lamp}Lamp"]
                last_seen = lamp_state.last_seen
                if sum(lamp_state.value) == 4:
                    lamp_state = True
                elif sum(lamp_state.value) == 0:
                    lamp_state = False
                else:
                    raise HALError(f"Failed determining state for lamp {lamp}.")
                state[lamp] = (lamp_state, time.time() - last_seen)

        return state

    async def turn_lamp(
        self,
        command: HALCommandType,
        lamps: str | list[str],
        state: bool,
        wait: bool = True,
        wait_for_warmup: bool = False,
        turn_off_others: bool = False,
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

        """

        if isinstance(lamps, str):
            lamps = [lamps]

        for lamp in lamps:
            if lamp not in self.LAMPS:
                raise HALError(f"Invalid lamp {lamp}.")

        current_status = self.list_status()
        changing: bool = False

        tasks = []
        for ll in self.LAMPS:
            if ll in lamps:
                if current_status[ll][0] is state:
                    pass
                else:
                    changing = True
                    tasks.append(self._command_one(command, ll, state))
            else:
                if turn_off_others is True and current_status[ll][0] is not False:
                    tasks.append(self._command_one(command, ll, False))

        if wait:
            await asyncio.gather(*tasks)

        if wait and wait_for_warmup and changing is True and state is True:
            for lamp in lamps:
                new_status = self.list_status()

                if new_status[lamp][0] is False:
                    wait_time = self.WARMUP[lamp]
                else:
                    elapsed = time.time() - new_status[lamp][1]
                    wait_time = self.WARMUP[lamp] - elapsed

                if wait_time > 0:
                    command.debug(
                        f"Waiting additional {round(wait_time, 1)} seconds for "
                        f"{lamp} to warm up."
                    )
                    await asyncio.sleep(wait_time)
