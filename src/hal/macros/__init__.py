#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# @Author: José Sánchez-Gallego (gallegoj@uw.edu)
# @Date: 2021-10-10
# @Filename: __init__.py
# @License: BSD 3-clause (http://www.opensource.org/licenses/BSD-3-Clause)

import glob
import importlib
import inspect
import os
import warnings

from hal.exceptions import HALUserWarning

from .macro import Macro


# Dynamically inspect all the files in this directory and import the subclasses
# of Macro. Also create a list of instances for the macros.

# TODO: maybe Macro subclasses should be a singleton ...


exclusions = ["__init__.py", "macro.py"]

cwd = os.getcwd()
os.chdir(os.path.dirname(os.path.realpath(__file__)))

files = [f_ for f_ in glob.glob("**/*.py", recursive=True) if f_ not in exclusions]
all_macros: list[Macro] = []

for f_ in files:
    try:
        modname = f_[0:-3].replace("/", ".")
        mod = importlib.import_module("hal.macros." + modname)
        for objname in dir(mod):
            if objname.startswith("_"):
                continue

            obj = getattr(mod, objname)
            if inspect.isclass(obj) and issubclass(obj, Macro) and obj != Macro:
                all_macros.append(obj())
                locals().update({objname: obj})

    except Exception as ee:
        warnings.warn(f"cannot import file {f_}: {ee}", HALUserWarning)

os.chdir(cwd)

__all__ = ["all_macros", "Macro"]
