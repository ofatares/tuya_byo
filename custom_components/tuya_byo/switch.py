"""Switch platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import (
    CLIMATE_PRESET_CAPABILITIES,
    CLIMATE_SWING_CAPABILITIES,
    PRIMARY_CODES,
    USER_SWITCH_CAPABILITIES,
    capability_for_code,
    friendly_label,
    is_boolean,
    is_diagnostic_code,
)
from .const import DATA_COORDINATORS, DOMAIN

# Capabilities that belong inside the climate card when the device is a climate device.
CLIMATE_OWNED = CLIMATE_PRESET_CAPABILITIES | CLIMATE_SWING_CAPABILITIES | {"fan_mode"}


def _device_has_climate(coordinator) -> bool:
    return bool(coordinator.find_dp("temp_set") and coordinator.find_dp("mode"))


def _is_user_switch(coordinator, dp: str, code: str, meta: dict, value) -> bool:
    code_l = code.lower()
    if is_diagnostic_code(code_l):
        return False
    if code_l in PRIMARY_CODES:
        return False
    cap = capability_for_code(code_l)
    if _device_has_climate(coordinator) and cap in CLIMATE_OWNED:
        return False
    if cap not in USER_SWITCH_CAPABILITIES:
        return False
    return is_boolean(meta, value)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            value = coordinator.get_dp_value(dp)
            if _is_user_switch(coordinator, str(dp), code, meta, value):
                entities.append(TuyaBYOSwitch(coordinator, str(dp), code))
    async_add_entities(entities)


class TuyaBYOSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, dp: str, code: str) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_switch"
        self._attr_name = f"{coordinator.name} {friendly_label(code)}"
        self._attr_device_info = coordinator.device_info
        if "lock" in code:
            self._attr_device_class = SwitchDeviceClass.SWITCH
        self._attr_extra_state_attributes = {"tuya_byo_capability": capability_for_code(code), "homekit_recommended": True}

    @property
    def is_on(self):
        return bool(self.coordinator.get_dp_value(self.dp, False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp, False)
