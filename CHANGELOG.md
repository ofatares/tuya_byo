# Changelog

## 0.20.0

- Fix HVAC power semantics: OFF writes only the power DP and mode is no longer treated as ON.
- Use TinyTuya set_status for DPS writes.
- Force a fresh local refresh immediately after commands.
- Improve HVAC fan modes and keep vertical swing support conservative.

