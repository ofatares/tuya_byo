# Tuya BYO

Tuya BYO is a Home Assistant custom integration for local control of Tuya / Smart Life devices using TinyTuya as local transport and Tuya Cloud only for device metadata, local keys and capability discovery.

## v0.18.0

This version focuses on the Cloud knowledge layer:

- downloads device specifications/functions/status from several Tuya endpoints;
- parses Thing Model responses, including nested JSON strings;
- writes a diagnostic file to `/config/tuya_byo/diagnostics.json`;
- improves mapping of DP IDs to real capabilities when Tuya Cloud exposes them;
- keeps UI generation conservative to avoid breaking working controls.

## Important

Do not commit your real `devices.json`, local keys or Tuya API secrets.

a
