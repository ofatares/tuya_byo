"""Number platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import capability_for_code, friendly_label, is_diagnostic_code, is_number, values_dict
from .const import DATA_COORDINATORS, DOMAIN, DP_FAN_SPEED, DP_HUMIDITY_CURRENT, DP_TEMP_CURRENT, DP_TEMP_SET

EXCLUDED_CODES = {
    DP_TEMP_SET,
    DP_TEMP_CURRENT,
    DP_HUMIDITY_CURRENT,
    DP_FAN_SPEED,
    "fan_speed_enum",
    "fan_mode",
    "wind_speed",
    "windspeed",
    "temp_current_f",
    "temp_set_f",
}
USER_NUMBER_CAPABILITIES = {"timer", "brightness", "color_temperature"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            cap = capability_for_code(code)
            if is_diagnostic_code(code) or code in EXCLUDED_CODES:
                continue
            if is_number(meta) and cap in USER_NUMBER_CAPABILITIES:
                entities.append(TuyaBYONumber(coordinator, str(dp), code, meta))
    async_add_entities(entities)


class TuyaBYONumber(CoordinatorEntity, NumberEntity):
    def __init__(self, coordinator, dp: str, code: str, meta: dict) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        values = values_dict(meta)
        self.scale = int(values.get("scale", 0)) if isinstance(values, dict) else 0
        divider = 10 ** self.scale
        self._attr_native_min_value = (float(values.get("min", 0)) / divider) if isinstance(values, dict) else 0
        self._attr_native_max_value = (float(values.get("max", 100)) / divider) if isinstance(values, dict) else 100
        self._attr_native_step = (float(values.get("step", 1)) / divider) if isinstance(values, dict) else 1
        if isinstance(values, dict) and values.get("unit"):
            self._attr_native_unit_of_measurement = values.get("unit")
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_number"
        self._attr_name = f"{coordinator.name} {friendly_label(code)}"
        self._attr_device_info = coordinator.device_info
        self._attr_extra_state_attributes = {"tuya_byo_capability": capability_for_code(code), "homekit_recommended": False}

    @property
    def native_value(self):
        value = self.coordinator.get_dp_value(self.dp)
        if value is None:
            return None
        try:
            return float(value) / (10 ** self.scale)
        except Exception:  # noqa: BLE001
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_dp(self.dp, int(round(float(value) * (10 ** self.scale))))
