# Changelog

## 0.7.2 - December 11, 2023

### ✨ Improved

* The overheads are now recorded with a `macro_id` that increases for each new macro run.
* Added a `test` macro and command that just waits but is useful for simple testing.


## 0.7.1 - December 10, 2023

### 🔧 Fixed

* Correctly mark whether a set of concurrent stages succeeded in the database overhead table.


## 0.7.0 - December 6, 2023

### 🔥 Breaking changes

* Deprecated Python 3.9.

### 🚀 New

* [#14](https://github.com/sdss/HAL/issues/14) Record overheads for each stage and macro in the database and output `stage_duration` keyword.


## 0.6.0 - December 4, 2023

### 🏷️ Changed

* Set maximum number of iterations for acquisition in `goto-field` to 4.
* If acquisition fails to reach the target RMS after `acquisition_max_iterations` but the RMS is lower than `acquisition_min_rms`, the macro emits a warning but does not fail.

### 🔧 Fixed

* Fixed circular import preventing the import of the goto-field macro.
* Fix getting `target_rms` in auto mode.

### ⚙️ Engineering

* Lint using `ruff`.
* Update workflows.


## 0.6.0b4 - January 15, 2023

### ✨ Improved

* Emit `running_scripts` keyword when a command is running. Needed for Boson 0.3.1.


## 0.6.0b3 - January 15, 2023

### 🔧 Fixed

* Only register MCP callback for gang connection when at APO.


## 0.6.0b2 - January 15, 2023

### 🚀 New

* Added the ability to pause/resume the expose macro. Users can issue `hal expose --pause` that will finish the current exposure and then wait until `hal expose --resume` is issued. If the count is changed while paused, the adjusted ETR is output on resuming. The same behaviour can be achieved with `hal auto --pause` and `hal auto --resume` (note that this will NOT pause the `goto-field` macro).

### 🔧 Fixed

* `hal auto --modify --count X` was not refreshing the `ExposureHelper` after updating the parameters.
* Several issues deciding how to handle command modifiers when the macro is already running.


## 0.6.0b1 - January 10, 2023

### 🚀 New

* [COS-89](https://jira.sdss.org/browse/COS-89) ([#12](https://github.com/sdss/HAL/issues/12) Added an auto-mode macro. When active, the auto macro will run the `goto-field` and `expose` macros continuously. A few minutes before the end of the `expose` macro completes, a new design is preloaded from the queue. The `goto-field` logic for selecting stages is similar to `goto-field --auto`. The auto macro can be cancelled with `hal auto --stop` which will complete the current stage and then quit, or `hal auto --stop --now` that immediately aborts (ongoing exposures are never aborted). The auto mode should be able to take over from any current state; for example if the auto mode is enabled during an `expose` macro, it will skip the `goto-field` stage, wait until `expose` is done, and then start the loop (note tha this case a new design will not be preloaded during the ongoing `expose`). The count of exposures to take can me modified with `hal auto --modify --count X` which behaves similarly to the `hal expose --modify` command. Requires `cherno` 0.5.0 or above.
* [COS-66](https://jira.sdss.org/browse/COS-66) ([#13](https://github.com/sdss/HAL/issues/13) The parameters for an ongoing `expose` macro can be modified by issuing a new `hal expose` command with the `--modify` flag. Exposure information is handled by a new `ExposureHelper` class that calculates the exposures for each instrument and ensures readout time matching. The behaviour for the user should be mostly unchanged.


## 0.5.2 - January 5, 2023

* Fix several typos in the lists of stages for `goto-field --auto`.


## 0.5.1 - January 4, 2023

### 🔧 Fixed

* Do not stop the guide look in `goto-field` if we are not taking BOSS calibrations or halting the axes.


## 0.5.0 - January 2, 2023

### 🚀 New

* Added a new `goto-field` stage, `lamps`, that runs concurrently with `reslew` and turn on BOSS calibrations lamps (if needed) at that point. This saves a few seconds if we are taking a single BOSS arc. The stage is not required, and the lamps will be turned on at the calibration stage if `lamps` is omitted.

### ✨ Improved

* Several performance improvements to `goto-field`. FFS are only closed if we are taking BOSS calibrations; when turning off lamps, we don't wait until they are really off, just send the command; the APOGEE shutter is closed at the beginning of the goto-field, but we don't wait for it to fully close before moving to the reconfiguration.
* After the BOSS FF stage, only the FF lamp is turned off.

### 🔧 Fixed

* Fixed a case in which lamp status reporting could fail if the lamps were caught at an intermediate state in which only some of the lamps were on.

### ⚙️ Engineering

* Macro exceptions are logged to the file log with full traceback.


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
