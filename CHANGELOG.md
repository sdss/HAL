# Changelog

## Next version

### ✨ Improved

* Several performance improvements to `goto-field`. FFS are only closed if we are taking BOSS calibrations; when turning off lamps, we don't wait until they are really off, just send the command; the APOGEE shutter is closed at the beginning of the goto-field, but we don't wait for it to fully close before moving to the reconfiguration.


## 0.4.0 - December 21, 2022

### 🚀 Added

* [COS-88](https://jira.sdss.org/browse/COS-88) ([#11](https://github.com/sdss/HAL/pull/11)): `hal goto-field` now accepts an `--auto` flag that selects the stages depending on the design loaded.

### 🏷️ Changed

* If `expose` is called with `--without-fpi`, the FPI shutter is left where it is.


## 0.3.0 - September 11, 2022

### 🚀 Added

* [#9](https://github.com/sdss/HAL/pull/9) Some changes for LCO. Splits the script into APO and LCO version.

### 🏷️ Changed

* [#8](https://github.com/sdss/HAL/pull/8) Go to field turns on HgCd during prepare if arcs or Hartmanns are going to be taken, even if the `fvc` stage is selected. If `fvc` is not selected both HgCd and Ne are turned on. The telescope now slews to the field rotator angle.


## 0.2.0 - June 1, 2022

### 🚀 New

* [#2](https://github.com/sdss/HAL/pull/2) HAL expose macro and actor command. Multiple subsequent commits fine-tuning its behaviour.

### ✨ Improved

* [COS-68](https://jira.sdss.org/browse/COS-68) Better handling of lamps during go to field macro. Reduce warm up time for HgCd lamp to 108 seconds to account for BOSS flushing.
* [COS-71](https://jira.sdss.org/browse/COS-71) Update evening/morning calibration scripts with dithered version.
* [#6](https://github.com/sdss/HAL/pull/6) Update the `goto-field` macro to execute the FVC loop at a fixed rotator angle.
* [#7](https://github.com/sdss/HAL/pull/7) Check FBI LED levels before exposing.
* Improved FPI shutter handling.
* Mote `goto-field` improvements:
  * Go to field: add a `cherno stop` during the `prepare` stage.
  * Do not reset cherno offset.
  * Re-slew and open FFS at the same time.
  * Slew timeout 160 -> 180s.
  * Run 5 iterations with full corrections in the `acquire` stage before moving to guiding using the PID coefficients.

### 🔧 Fixed

* If a stage has been finished, do not cancel it.


## 0.1.0 - January 7, 2022

### 🚀 New

* Basic infrastructure for scripts and macros.
* [#1](https://github.com/sdss/HAL/pull/1) Command to run scripts.
* Goto commands and TCC status.
* `goto-field` macro.
