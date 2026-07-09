# Changelog

## 0.12.0

- Adds live-DP inspector entities for unknown DPS (`dp_101`, `dp_102`, etc.).
- Preserves and exposes live DPS even when the Tuya Cloud model does not name them.
- Adds extra automatic switches for boolean/switch-like functions such as sleep, mute, display, eco, turbo, swing, clean, ionizer and beep when present.
- Keeps unknown numeric DPS as sensors instead of writable controls to avoid unsafe commands.
- Improves fan mode handling for climate devices.
- Keeps TinyTuya device creation and polling inside Home Assistant executor.

## 0.11.0

- Fixes connectivity regression with TinyTuya executor handling.
