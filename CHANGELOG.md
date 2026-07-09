# Changelog

## 0.11.0

- Fix TinyTuya blocking calls by creating and polling devices inside Home Assistant executor jobs.
- Restores device connectivity after v0.10 regression.


## 0.10.0
- Rename display name to Tuya BYO.
- Add project logo/icon.
- Add generated select, number and sensor platforms.
- Add extra Boolean DPS switches based on live DPS values.
- Add climate fan mode support where a `fan_speed` DP is available.
