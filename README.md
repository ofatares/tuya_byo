# Tuya BYO

Custom Home Assistant integration for local Tuya / Smart Life devices.

## Current focus

Tuya BYO reads Tuya Cloud metadata and local TinyTuya DPS status, then creates Home Assistant entities automatically.

## v0.12.0

This version adds a device inspector mode by exposing unknown live DPS as diagnostic-style sensors. This helps identify hidden functions such as sleep, mute, display LED, swing, turbo and eco.

## HACS

Repository structure:

```text
hacs.json
custom_components/localtuya_byo/manifest.json
```

After updating through HACS, restart Home Assistant manually.
