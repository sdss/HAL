#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

from clu import Command
from sdsstools import get_config, get_logger, get_package_version


NAME = "sdss-hal"


config = get_config("hal")
log = get_logger(NAME)


__version__ = get_package_version(path=__file__, package_name=NAME)


from .actor import HALActor
