"""Sensor platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_HUMIDITY_CURRENT, DP_TEMP_CURRENT, DP_TEMP_SET

SENSOR_CODES = {DP_HUMIDITY_CURRENT, DP_TEMP_CURRENT}
EXCLUDED_CODES = {DP_TEMP_SET, "temp_set_f", "switch", "fan_switch", "switch_led"}
UNITS = {
    DP_HUMIDITY_CURRENT: PERCENTAGE,
    DP_TEMP_CURRENT: UnitOfTemperature.CELSIUS,
}
LABELS = {
    DP_HUMIDITY_CURRENT: "humedad",
    DP_TEMP_CURRENT: "temperatura actual",
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            # Known read-only sensors. Unknown dp_N values are intentionally hidden from
            # the normal UI; they belong in diagnostics, not as user-facing entities.
            if code in SENSOR_CODES and code not in EXCLUDED_CODES:
                entities.append(TuyaBYOSensor(coordinator, str(dp), code))
    async_add_entities(entities)

class TuyaBYOSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, dp: str, code: str) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_sensor"
        label = LABELS.get(code, code.replace("_", " "))
        self._attr_name = f"{coordinator.name} {label}"
        self._attr_native_unit_of_measurement = UNITS.get(code)
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        return self.coordinator.get_dp_value(self.dp)
