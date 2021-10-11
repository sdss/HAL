#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: base.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import enum
import warnings
from contextlib import suppress
from functools import partial

from typing import TYPE_CHECKING, Callable, Coroutine, Optional, Union

from hal.exceptions import HALError, HALUserWarning


if TYPE_CHECKING:
    from clu import Command

    from hal import HALActor


__all__ = ["Macro"]


StageType = Union[str, tuple[str, ...], list[str]]


class StageStatus(enum.Flag):
    """Stage status codes."""

    WAITING = enum.auto()
    ACTIVE = enum.auto()
    CANCELLED = enum.auto()
    CANCELLING = enum.auto()
    FINISHED = enum.auto()
    FAILED = enum.auto()


def flatten_stages(stages: list[StageType]) -> list[str]:
    flat = []
    for stage in stages:
        if isinstance(stage, str):
            flat.append(stage)
        else:
            flat += list(stage)
    return flat


class Macro:
    """A base macro class that offers concurrency and cancellation."""

    name: str
    __STAGES__: list[StageType]

    def __init__(
        self,
        name: Optional[str] = None,
        stages: Optional[list[StageType]] = None,
        stage_params: dict = {},
        external_stages: dict[str, Callable[..., Coroutine]] = {},
    ):

        if name is None and not hasattr(self, "name"):
            raise HALError("The macro does not have a name attribute.")
        self.name = name or self.name

        # Stages to actually run (may skip some from __STAGES__)
        if stages is None and not hasattr(self, "__STAGES__"):
            raise HALError("The macro does not have a __STAGES__ attribute.")
        self.stages = stages or self.__STAGES__

        self.stage_status: dict[str, StageStatus] = {}

        self._stage_params = stage_params
        self._external_stages = external_stages

        self.running = False

        self._preconditions_task: asyncio.Task | None = None
        self._running_task: asyncio.Task | None = None

        self.command: Command[HALActor]  # Will be set in reset()

        self.reset(self.stages)

    def __repr__(self):
        stages = flatten_stages(self.stages)
        return f"<{self.__class__.__name__} (name={self.name}, stages={stages})>"

    def reset(
        self,
        stages: Optional[list[StageType]] = None,
        command: Optional[Command[HALActor]] = None,
    ):
        """Resets stage status."""

        if stages is None:
            stages = self.__STAGES__.copy()
        else:
            stages = stages.copy()

        if len(stages) == 0:
            raise HALError("No stages found.")

        self.stages = stages
        self.stage_status = {st: StageStatus.WAITING for st in flatten_stages(stages)}

        for st in self.stage_status:
            if getattr(self, st, None) is None:
                if st not in self._external_stages:
                    raise HALError(f"Cannot find method for stage {st!r}.")

        self.running = False
        self._preconditions_task = None
        self._running_task = None

        if command:
            self.command = command
            self.list_stages()

    def set_stage_status(
        self,
        stages: StageType,
        status: StageStatus,
    ):
        """Set the stage status and inform the actor."""

        if isinstance(stages, str):
            stages = (stages,)

        for stage in stages:
            if stage not in self.stage_status:
                warnings.warn(
                    "Cannot find stage {stage} in list. "
                    "Maybe the macro was not reset correctly.",
                    HALUserWarning,
                )
                return

            self.stage_status[stage] = status

        self.output_stage_status()

    def output_stage_status(
        self,
        command: Optional[Command[HALActor]] = None,
        level: str = "d",
    ):
        """Outputs the stage status to the actor."""

        command = command or self.command
        if not command:
            warnings.warn(
                "Cannot write to clients in output_stage_status(). Command not set.",
                HALUserWarning,
            )
            return

        status_keyw = [self.name]
        for stage in self.stage_status:
            status_name = self.stage_status[stage].name
            assert status_name
            status_keyw += [stage, status_name.lower()]

        command.write(level, stage_status=status_keyw)

    def list_stages(
        self, command: Optional[Command[HALActor]] = None, level: str = "i"
    ):
        """Outputs stages to the actor."""

        command = command or self.command
        if not command:
            warnings.warn(
                "Cannot write to clients in list_stages(). Command not set.",
                HALUserWarning,
            )
            return

        command.write(
            level,
            stages=[self.name] + [st for st in flatten_stages(self.stages)],
        )
        command.write(
            level,
            all_stages=[self.name] + [st for st in flatten_stages(self.__STAGES__)],
        )

    def fail_macro(
        self,
        error: Exception,
        stage: Optional[StageType] = None,
    ):
        """Fails the macros and informs the actor."""

        if self.command:
            self.command.error(error=f"Macro {self.name} failed unexpectedly.")
            self.command.error(error=error)
        else:
            warnings.warn(
                "Cannot write to clients in fail_macro(). Command not set.",
                HALUserWarning,
            )

        if stage is None:
            stage = list(self.stage_status.keys())
        else:
            if not isinstance(stage, (list, tuple)):
                stage = [stage]

        for ss in stage:
            if self.stage_status[ss] == StageStatus.ACTIVE:
                self.stage_status[ss] = StageStatus.FAILED

        self.output_stage_status()
        self.running = False

    async def run(self):
        """Executes the macro allowing for cancellation."""

        if self.running:
            raise HALError("This macro is already running.")

        if self.command is None:
            raise HALError("Cannot start a macro without an active command.")

        self.running = True
        self._preconditions_task = asyncio.create_task(self.preconditions())
        self._running_task = asyncio.create_task(self._do_run())

        try:
            await self._running_task
        except asyncio.CancelledError:
            with suppress(asyncio.CancelledError):
                self._running_task.cancel()
                await self._running_task
        except Exception as err:
            self.fail_macro(err)

        self.running = False

        return StageStatus.FAILED not in self.stage_status.values()

    def _get_coros(self, stage: StageType) -> list[Coroutine]:

        if isinstance(stage, str):
            stage_method = getattr(self, stage, None)
            if stage_method is None or stage in self._external_stages:
                stage_method = partial(self._external_stages[stage], self)

            stage_kwargs = self._stage_params.get(stage, {})

            if not asyncio.iscoroutinefunction(stage_method):
                raise HALError(f"Stage function for {stage} is not a coroutine.")

            return [stage_method(**stage_kwargs)]

        else:
            coros: list[Coroutine] = []
            for st in stage:
                coros += self._get_coros(st)

            return coros

    async def _do_run(self):
        """Actually run the stages."""

        current_task: asyncio.Future | None = None

        for istage, stage in enumerate(self.stages):
            stage_coros = self._get_coros(stage)
            current_task = asyncio.gather(*stage_coros)

            self.set_stage_status(stage, StageStatus.ACTIVE)

            try:
                await current_task
            except asyncio.CancelledError:
                with suppress(asyncio.CancelledError):
                    current_task.cancel()
                    await current_task
                # Cancel this and all future stages.
                cancel_stages = flatten_stages(self.stages[istage:])
                self.set_stage_status(cancel_stages, StageStatus.CANCELLED)
                return
            except Exception as err:
                warnings.warn(
                    f"Macro {self.name} failed with error {err}",
                    HALUserWarning,
                )
                self.fail_macro(err, stage=stage)
                return

            self.set_stage_status(stage, StageStatus.FINISHED)

    def cancel(self):
        """Cancels the execution ot the macro."""

        if not self.running or not self._running_task:
            raise HALError("The macro is not running.")

        self._running_task.cancel()

    async def preconditions(self):
        """A task that is run concurrently with the stages when the macro starts."""

        pass