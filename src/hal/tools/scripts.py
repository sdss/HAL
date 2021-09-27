#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-09-27
# @Filename: scripts.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from hal.actor import HALActor


__all__ = ["Scripts"]


@dataclass
class Scripts:

    actor: HALActor
