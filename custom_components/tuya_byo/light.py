"""Light platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_SWITCH_LED

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        if coordinator.find_dp(DP_SWITCH_LED):
            entities.append(TuyaBYOLight(coordinator))
    async_add_entities(entities)

class TuyaBYOLight(CoordinatorEntity, LightEntity):
    # This is a plain on/off panel LED, no brightness/color -- but HA now
    # requires every LightEntity to declare supported_color_modes even for
    # that case, otherwise entity registration raises HomeAssistantError and
    # the whole light platform setup for this entry fails.
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self.dp_switch = coordinator.find_dp(DP_SWITCH_LED)
        self._attr_unique_id = f"{coordinator.device_id}_light"
        self._attr_name = f"{coordinator.name} luz"
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self):
        return bool(self.coordinator.get_dp_value(self.dp_switch, False))

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp_switch, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp_switch, False)
