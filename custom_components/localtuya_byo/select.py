"""Select platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_MODE

LABELS = {
    "fan_direction": "dirección",
    "work_mode": "modo luz",
    "temp_unit_convert": "unidad temperatura",
    "swing_mode": "modo swing",
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            values = meta.get("values", {}) if isinstance(meta, dict) else {}
            options = values.get("range") if isinstance(values, dict) else None
            if meta.get("type") == "Enum" and isinstance(options, list) and code not in {DP_MODE}:
                entities.append(TuyaBYOSelect(coordinator, str(dp), code, [str(v) for v in options]))
    async_add_entities(entities)

class TuyaBYOSelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator, dp: str, code: str, options: list[str]) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        self._attr_options = options
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_select"
        label = LABELS.get(code, code.replace("_", " "))
        self._attr_name = f"{coordinator.name} {label}"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self):
        value = self.coordinator.get_dp_value(self.dp)
        return str(value) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_dp(self.dp, option)
