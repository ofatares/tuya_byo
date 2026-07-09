# Tuya BYO

Tuya BYO is a Home Assistant custom integration for local control of Tuya / Smart Life devices.

It uses Tuya Cloud only to retrieve local keys and device model metadata. Commands and polling are local through TinyTuya.

## Current goals

- Clean user-facing entities by default.
- Hide raw `DP xxx` noise from normal UI.
- Use Tuya Cloud Product Specification / Thing Model where available.
- Create meaningful Home Assistant entities: climate, fan, light, switch, select, number and sensor.
- Keep technical diagnostics separate from controls.

## Notes

The integration domain is now `tuya_byo`.

If you previously installed experimental builds using `localtuya_byo`, remove that integration and install Tuya BYO as a new integration.
