# Changelog

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
