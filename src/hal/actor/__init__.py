#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from clu import Command
from clu.parsers.click import command_parser

from .actor import HALActor


hal_command_parser = command_parser

HALCommandType = Command[HALActor]


from .calibrations import *
from .goto import *
from .goto_field import *
from .script import *
from .status import *
