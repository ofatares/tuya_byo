"""Climate platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
try:
    from homeassistant.components.climate.const import PRESET_NONE
except Exception:  # noqa: BLE001
    PRESET_NONE = "none"
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_FAN_SPEED, DP_MODE, DP_SWITCH, DP_TEMP_CURRENT, DP_TEMP_SET

MODE_TO_HVAC = {
    "cold": HVACMode.COOL,
    "hot": HVACMode.HEAT,
    "wet": HVACMode.DRY,
    "wind": HVACMode.FAN_ONLY,
    "auto": HVACMode.AUTO,
}
HVAC_TO_MODE = {v: k for k, v in MODE_TO_HVAC.items()}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        if coordinator.find_dp(DP_TEMP_SET) and coordinator.find_dp(DP_MODE):
            entities.append(TuyaBYOClimate(coordinator))
    async_add_entities(entities)

class TuyaBYOClimate(CoordinatorEntity, ClimateEntity):
    """Tuya climate entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.AUTO]
    _attr_preset_modes = [PRESET_NONE]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_climate"
        self._attr_name = coordinator.name
        self._attr_device_info = coordinator.device_info
        self.dp_switch = coordinator.find_dp(DP_SWITCH)
        self.dp_target = coordinator.find_dp(DP_TEMP_SET)
        self.dp_current = coordinator.find_dp(DP_TEMP_CURRENT)
        self.dp_mode = coordinator.find_dp(DP_MODE)
        self.dp_fan_mode = coordinator.find_dp(DP_FAN_SPEED, "fan_speed_enum", "wind_speed", "fan_mode", "windspeed")
        self._attr_fan_modes = self._build_fan_modes()
        meta = coordinator.mapping.get(self.dp_target, {}) if self.dp_target else {}
        vals = meta.get("values", {}) if isinstance(meta, dict) else {}
        self.scale = int(vals.get("scale", 1)) if isinstance(vals, dict) else 1
        divider = 10 ** self.scale
        self._attr_min_temp = (int(vals.get("min", 160)) / divider) if isinstance(vals, dict) else 16
        self._attr_max_temp = (int(vals.get("max", 310)) / divider) if isinstance(vals, dict) else 31

    @property
    def hvac_mode(self):
        if self.dp_switch and not bool(self.coordinator.get_dp_value(self.dp_switch, False)):
            return HVACMode.OFF
        mode = self.coordinator.get_dp_value(self.dp_mode, "auto")
        return MODE_TO_HVAC.get(mode, HVACMode.AUTO)

    @property
    def current_temperature(self):
        val = self.coordinator.get_dp_value(self.dp_current)
        try:
            return float(val)
        except Exception:
            return None

    @property
    def target_temperature(self):
        val = self.coordinator.get_dp_value(self.dp_target)
        try:
            return float(val) / (10 ** self.scale)
        except Exception:
            return None


    def _build_fan_modes(self):
        if not self.dp_fan_mode:
            self._attr_supported_features &= ~ClimateEntityFeature.FAN_MODE
            return None
        meta = self.coordinator.mapping.get(self.dp_fan_mode, {})
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        options = []
        if isinstance(values, dict):
            rng = values.get("range") or values.get("options")
            if isinstance(rng, list):
                options = [str(v) for v in rng]
        if not options:
            current = self.coordinator.get_dp_value(self.dp_fan_mode)
            # Johnson/Midea modules often expose fan mode as string even if cloud says Integer.
            if isinstance(current, str):
                options = ["auto", "low", "middle", "high", "strong"]
            else:
                options = ["auto", "low", "middle", "high", "strong"]
        return options

    @property
    def fan_mode(self):
        if not self.dp_fan_mode:
            return None
        value = self.coordinator.get_dp_value(self.dp_fan_mode)
        return str(value) if value is not None else None

    async def async_set_fan_mode(self, fan_mode: str):
        if not self.dp_fan_mode:
            return
        current = self.coordinator.get_dp_value(self.dp_fan_mode)
        # If the device reports strings, send strings. If it reports numeric values, map common names.
        if isinstance(current, int):
            mapping = {"auto": 0, "low": 1, "middle": 2, "high": 3, "strong": 4}
            await self.coordinator.async_set_dp(self.dp_fan_mode, mapping.get(fan_mode, current))
        else:
            await self.coordinator.async_set_dp(self.dp_fan_mode, fan_mode)

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.OFF:
            if self.dp_switch:
                await self.coordinator.async_set_dp(self.dp_switch, False)
            return
        if self.dp_switch:
            await self.coordinator.async_set_dp(self.dp_switch, True)
        if self.dp_mode and hvac_mode in HVAC_TO_MODE:
            await self.coordinator.async_set_dp(self.dp_mode, HVAC_TO_MODE[hvac_mode])

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE not in kwargs or not self.dp_target:
            return
        temp = kwargs[ATTR_TEMPERATURE]
        await self.coordinator.async_set_dp(self.dp_target, int(round(float(temp) * (10 ** self.scale))))
