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

    name = "lamps"

    def _command_one(self, command: HALCommandType, lamp: str, state: bool):
        """Commands one lamp."""

        state_str = "on" if state is True else "off"

        return self._send_command(
            command,
            "mcp",
            f"{lamp.lower()}_{state_str}",
            time_limit=config["timeouts"]["lamps"],
        )

    async def all_off(self, command: HALCommandType, force: bool = False):
        """Turn off all the lamps."""

        status = self.list_status()

        tasks = []
        for lamp in self.LAMPS:
            if force is False and status[lamp][0] is False and status[lamp][-1] is True:
                continue
            tasks.append(self.turn_lamp(command, lamp, False, force=force))

        await asyncio.gather(*tasks)

    def list_status(self) -> dict[str, tuple[bool, bool, float, bool]]:
        """Returns a dictionary with the state of the lamps.

        For each lamp the first value in the returned tuple is whether the
        lamp has been commanded on. The second value is whether the lamps is
        actually on. The third value is how long since it changed states.
        The final value indicates whether the lamp has warmed up.

        """

        state = {}
        for lamp in self.LAMPS:
            commanded_key = f"{lamp}LampCommandedOn"
            commanded_on = self.actor.models["mcp"][commanded_key][0]
            if commanded_on is None:
                raise HALError(f"Failed getting {commanded_key}.")
            if lamp in ["wht", "UV"]:
                is_on = bool(commanded_on)
                state[lamp] = (is_on, is_on, 0.0, is_on)
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

                elapsed = time.time() - last_seen
                warmed = (elapsed >= self.WARMUP[lamp]) if bool(commanded_on) else False
                state[lamp] = (bool(commanded_on), lamp_state, elapsed, warmed)

        return state

    async def turn_lamp(
        self,
        command: HALCommandType,
        lamps: str | list[str],
        state: bool,
        turn_off_others: bool = False,
        force: bool = False,
    ):
        """Turns a lamp on or off.

        This routine always blocks until the lamps are on and warmed up. If
        you don't want to block, call it as a task.

        Parameters
        ----------
        command
            The command that issues the lamp switching.
        lamp
            Name of the lamp(s) to turn on or off.
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

        status = self.list_status()

        tasks = []
        turn_off_tasks = []
        for ll in self.LAMPS:
            if ll in lamps:
                if force is False and status[ll][0] is state and status[ll][-1] is True:
                    pass
                else:
                    tasks.append(self._command_one(command, ll, state))
            else:
                if turn_off_others is True:
                    if status[ll][0] is not False or force is True:
                        turn_off_tasks.append(self._command_one(command, ll, False))

        if len(turn_off_tasks) > 0:
            await asyncio.gather(*turn_off_tasks)

        await asyncio.gather(*tasks)

        done_lamps: list[bool] = [False] * len(lamps)
        warmed: list[bool] = [False] * len(lamps)

        n_iter = 0
        while True:

            if all(done_lamps):
                if state is False:
                    command.info(f"Lamp(s) {','.join(lamps)} are off.")
                    return
                elif all(warmed):
                    command.info(f"Lamp(s) {','.join(lamps)} are on and warmed up.")
                    return

            new_status = self.list_status()
            for i, lamp in enumerate(lamps):
                # Don't don't anything if we're already at the state.
                if done_lamps[i] and (state is False or warmed[i]):
                    continue

                # Index 1 is if the lamp is actually on/off, not only commanded.
                if new_status[lamp][1] is state:
                    done_lamps[i] = True

                if state is True:
                    # Index 2 is the elapsed time since it was completely on/off.
                    elapsed = new_status[lamp][2]
                    if elapsed >= self.WARMUP[lamp]:
                        command.debug(f"Lamp {lamp}: warm-up complete.")
                        warmed[i] = True
                    elif (n_iter % 5) == 0:
                        remaining = int(self.WARMUP[lamp] - elapsed)
                        command.debug(
                            f"Warming up lamp {lamp}: " f"{remaining} s remaining."
                        )

            await asyncio.sleep(1)
            n_iter += 1
