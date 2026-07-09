# Tuya BYO

Tuya BYO is a Home Assistant custom integration for local control of Tuya/Smart Life devices.

## 0.13.0

This version adds the first Cloud Product Specification / Thing Model analyser. It uses Tuya Cloud metadata to name and classify functions, then controls the device locally through TinyTuya.

Current focus:

- Climate devices: temperature, mode and fan mode.
- Create ceiling fan: fan, direction and light.
- Extra Cloud-described switches/selects/numbers when the Cloud API exposes exact DP identifiers.

Raw unknown DPS are hidden from the normal UI to avoid unusable entities like `DP 103`.
