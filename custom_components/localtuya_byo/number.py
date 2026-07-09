"""Number platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_FAN_SPEED, DP_TEMP_CURRENT, DP_TEMP_SET, DP_HUMIDITY_CURRENT

EXCLUDED_CODES = {DP_TEMP_SET, DP_TEMP_CURRENT, DP_HUMIDITY_CURRENT, DP_FAN_SPEED, "fan_speed_enum", "temp_current_f", "temp_set_f"}
LABELS = {
    "countdown_left_fan": "temporizador ventilador",
    "temp_value": "temperatura color luz",
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            if code.startswith("dp_"):
                continue
            if meta.get("type") in {"Integer", "Float", "value"} and code not in EXCLUDED_CODES:
                entities.append(TuyaBYONumber(coordinator, str(dp), code, meta))
    async_add_entities(entities)

class TuyaBYONumber(CoordinatorEntity, NumberEntity):
    def __init__(self, coordinator, dp: str, code: str, meta: dict) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        self.scale = int(values.get("scale", 0)) if isinstance(values, dict) else 0
        divider = 10 ** self.scale
        self._attr_native_min_value = (float(values.get("min", 0)) / divider) if isinstance(values, dict) else 0
        self._attr_native_max_value = (float(values.get("max", 100)) / divider) if isinstance(values, dict) else 100
        self._attr_native_step = (float(values.get("step", 1)) / divider) if isinstance(values, dict) else 1
        if isinstance(values, dict) and values.get("unit"):
            self._attr_native_unit_of_measurement = values.get("unit")
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_number"
        label = LABELS.get(code, code.replace("_", " "))
        self._attr_name = f"{coordinator.name} {label}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self):
        value = self.coordinator.get_dp_value(self.dp)
        if value is None:
            return None
        try:
            return float(value) / (10 ** self.scale)
        except Exception:
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_dp(self.dp, int(round(float(value) * (10 ** self.scale))))
