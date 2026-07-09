"""Switch platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN

# These are represented by dedicated entities.
KNOWN_PRIMARY_CODES = {"switch", "switch_led", "fan_switch"}

# Only create user-facing switches when the code is meaningful. Unknown dp_XXX
# values are hidden from the normal UI; they belong in diagnostics.
SWITCH_CODE_HINTS = (
    "sleep", "quiet", "night",
    "mute", "silent",
    "display", "led", "screen", "panel",
    "eco", "energy", "save",
    "turbo", "boost", "powerful", "strong",
    "swing", "swing_ud", "swing_lr", "wind_swing",
    "clean", "self_clean", "health", "anion", "ion",
    "beep", "sound",
    "child", "lock",
    "fresh", "uv", "steril", "dry", "mildew",
)

LABELS = {
    "fan_beep": "beep",
    "beep": "beep",
    "switch_sleep": "sleep",
    "sleep": "sleep",
    "quiet_sleep": "sleep",
    "mute": "mute",
    "switch_mute": "mute",
    "display": "display",
    "switch_display": "display",
    "led": "led",
    "switch_led": "luz",
    "screen": "pantalla",
    "panel": "display",
    "eco": "eco",
    "energy": "eco",
    "turbo": "turbo",
    "boost": "turbo",
    "powerful": "turbo",
    "swing": "swing",
    "swing_ud": "swing vertical",
    "swing_lr": "swing horizontal",
    "switch_swing": "swing",
    "switch_swing_ud": "swing vertical",
    "switch_swing_lr": "swing horizontal",
    "self_clean": "autolimpieza",
    "clean": "limpieza",
    "anion": "ionizador",
    "health": "health",
    "child_lock": "bloqueo infantil",
}


def _is_user_switch(code: str, meta: dict, value) -> bool:
    code_l = code.lower()
    if code_l.startswith("dp_"):
        return False
    if code_l in KNOWN_PRIMARY_CODES:
        return False
    is_boolean_type = str(meta.get("type", "")).lower() in {"boolean", "bool"}
    is_boolean_value = isinstance(value, bool)
    looks_like_switch = any(hint in code_l for hint in SWITCH_CODE_HINTS)
    return (is_boolean_type or is_boolean_value) and looks_like_switch


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            value = coordinator.get_dp_value(dp)
            if _is_user_switch(code, meta, value):
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
        if "lock" in code:
            self._attr_device_class = SwitchDeviceClass.SWITCH

    @property
    def is_on(self):
        return bool(self.coordinator.get_dp_value(self.dp, False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp, False)
