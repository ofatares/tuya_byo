# Changelog

## 0.26.0

- Fix: `_build_swing_modes()` always returned the full hardcoded 8-position list (Up Flow, Above Up Fix, etc.) as soon as any swing DP was found, regardless of what the device's real Enum range actually is -- unlike `_build_fan_modes()`, which correctly reads the real range from the resolved DP's metadata. This both risked sending positions the device doesn't support and didn't explain a device showing fewer options than expected. Now mirrors the fan-mode logic: real range if known, a plain Apagado/Swing-vertical toggle if the DP is Boolean or the range isn't known.

## 0.25.1

- Revert: the persistent connection used for status polling since 0.24.0 caused intermittent disconnects and erratic state, especially noticeable when changing settings from the official Tuya app. This is consistent with the reason writes already avoided persistent sockets (some Tuya 3.5 HVAC modules don't tolerate a reused connection well) -- it evidently applies to reads on this hardware too. Reverted to a fresh connection per poll.
- Poll interval dialed back from the aggressive 6s to a more conservative 12s (still faster than the original 15s) to reduce connection churn now that every poll reconnects from scratch again.
- Kept: write-path preference caching and the batched switch+mode write from 0.23/0.24, which are unrelated to this and unaffected.

## 0.25.0

- Fix: the integration already called Tuya's "Query Things Data Model" endpoint (`GET /v2.0/cloud/thing/{device_id}/model`) -- the one endpoint that actually returns the real numeric DP id (as `abilityId`) alongside each function's code/type/value range -- but its response is a JSON-encoded *string*, and the parser silently dropped it instead of decoding it, and didn't recognise `abilityId` as a dp_id field. Both are fixed, verified against Tuya's documented example payload and a synthetic AC-shaped one (switch/mode/eco/swing_ud/switch_led all resolved correctly with the right dp_id, type and enum ranges).
- This means swing (including the precision multi-position options), eco, sleep, panel LED, etc. can now be discovered automatically from Tuya Cloud instead of relying on the value-matching guesswork (which was ambiguous for booleans) or on manual trial-and-error.
- Fix: a hardcoded DP5-is-fan-speed override for "kt"-category (Johnson/Midea) devices used to unconditionally overwrite whatever DP5 actually resolved to. Now it only applies when DP5 is still unmapped, so it can't clobber a correct mapping now that the model endpoint works.
- Add: a `reconfigure` step (Settings > Devices & Services > Tuya BYO > Reconfigure, needs HA 2024.11+) that re-queries Tuya Cloud with your existing credentials and refreshes the DP mapping in place -- no need to delete and re-add the integration to pick this up. If your HA is older, removing and re-adding the integration achieves the same thing.

## 0.24.0

- Perf: status polling now reuses one persistent local connection instead of opening a brand-new one (full TCP + session-key handshake) every single poll. This was the main reason the integration felt slower than the official Tuya app and lagged behind changes made from the mobile app. Writes still use a fresh connection per attempt on purpose (see 0.21.0 — reusing sockets for writes previously caused some Tuya 3.5 HVAC modules to ignore commands), so this only speeds up reads.
- Perf: writes now remember which command style (`set_status`/`set_value`/`set_multiple_values`) actually worked last time for each device and try it first, instead of always attempting them in a fixed order. In the common case this cuts a write down to a single attempt.
- Poll interval shortened from 15s to 6s now that polling is cheap, so changes made from the official app should show up in Home Assistant noticeably faster.

## 0.23.0

- Perf: turning the unit on with a specific HVAC mode used to issue two sequential local writes (power DP, then mode DP), each opening its own connection and forcing its own status refresh — roughly doubling how long "turn on" takes compared to a single-DP write. Added `TuyaBYODevice.async_set_dps()` to batch both DPs into one local command with a single status refresh at the end; `async_set_hvac_mode` now uses it.
- Reliability: added a short pause between fallback write paths (`set_status` -> `set_value` -> `set_multiple_values`) instead of reconnecting back-to-back, and one automatic retry (after a 1s pause) on a failed status poll before marking the entity unavailable. Local Tuya modules can be picky about rapid repeated connections; this should reduce spurious "No disponible" states and missed refreshes.

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

