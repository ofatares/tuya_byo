"""Climate platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
try:
    from homeassistant.components.climate.const import PRESET_NONE
except Exception:  # noqa: BLE001
    PRESET_NONE = "none"
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import (
    CLIMATE_PRESET_CAPABILITIES,
    CLIMATE_SWING_CAPABILITIES,
    capability_for_code,
    enum_options,
    is_boolean,
)
from .const import (
    DATA_COORDINATORS,
    DOMAIN,
    DP_FAN_SPEED,
    DP_MODE,
    DP_SWITCH,
    DP_TEMP_CURRENT,
    DP_TEMP_SET,
)

MODE_TO_HVAC = {
    "cold": HVACMode.COOL,
    "cool": HVACMode.COOL,
    "hot": HVACMode.HEAT,
    "heat": HVACMode.HEAT,
    "wet": HVACMode.DRY,
    "dry": HVACMode.DRY,
    "wind": HVACMode.FAN_ONLY,
    "fan": HVACMode.FAN_ONLY,
    "fan_only": HVACMode.FAN_ONLY,
    "auto": HVACMode.AUTO,
}
HVAC_TO_MODE = {
    HVACMode.COOL: "cold",
    HVACMode.HEAT: "hot",
    HVACMode.DRY: "wet",
    HVACMode.FAN_ONLY: "wind",
    HVACMode.AUTO: "auto",
}

FAN_MODE_CODES = (DP_FAN_SPEED, "fan_speed_enum", "wind_speed", "fan_mode", "windspeed", "speed")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        if coordinator.find_dp(DP_TEMP_SET) and coordinator.find_dp(DP_MODE):
            entities.append(TuyaBYOClimate(coordinator))
    async_add_entities(entities)


class TuyaBYOClimate(CoordinatorEntity, ClimateEntity):
    """Tuya climate entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.AUTO]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_climate"
        self._attr_name = coordinator.name
        self._attr_device_info = coordinator.device_info
        self._attr_extra_state_attributes = {"homekit_recommended": True}
        self.dp_switch = coordinator.find_dp(DP_SWITCH)
        self.dp_target = coordinator.find_dp(DP_TEMP_SET)
        self.dp_current = coordinator.find_dp(DP_TEMP_CURRENT)
        self.dp_mode = coordinator.find_dp(DP_MODE)
        self.dp_fan_mode = coordinator.find_dp(*FAN_MODE_CODES)
        self.dp_swing, self._swing_capability = self._find_swing_dp()
        self._preset_dps = self._find_preset_dps()

        features = ClimateEntityFeature.TARGET_TEMPERATURE
        if self.dp_fan_mode:
            features |= ClimateEntityFeature.FAN_MODE
        if self.dp_swing:
            features |= ClimateEntityFeature.SWING_MODE
        if self._preset_dps:
            features |= ClimateEntityFeature.PRESET_MODE
        self._attr_supported_features = features

        self._attr_fan_modes = self._build_fan_modes()
        self._attr_swing_modes = self._build_swing_modes()
        self._attr_preset_modes = [PRESET_NONE] + list(self._preset_dps.keys())

        meta = coordinator.mapping.get(self.dp_target, {}) if self.dp_target else {}
        vals = meta.get("values", {}) if isinstance(meta, dict) else {}
        self.scale = int(vals.get("scale", 1)) if isinstance(vals, dict) else 1
        divider = 10 ** self.scale
        self._attr_min_temp = (int(vals.get("min", 160)) / divider) if isinstance(vals, dict) else 16
        self._attr_max_temp = (int(vals.get("max", 310)) / divider) if isinstance(vals, dict) else 31

    def _find_swing_dp(self) -> tuple[str | None, str | None]:
        for dp in self.coordinator.all_dps():
            meta = self.coordinator.dp_meta(dp)
            code = str(meta.get("code", ""))
            cap = capability_for_code(code)
            if cap in CLIMATE_SWING_CAPABILITIES:
                return str(dp), cap
        return None, None

    def _find_preset_dps(self) -> dict[str, str]:
        presets: dict[str, str] = {}
        for dp in self.coordinator.all_dps():
            meta = self.coordinator.dp_meta(dp)
            code = str(meta.get("code", ""))
            cap = capability_for_code(code)
            if cap in CLIMATE_PRESET_CAPABILITIES:
                presets.setdefault(cap, str(dp))
        return presets

    @property
    def hvac_mode(self):
        if self.dp_switch:
            power = self.coordinator.get_dp_value(self.dp_switch, False)
            if power in (False, 0, "false", "False", "off", "OFF", "0", None):
                return HVACMode.OFF
        mode = str(self.coordinator.get_dp_value(self.dp_mode, "auto"))
        return MODE_TO_HVAC.get(mode, HVACMode.AUTO)

    @property
    def current_temperature(self):
        val = self.coordinator.get_dp_value(self.dp_current)
        try:
            return float(val)
        except Exception:  # noqa: BLE001
            return None

    @property
    def target_temperature(self):
        val = self.coordinator.get_dp_value(self.dp_target)
        try:
            return float(val) / (10 ** self.scale)
        except Exception:  # noqa: BLE001
            return None

    def _build_fan_modes(self):
        if not self.dp_fan_mode:
            return None
        meta = self.coordinator.mapping.get(self.dp_fan_mode, {})
        options = enum_options(meta)
        if not options:
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
        if isinstance(current, int):
            mapping = {"auto": 0, "low": 1, "middle": 2, "high": 3, "strong": 4}
            await self.coordinator.async_set_dp(self.dp_fan_mode, mapping.get(fan_mode, current))
        else:
            await self.coordinator.async_set_dp(self.dp_fan_mode, fan_mode)

    def _build_swing_modes(self):
        if not self.dp_swing:
            return None
        meta = self.coordinator.dp_meta(self.dp_swing)
        options = enum_options(meta)
        if options:
            return options
        return ["off", "on"]

    @property
    def swing_mode(self):
        if not self.dp_swing:
            return None
        value = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(value, bool):
            return "on" if value else "off"
        return str(value) if value is not None else None

    async def async_set_swing_mode(self, swing_mode: str):
        if not self.dp_swing:
            return
        current = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(current, bool):
            await self.coordinator.async_set_dp(self.dp_swing, swing_mode != "off")
        else:
            await self.coordinator.async_set_dp(self.dp_swing, swing_mode)

    @property
    def preset_mode(self):
        if self.hvac_mode == HVACMode.OFF:
            return PRESET_NONE
        for preset, dp in self._preset_dps.items():
            if bool(self.coordinator.get_dp_value(dp, False)):
                return preset
        return PRESET_NONE

    async def async_set_preset_mode(self, preset_mode: str):
        if not self._preset_dps:
            return
        if preset_mode in (PRESET_NONE, "none", "off"):
            for dp in self._preset_dps.values():
                meta = self.coordinator.dp_meta(dp)
                value = self.coordinator.get_dp_value(dp)
                if is_boolean(meta, value):
                    await self.coordinator.async_set_dp(dp, False)
            return
        dp = self._preset_dps.get(preset_mode)
        if not dp:
            return
        meta = self.coordinator.dp_meta(dp)
        value = self.coordinator.get_dp_value(dp)
        if is_boolean(meta, value):
            # Common AC presets are mutually exclusive in Home Assistant's climate UI.
            for other_preset, other_dp in self._preset_dps.items():
                if other_dp != dp and other_preset in {"sleep", "eco", "turbo"}:
                    await self.coordinator.async_set_dp(other_dp, False)
            await self.coordinator.async_set_dp(dp, True)
        else:
            await self.coordinator.async_set_dp(dp, preset_mode)

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
