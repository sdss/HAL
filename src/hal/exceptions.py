#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-03-24
# @Filename: exceptions.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)


class HALError(Exception):
    """A custom core HAL exception"""

    def __init__(self, message=None):
        message = "There has been an error" if not message else message

        super(HALError, self).__init__(message)


class MacroError(HALError):
    """An error during a macro execution."""

    pass


class HALNotImplemented(HALError):
    """A custom exception for not yet implemented features."""

    def __init__(self, message=None):
        message = "This feature is not implemented yet." if not message else message

        super(HALNotImplemented, self).__init__(message)


class HALMissingDependency(HALError):
    """A custom exception for missing dependencies."""

    pass


class HALWarning(Warning):
    """Base warning for HAL."""


class HALUserWarning(UserWarning, HALWarning):
    """The primary warning class."""

    pass


class HALDeprecationWarning(HALUserWarning):
    """A warning for deprecated features."""

    pass
