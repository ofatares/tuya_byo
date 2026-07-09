"""Switch platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN

KNOWN_PRIMARY_CODES = {"switch", "switch_led", "fan_switch"}
SWITCH_CODE_HINTS = (
    "sleep", "mute", "display", "led", "screen", "eco", "turbo", "swing",
    "clean", "health", "anion", "ion", "beep", "light", "child", "lock",
)
LABELS = {
    "fan_beep": "beep",
    "switch_sleep": "sleep",
    "sleep": "sleep",
    "mute": "mute",
    "switch_mute": "mute",
    "display": "display",
    "switch_display": "display",
    "led": "led",
    "switch_led": "luz",
    "screen": "pantalla",
    "eco": "eco",
    "turbo": "turbo",
    "swing": "swing",
    "swing_ud": "swing vertical",
    "swing_lr": "swing horizontal",
    "self_clean": "autolimpieza",
    "anion": "ionizador",
}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            value = coordinator.get_dp_value(dp)
            is_boolean_type = meta.get("type") in {"Boolean", "bool"}
            is_boolean_value = isinstance(value, bool)
            looks_like_switch = any(hint in code.lower() for hint in SWITCH_CODE_HINTS)
            if (is_boolean_type or is_boolean_value or looks_like_switch) and code not in KNOWN_PRIMARY_CODES:
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
