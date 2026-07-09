# Changelog

## 0.22.0

- Fix: `current_temperature` (climate) and the temp_current sensor never divided by the DP scale factor, unlike `target_temperature`. Now both read the scale from the DP's own metadata (defaulting to unscaled, which matches how most Tuya HVAC modules report ambient temperature).
- Fix: the power/switch DP was only matched against the codes `switch`, `power`, `switch_ac`. Added the very common alias `switch_1` (plus `Power`/`power_switch`), which is likely why some units kept showing the last active HVAC mode (e.g. "Cooling") instead of "Off" — the integration couldn't find the power DP at all, so `hvac_mode` fell back to the mode DP, which Tuya keeps unchanged even when the unit is off.
- Fix: `async_setup_entry` for the climate platform only checked the mode DP against the bare code `mode`, while entity setup itself also accepted `work_mode`. A device using only `work_mode` could therefore fail to get a climate entity created at all. Both now use the same alias list.
- Add: debug-level logging of the resolved DP mapping (raw dps, and which DP was assigned to switch/mode/target/current/fan/swing) when a climate entity is created. Enable debug logging for `custom_components.tuya_byo` and check Settings > System > Logs to see exactly which physical DP feeds each control — useful when a device's mapping is guessed wrong.

## 0.21.0

- Fix HVAC command writes using fresh TinyTuya device per call.
- Add robust DP write fallback: set_status, set_value and multi-value where available.
- Avoid stale local state after power/mode changes.


## 0.20.0

- Fix HVAC power semantics: OFF writes only the power DP and mode is no longer treated as ON.
- Use TinyTuya set_status for DPS writes.
- Force a fresh local refresh immediately after commands.
- Improve HVAC fan modes and keep vertical swing support conservative.

