#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: base.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import abc
import asyncio
import enum
import logging
import warnings
from contextlib import suppress

from typing import ClassVar, Coroutine, Generic, Optional, TypeVar, Union, cast

from clu import BaseCommand, FakeCommand
from sdsstools.logger import SDSSLogger

from hal.exceptions import HALError, HALUserWarning


__all__ = ["Macro", "StageHelper"]


StageType = Union[str, tuple[str, ...], list[str]]
Command_co = TypeVar("Command_co", bound=BaseCommand, covariant=True)


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


class StageHelper(abc.ABCMeta):
    """A stage helper."""

    @abc.abstractmethod
    async def run(self, macro: Macro, *args, **kwargs):
        """Stage task."""
        pass

    def __call__(self, macro: Macro, *args, **kwargs):
        return self.run(macro, *args, **kwargs)


class Macro(Generic[Command_co]):
    """A base macro class that offers concurrency and cancellation."""

    __RUNNING__: ClassVar[list[str]] = []

    name: str

    __STAGES__: list[StageType]
    __CLEANUP__: list[StageType] = []

    def __init__(
        self,
        name: Optional[str] = None,
        stages: Optional[list[StageType]] = None,
    ):

        if name is None and not hasattr(self, "name"):
            raise HALError("The macro does not have a name attribute.")
        self.name = name or self.name

        # Stages to actually run (may skip some from __STAGES__)
        if stages is None and not hasattr(self, "__STAGES__"):
            raise HALError("The macro does not have a __STAGES__ attribute.")

        self.stages = stages or self.__STAGES__.copy()
        self.stages += self.__CLEANUP__.copy()

        self.stage_status: dict[str, StageStatus] = {}

        null_log = logging.Logger("hal-null-log")
        null_log.addHandler(logging.NullHandler())

        self.command: Command_co = cast(Command_co, FakeCommand(null_log))

        self._running = False

        self._running_task: asyncio.Task | None = None

        self.reset(self.stages)

    def __repr__(self):
        stages = flatten_stages(self.stages)
        return f"<{self.__class__.__name__} (name={self.name}, stages={stages})>"

    def reset(
        self,
        stages: Optional[list[StageType]] = None,
        command: Optional[Command_co] = None,
    ):
        """Resets stage status."""

        if stages is None:
            stages = self.__STAGES__.copy()
        else:
            stages = stages.copy()

        if len(stages) == 0:
            raise HALError("No stages found.")

        self.stages = stages + self.__CLEANUP__.copy()
        self.stage_status = {st: StageStatus.WAITING for st in flatten_stages(stages)}

        for st in self.stage_status:
            if getattr(self, st, None) is None:
                raise HALError(f"Cannot find method for stage {st!r}.")

        self.running = False
        self._running_task = None

        if command:
            self.command = command

        self.list_stages()

    @property
    def running(self):
        """Is the macro running?"""
        return self._running

    @running.setter
    def running(self, is_running: bool):
        """Sets the macro status as running/not-running and informs the actor."""

        if self._running == is_running:
            return

        self._running = is_running

        if is_running is True and self.name not in Macro.__RUNNING__:
            Macro.__RUNNING__.append(self.name)
        elif is_running is False and self.name in Macro.__RUNNING__:
            Macro.__RUNNING__.remove(self.name)

        self.command.debug(running_macros=Macro.__RUNNING__)

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
                    f"Cannot find stage {stage} in list. "
                    "Maybe the macro was not reset correctly.",
                    HALUserWarning,
                )
                return

            self.stage_status[stage] = status

        self.output_stage_status()

    def output_stage_status(
        self,
        command: Optional[Command_co] = None,
        level: str = "d",
    ):
        """Outputs the stage status to the actor."""

        out_command = command or self.command

        status_keyw = [self.name]
        for stage in self.stage_status:
            status_name = self.stage_status[stage].name
            assert status_name
            status_keyw += [stage, status_name.lower()]

        out_command.write(level, stage_status=status_keyw)

    def list_stages(self, command: Optional[Command_co] = None, level: str = "i"):
        """Outputs stages to the actor."""

        list_command = command or self.command

        list_command.write(
            level,
            stages=[self.name] + [st for st in flatten_stages(self.stages)],
        )
        list_command.write(
            level,
            all_stages=[self.name]
            + [st for st in flatten_stages(self.__STAGES__ + self.__CLEANUP__)],
        )

    async def fail_macro(
        self,
        error: Exception,
        stage: Optional[StageType] = None,
    ):
        """Fails the macros and informs the actor."""

        self.command.error(error=error)

        if stage is None:
            stage = list(self.stage_status.keys())
        else:
            if not isinstance(stage, (list, tuple)):
                stage = [stage]

        is_cleanup: bool = False
        for ss in stage:
            if self.stage_status[ss] == StageStatus.ACTIVE:
                self.stage_status[ss] = StageStatus.FAILED
            if ss in self.__CLEANUP__:
                is_cleanup = True

        self.output_stage_status()

        if len(self.__CLEANUP__) > 0 and is_cleanup is False:
            self.command.warning("Running cleanup tasks.")
            for cleanup_stage in self.__CLEANUP__:
                try:
                    await asyncio.gather(*self._get_coros(cleanup_stage))
                except Exception as err:
                    self.command.error(f"Cleanup {cleanup_stage} failed: {err}")
                    break

        self.running = False

    async def run(self):
        """Executes the macro allowing for cancellation."""

        if self.running:
            raise HALError("This macro is already running.")

        if self.command is None:
            raise HALError("Cannot start a macro without an active command.")

        self.running = True
        self._running_task = asyncio.create_task(self._do_run())

        try:
            await self._running_task
        except asyncio.CancelledError:
            with suppress(asyncio.CancelledError):
                self._running_task.cancel()
                await self._running_task
        except Exception as err:
            await self.fail_macro(err)

        self.running = False

        return StageStatus.FAILED not in self.stage_status.values()

    def _get_coros(self, stage: StageType) -> list[Coroutine]:

        if isinstance(stage, str):
            stage_method = getattr(self, stage)

            if not asyncio.iscoroutinefunction(stage_method):
                raise HALError(f"Stage function for {stage} is not a coroutine.")

            return [stage_method()]

        else:
            coros: list[Coroutine] = []
            for st in stage:
                coros += self._get_coros(st)

            return coros

    async def _do_run(self):
        """Actually run the stages."""

        current_task: asyncio.Future | None = None

        for istage, stage in enumerate(self.stages + self.__CLEANUP__.copy()):
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
                await self.fail_macro(err, stage=stage)
                return

            self.set_stage_status(stage, StageStatus.FINISHED)

    def cancel(self):
        """Cancels the execution ot the macro."""

        if not self.running or not self._running_task:
            raise HALError("The macro is not running.")

        self._running_task.cancel()
