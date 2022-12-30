#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: macro.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

import asyncio
import enum
import warnings
from collections import defaultdict
from contextlib import suppress

from typing import TYPE_CHECKING, Any, ClassVar, Coroutine, Optional, Union

from clu import Command, CommandStatus

from hal import config
from hal.exceptions import HALUserWarning, MacroError


if TYPE_CHECKING:
    from hal.actor import HALCommandType


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


def flatten(stages: list[StageType]) -> list[str]:
    flat = []
    for stage in stages:
        if isinstance(stage, str):
            flat.append(stage)
        else:
            flat += list(stage)
    return flat


class Macro:
    """A base macro class that offers concurrency and cancellation."""

    __RUNNING__: ClassVar[list[str]] = []

    name: str

    __STAGES__: list[StageType]
    __PRECONDITIONS__: list[StageType] = []
    __CLEANUP__: list[StageType] = []

    def __init__(self, name: Optional[str] = None):

        if name is None and not hasattr(self, "name"):
            raise MacroError("The macro does not have a name attribute.")
        self.name = name or self.name

        if not hasattr(self, "__STAGES__"):
            raise MacroError("Must override __STAGES__.")

        self.stages = self.__PRECONDITIONS__ + self.__STAGES__ + self.__CLEANUP__
        self._flat_stages = flatten(self.stages)

        for stage in self.__PRECONDITIONS__ + self.__CLEANUP__:
            if not isinstance(stage, str):
                raise MacroError(
                    "Preconditions and cleanup stages cannot run in parallel."
                )
            if stage in flatten(self.__STAGES__):
                raise MacroError(f"Stage {stage} cannot be a selectable stage.")

        if len(self.stages) != len(set(self.stages)):
            raise MacroError("Duplicate stages found.")

        self.stage_status = {st: StageStatus.WAITING for st in flatten(self.stages)}

        self._base_config = config["macros"].get(self.name, {}).copy()
        self.config: defaultdict[str, Any] = defaultdict(
            lambda: None, self._base_config.copy()
        )

        self.command: HALCommandType

        self._running: bool = False
        self.failed: bool = False
        self.cancelled: bool = False

        self._running_task: asyncio.Task | None = None

    def __repr__(self):
        stages = flatten(self.stages)
        return f"<{self.__class__.__name__} (name={self.name}, stages={stages})>"

    def _reset_internal(self, **opts):
        """Internal reset method that can be overridden by the subclasses."""

        pass

    def reset(
        self,
        command: HALCommandType,
        reset_stages: Optional[list[StageType]] = None,
        force: bool = False,
        **opts,
    ):
        """Resets stage status.

        ``reset_stages`` is a list of stages to be executed when calling `.run`.
        If ``reset_stages`` is a list of string and ``force=False``, the reset
        stages are rearranged according to the original ``__STAGES__`` order,
        including concurrent stages. If the list of ``reset_stages`` includes
        tuples representing stages that must be run concurrently, or
        ``force=True``, then the stages are run as input.

        ``opts`` parameters will be used to override the macro configuration
        options only until the next reset.

        """

        if command is None:
            raise MacroError("A new command must be passed to reset.")

        self._reset_internal(**opts)

        if reset_stages is None:
            self.stages = self.__PRECONDITIONS__ + self.__STAGES__ + self.__CLEANUP__
        else:
            self.stages = []

            if force is False and all([isinstance(x, str) for x in reset_stages]):
                for stage in self.__STAGES__:
                    if isinstance(stage, str) and stage in reset_stages:
                        self.stages.append(stage)
                    elif isinstance(stage, (tuple, list)):
                        if all([x in reset_stages for x in stage]):
                            self.stages.append(stage)
                        else:
                            for x in stage:
                                if x in reset_stages:
                                    self.stages.append(x)
            else:
                self.stages = reset_stages.copy()

            for stage in flatten(self.stages):
                if stage not in flatten(self.__STAGES__):
                    raise MacroError(f"Unknown stage {stage}.")

            for pre_stage in self.__PRECONDITIONS__:
                if pre_stage not in flatten(self.stages):
                    self.stages.insert(0, pre_stage)

            for cleanup_stage in self.__CLEANUP__:
                if cleanup_stage not in flatten(self.stages):
                    self.stages.append(cleanup_stage)

        if len(self.stages) == 0:
            raise MacroError("No stages found.")

        self._flat_stages = flatten(self.stages)

        # Reload the config and update it with custom options for this run.
        self.config = defaultdict(lambda: None, self._base_config.copy())
        self.config.update(
            {k: v for k, v in opts.items() if k not in self.config or v is not None}
        )

        self.failed = False
        self.cancelled = False

        self.stage_status = {st: StageStatus.WAITING for st in flatten(self.stages)}

        for st in self.stage_status:
            if getattr(self, st, None) is None:
                raise MacroError(f"Cannot find method for stage {st!r}.")

        self.running = False
        self._running_task = None

        if command:
            self.command = command

        self.list_stages()

    @property
    def actor(self):
        """Returns the command actor."""

        return self.command.actor

    @property
    def helpers(self):
        """Returns the actor helpers."""

        return self.actor.helpers

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
        output: bool = True,
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

        if output:
            self.output_stage_status()

    def output_stage_status(
        self,
        command: Optional[HALCommandType] = None,
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

    def list_stages(
        self,
        command: Optional[HALCommandType] = None,
        level: str = "i",
        only_all: bool = False,
    ):
        """Outputs stages to the actor."""

        list_command = command or self.command

        if only_all is False:
            list_command.write(
                level,
                stages=[self.name] + [st for st in flatten(self.stages)],
            )

        list_command.write(
            level,
            all_stages=[self.name]
            + [st for st in flatten(self.__STAGES__ + self.__CLEANUP__)],
        )

    async def fail_macro(
        self,
        error: Exception,
        stage: Optional[StageType] = None,
    ):
        """Fails the macros and informs the actor."""

        self.command.error(error=error)
        self.command.actor.log.exception(f"Macro {self.name} failed with error:")

        self.failed = True

        if stage is None:
            stage = list(self.stage_status.keys())
        else:
            if not isinstance(stage, (list, tuple)):
                stage = [stage]

        for ss in stage:
            if ss in self.__CLEANUP__:
                continue
            if self.stage_status[ss] == StageStatus.ACTIVE:
                self.stage_status[ss] = StageStatus.FAILED
            if self.stage_status[ss] == StageStatus.WAITING:
                self.stage_status[ss] = StageStatus.CANCELLED

        self.output_stage_status()

        for icleanup, cleanup_stage in enumerate(self.__CLEANUP__):
            if self.stage_status[str(cleanup_stage)] != StageStatus.WAITING:
                continue

            if icleanup == 0:
                self.command.warning("Running cleanup tasks.")

            try:
                self.set_stage_status(cleanup_stage, StageStatus.ACTIVE)
                await asyncio.gather(*self._get_coros(cleanup_stage))
                self.set_stage_status(cleanup_stage, StageStatus.FINISHED)
            except Exception as err:
                self.command.error(f"Cleanup {cleanup_stage} failed: {err}")
                self.set_stage_status(cleanup_stage, StageStatus.FAILED)
                break

        self.running = False

    async def run(self):
        """Executes the macro allowing for cancellation."""

        if self.running:
            raise MacroError("This macro is already running.")

        if not hasattr(self, "command") or self.command is None:
            raise MacroError("Cannot start a macro without an active command.")

        if self.command.status.is_done:
            raise MacroError("The command is done.")

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
                raise MacroError(f"Stage function for {stage} is not a coroutine.")

            return [stage_method()]

        else:
            coros: list[Coroutine] = []
            for st in stage:
                coros += self._get_coros(st)

            return coros

    async def _do_run(self):
        """Actually run the stages."""

        current_task: asyncio.Future | None = None

        for istage, stage in enumerate(self.stages):
            stage_coros = [asyncio.create_task(coro) for coro in self._get_coros(stage)]
            current_task = asyncio.gather(*stage_coros)

            self.set_stage_status(stage, StageStatus.ACTIVE)

            try:
                await current_task

            except asyncio.CancelledError:
                with suppress(asyncio.CancelledError):
                    current_task.cancel()
                    await current_task

                # Cancel this and all future stages.
                cancel_stages = [
                    stg
                    for stg in flatten(self.stages[istage:])
                    if stg not in self.__CLEANUP__
                    and self.stage_status[stg] != StageStatus.FINISHED
                ]
                self.set_stage_status(
                    cancel_stages,
                    StageStatus.CANCELLED,
                    output=False,
                )
                self.cancelled = True
                await self.fail_macro(MacroError("The macro was cancelled"))
                return

            except Exception as err:
                warnings.warn(
                    f"Macro {self.name} failed with error '{err}'",
                    HALUserWarning,
                )

                # Cancel stage tasks (in case we are running multiple concurrently).
                with suppress(asyncio.CancelledError):
                    for task in stage_coros:
                        if not task.done():
                            task.cancel()

                await self.fail_macro(err, stage=stage)
                return

            self.set_stage_status(stage, StageStatus.FINISHED)

    def cancel(self):
        """Cancels the execution ot the macro."""

        if not self.running or not self._running_task:
            raise MacroError("The macro is not running.")

        self._running_task.cancel()

    async def send_command(
        self,
        target: str,
        command_string: str,
        raise_on_fail: bool = True,
        **kwargs,
    ):
        """Sends a command to an actor. Raises `.MacroError` if it fails.

        Parameters
        ----------
        target
            Actor to command.
        command_string
            Command string to pass to the actor.
        raise_on_fail
            If the command failed, raise an error.
        kwargs
            Additional parameters to pass to ``send_command()``.

        """

        if not isinstance(self.command, Command):
            raise MacroError("A command is required to use send_command().")

        command = await self.command.send_command(target, command_string, **kwargs)

        if command.status.did_fail and raise_on_fail:
            if command.status == CommandStatus.TIMEDOUT:
                raise MacroError(f"Command {target} {command_string} timed out.")
            else:
                raise MacroError(f"Command {target} {command_string} failed.")

        return command
