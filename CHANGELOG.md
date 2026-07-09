# Changelog

## 0.15.0

- Adds a capability resolver for climate presets, swing, display/LED, mute and other common Tuya AC functions.
- Moves fan mode and swing mode into the Climate entity when possible.
- Maps Sleep/Eco/Turbo as Climate preset modes when detected.
- Keeps Display/LED/Mute/Clean/Health/Beep as clean user-facing switches.
- Hides unknown `DP xxx` and Fahrenheit entities from normal UI.
- Adds `homekit_recommended` attributes to clean entities to help decide what to expose through HomeKit Bridge.
- Refreshes root/component icon files for HACS.

## 0.14.0

- Renamed integration domain to `tuya_byo`.
- Cleaner default UI.
