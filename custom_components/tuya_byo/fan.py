"""Fan platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_FAN_DIRECTION, DP_FAN_SPEED, DP_FAN_SWITCH

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        if coordinator.find_dp(DP_FAN_SWITCH):
            entities.append(TuyaBYOFan(coordinator))
    async_add_entities(entities)

class TuyaBYOFan(CoordinatorEntity, FanEntity):
    """Tuya fan entity."""

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_fan"
        self._attr_name = coordinator.name
        self._attr_device_info = coordinator.device_info
        self.dp_switch = coordinator.find_dp(DP_FAN_SWITCH)
        self.dp_speed = coordinator.find_dp(DP_FAN_SPEED)
        self.dp_direction = coordinator.find_dp(DP_FAN_DIRECTION)
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if self.dp_speed:
            features |= FanEntityFeature.SET_SPEED
        if self.dp_direction:
            features |= FanEntityFeature.DIRECTION
        self._attr_supported_features = features
        meta = coordinator.mapping.get(self.dp_speed, {}) if self.dp_speed else {}
        vals = meta.get("values", {}) if isinstance(meta, dict) else {}
        self.min_speed = int(vals.get("min", 1)) if isinstance(vals, dict) else 1
        self.max_speed = int(vals.get("max", 6)) if isinstance(vals, dict) else 6

    @property
    def is_on(self):
        return bool(self.coordinator.get_dp_value(self.dp_switch, False))

    @property
    def percentage(self):
        if not self.dp_speed:
            return None
        value = self.coordinator.get_dp_value(self.dp_speed)
        try:
            value = int(value)
            return round((value - self.min_speed) * 100 / max(1, (self.max_speed - self.min_speed)))
        except Exception:
            return None

    @property
    def current_direction(self):
        if not self.dp_direction:
            return None
        val = self.coordinator.get_dp_value(self.dp_direction)
        if val == "reverse":
            return "reverse"
        return "forward"

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        await self.coordinator.async_set_dp(self.dp_switch, True)
        if percentage is not None and self.dp_speed:
            await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp_switch, False)

    async def async_set_percentage(self, percentage: int):
        if not self.dp_speed:
            return
        value = self.min_speed + round((percentage / 100) * (self.max_speed - self.min_speed))
        value = max(self.min_speed, min(self.max_speed, value))
        await self.coordinator.async_set_dp(self.dp_speed, value)

    async def async_set_direction(self, direction: str):
        if self.dp_direction:
            await self.coordinator.async_set_dp(self.dp_direction, "reverse" if direction == "reverse" else "forward")
