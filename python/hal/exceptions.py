# !usr/bin/env python
# -*- coding: utf-8 -*-
#
# Licensed under a 3-clause BSD license.
#
# @Author: Brian Cherinka
# @Date:   2017-12-05 12:01:21
# @Last modified by:   Brian Cherinka
# @Last Modified time: 2017-12-05 12:19:32

from __future__ import print_function, division, absolute_import


class HalError(Exception):
    """A custom core Hal exception"""

    def __init__(self, message=None):

        message = 'There has been an error' \
            if not message else message

        super(HalError, self).__init__(message)


class HalNotImplemented(HalError):
    """A custom exception for not yet implemented features."""

    def __init__(self, message=None):

        message = 'This feature is not implemented yet.' \
            if not message else message

        super(HalNotImplemented, self).__init__(message)


class HalAPIError(HalError):
    """A custom exception for API errors"""

    def __init__(self, message=None):
        if not message:
            message = 'Error with Http Response from Hal API'
        else:
            message = 'Http response error from Hal API. {0}'.format(message)

        super(HalAPIError, self).__init__(message)


class HalApiAuthError(HalAPIError):
    """A custom exception for API authentication errors"""
    pass


class HalMissingDependency(HalError):
    """A custom exception for missing dependencies."""
    pass


class HalWarning(Warning):
    """Base warning for Hal."""


class HalUserWarning(UserWarning, HalWarning):
    """The primary warning class."""
    pass


class HalSkippedTestWarning(HalUserWarning):
    """A warning for when a test is skipped."""
    pass


class HalDeprecationWarning(HalUserWarning):
    """A warning for deprecated features."""
    pass
