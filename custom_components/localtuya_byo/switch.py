"""Switch platform for Tuya BYO Local."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN

KNOWN_PRIMARY_CODES = {"switch", "switch_led", "fan_switch"}
LABELS = {
    "fan_beep": "beep",
    "sleep": "sleep",
    "mute": "mute",
    "display": "display",
    "led": "led",
    "screen": "pantalla",
    "eco": "eco",
    "turbo": "turbo",
    "swing": "swing",
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp, meta in coordinator.mapping.items():
            code = meta.get("code", f"dp_{dp}")
            value = coordinator.get_dp_value(dp)
            is_boolean_type = meta.get("type") == "Boolean"
            is_boolean_value = isinstance(value, bool)
            if (is_boolean_type or is_boolean_value) and code not in KNOWN_PRIMARY_CODES:
                entities.append(TuyaBYOSwitch(coordinator, str(dp), code))
    async_add_entities(entities)

class TuyaBYOSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, dp: str, code: str) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_switch"
        label = LABELS.get(code, code.replace("_", " "))
        self._attr_name = f"{coordinator.name} {label}"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self):
        return bool(self.coordinator.get_dp_value(self.dp, False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp, False)
