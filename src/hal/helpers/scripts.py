#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-27
# @Filename: scripts.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import pathlib
from dataclasses import dataclass

from typing import TYPE_CHECKING

import hal


if TYPE_CHECKING:
    from clu import Command

    from hal.actor import HALActor


__all__ = ["Scripts"]


@dataclass
class Scripts:

    actor: HALActor
    path: pathlib.Path

    def __post_init__(self):

        self.path = pathlib.Path(self.path)
        if not self.path.is_absolute():
            self.path = pathlib.Path(hal.__file__).parent / self.path

        self.running: dict[str, asyncio.Task] = {}

    def list_scripts(self):
        """Returns a list of script names."""

        return [ff.name.replace(ff.suffix, "") for ff in self.path.glob("*.inp")]

    def get_steps(self, name: str) -> list[tuple[str, str, float | None]]:
        """Returns the list of steps of the script."""

        if name not in self.list_scripts():
            raise ValueError(f"Cannot find script {name}.")

        lines = (self.path / (name + ".inp")).read_text().splitlines()

        steps = []
        for line in lines:
            if line.strip().startswith("#"):
                continue
            parts = line.strip().split()
            try:
                timeout = float(parts[0])
                actor = parts[1]
                command_string = " ".join(parts[2:])

            except ValueError:
                actor = parts[0]
                command_string = " ".join(parts[1:])
                timeout = None
            steps.append((actor, command_string, timeout))

        return steps

    async def run(self, name: str, command: Command[HALActor] | None = None) -> bool:
        """Runs a script.

        This coroutine creates a task with all the steps to execute and adds it to
        the ``running`` dictionary. The execution can be cancelled by calling `.stop`,
        at which point the task will be cancelled and `.run` will handle the
        cancellation.

        """

        async def run_steps(steps):
            for n, step in enumerate(steps):
                actor, command_string, timeout = step

                if command:
                    step_message = f"{actor} {command_string}"
                    if timeout:
                        step_message = f"{timeout} {step_message}"
                    command.warning(text=f"Script {name}: {step_message}")

                await asyncio.wait_for(
                    self.actor.send_command(actor, command_string),
                    timeout,
                )
                if command:
                    command.debug(script_step=[name, command_string, n + 1, len(steps)])

        if name in self.running:
            raise RuntimeError(f"Script {name} is already running.")

        steps = self.get_steps(name)

        task = asyncio.create_task(run_steps(steps))
        self.running[name] = task

        # Now actually await the task, but be sure to handle cancellation.
        # If there is another kind of error (e.g. a timeout), raise it.
        try:
            await task
        except asyncio.CancelledError:
            return False
        except asyncio.TimeoutError:
            if command:
                command.error(error=f"Script {name}: one of the steps timedout out.")
            return False
        except Exception:
            raise
        finally:
            self.running.pop(name)

        return True

    async def cancel(self, name: str):
        """Cancels a running script."""

        if name not in self.running:
            raise RuntimeError(f"Script {name} is not running.")

        task = self.running[name]
        task.cancel()
