"""Select platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import (
    CLIMATE_PRESET_CAPABILITIES,
    CLIMATE_SWING_CAPABILITIES,
    FAN_MODE_CODES,
    capability_for_code,
    enum_options,
    friendly_label,
    is_diagnostic_code,
)
from .const import DATA_COORDINATORS, DOMAIN, DP_MODE

CLIMATE_OWNED_CAPABILITIES = CLIMATE_PRESET_CAPABILITIES | CLIMATE_SWING_CAPABILITIES | {"fan_mode"}
CLIMATE_OWNED_CODES = {DP_MODE, *FAN_MODE_CODES}


def _device_has_climate(coordinator) -> bool:
    return bool(coordinator.find_dp("temp_set") and coordinator.find_dp("mode"))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        has_climate = _device_has_climate(coordinator)
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            if is_diagnostic_code(code):
                continue
            cap = capability_for_code(code)
            if has_climate and (cap in CLIMATE_OWNED_CAPABILITIES or code in CLIMATE_OWNED_CODES):
                continue
            options = enum_options(meta)
            if options:
                entities.append(TuyaBYOSelect(coordinator, str(dp), code, options))
    async_add_entities(entities)


class TuyaBYOSelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator, dp: str, code: str, options: list[str]) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        self._attr_options = options
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_select"
        self._attr_name = f"{coordinator.name} {friendly_label(code)}"
        self._attr_device_info = coordinator.device_info
        self._attr_extra_state_attributes = {"tuya_byo_capability": capability_for_code(code), "homekit_recommended": True}

    @property
    def current_option(self):
        value = self.coordinator.get_dp_value(self.dp)
        return str(value) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_dp(self.dp, option)
