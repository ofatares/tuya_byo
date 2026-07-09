# Tuya BYO

Tuya BYO is a local-first Home Assistant custom integration for Tuya / Smart Life devices.

## Current focus

- Local control through TinyTuya.
- Cloud-assisted capability discovery.
- Clean Home Assistant entities instead of raw DPS.
- HomeKit-friendly entity output.

## HomeKit

Tuya BYO does not expose devices directly to HomeKit. Use Home Assistant's **HomeKit Bridge** integration and include only the clean entities you want, for example:

- `climate.salon`
- `climate.dormitorio`
- `fan.ventilador`
- `light.ventilador_luz`
- clean switches such as display, mute, clean, health, beep when useful

Diagnostic/raw DP entities are intentionally hidden from normal UI.

## HACS

Repository structure:

```text
custom_components/tuya_byo/manifest.json
hacs.json
icon.png
logo.png
```

## Notes

This is an early integration. Keep your official Tuya/Midea integrations installed until Tuya BYO covers everything you need.
