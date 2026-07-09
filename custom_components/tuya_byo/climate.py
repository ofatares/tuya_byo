"""Climate platform for Tuya BYO."""
from __future__ import annotations

import logging

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
try:
    from homeassistant.components.climate import FAN_AUTO, FAN_HIGH, FAN_LOW, FAN_MEDIUM
except Exception:  # noqa: BLE001
    FAN_AUTO = "auto"
    FAN_LOW = "low"
    FAN_MEDIUM = "middle"
    FAN_HIGH = "high"
try:
    from homeassistant.components.climate.const import PRESET_NONE, PRESET_SLEEP, PRESET_ECO, PRESET_BOOST
except Exception:  # noqa: BLE001
    PRESET_NONE = "none"
    PRESET_SLEEP = "sleep"
    PRESET_ECO = "eco"
    PRESET_BOOST = "boost"
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_FAN_SPEED, DP_MODE, DP_SWITCH, DP_TEMP_CURRENT, DP_TEMP_SET

_LOGGER = logging.getLogger(__name__)

# Tuya values used by the Johnson/Midea module we have seen in Smart Life / TinyTuya.
MODE_TO_HVAC = {
    "cold": HVACMode.COOL,
    "hot": HVACMode.HEAT,
    "wet": HVACMode.DRY,
    "wind": HVACMode.FAN_ONLY,
    "auto": HVACMode.AUTO,
}
HVAC_TO_MODE = {v: k for k, v in MODE_TO_HVAC.items()}

FAN_LABELS = {
    "auto": "Auto",
    "mute": "Mute",
    "low": "Low",
    "mid_low": "Mid-Low",
    "middle_low": "Mid-Low",
    "mid": "Mid",
    "middle": "Mid",
    "mid_high": "Mid-High",
    "middle_high": "Mid-High",
    "high": "High",
    "turbo": "Turbo",
    "strong": "Turbo",
}

# Home Assistant climate swing modes are strings; keep the Tuya value as command value.
SWING_LABELS = {
    "off": "Apagado",
    "false": "Apagado",
    "0": "Apagado",
    "on": "Encendido",
    "true": "Encendido",
    "1": "Encendido",
    "swing": "Up-Down Flow",
    "up_down": "Up-Down Flow",
    "up": "Up Flow",
    "down": "Down Flow",
    "up_fix": "Up Fix",
    "above_up_fix": "Above Up Fix",
    "middle_fix": "Middle Fix",
    "above_down_fix": "Above Down Fix",
    "down_fix": "Down Fix",
}
SWING_COMMANDS_BY_LABEL = {label: value for value, label in SWING_LABELS.items()}

# Common codes that should be exposed as presets inside climate when present.
PRESET_CODE_HINTS = {
    PRESET_SLEEP: ("sleep", "night", "quiet"),
    PRESET_ECO: ("eco", "energy", "save", "gen"),
    PRESET_BOOST: ("turbo", "boost", "powerful", "strong"),
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        if coordinator.find_dp(DP_TEMP_SET) and coordinator.find_dp(DP_MODE):
            entities.append(TuyaBYOClimate(coordinator))
    async_add_entities(entities)


class TuyaBYOClimate(CoordinatorEntity, ClimateEntity):
    """Tuya air conditioner entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.DRY, HVACMode.FAN_ONLY, HVACMode.AUTO]

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
        self.dp_swing = self._find_swing_dp()
        self.preset_dps = self._find_preset_dps()

        self.scale = 1
        self._attr_min_temp = 16
        self._attr_max_temp = 31
        self._attr_target_temperature_step = 0.5
        self._load_temperature_metadata()

        supported = ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_fan_modes = self._build_fan_modes()
        if self._attr_fan_modes:
            supported |= ClimateEntityFeature.FAN_MODE
        self._attr_swing_modes = self._build_swing_modes()
        if self._attr_swing_modes:
            supported |= ClimateEntityFeature.SWING_MODE
        self._attr_preset_modes = self._build_preset_modes()
        if self._attr_preset_modes and len(self._attr_preset_modes) > 1:
            supported |= ClimateEntityFeature.PRESET_MODE
        self._attr_supported_features = supported

    def _load_temperature_metadata(self) -> None:
        meta = self.coordinator.mapping.get(self.dp_target, {}) if self.dp_target else {}
        vals = meta.get("values", {}) if isinstance(meta, dict) else {}
        if not isinstance(vals, dict):
            return
        try:
            self.scale = int(vals.get("scale", 1))
        except Exception:  # noqa: BLE001
            self.scale = 1
        divider = 10 ** self.scale
        try:
            self._attr_min_temp = int(vals.get("min", 160)) / divider
            self._attr_max_temp = int(vals.get("max", 310)) / divider
        except Exception:  # noqa: BLE001
            self._attr_min_temp = 16
            self._attr_max_temp = 31
        try:
            step_raw = int(vals.get("step", 5))
            self._attr_target_temperature_step = step_raw / divider
        except Exception:  # noqa: BLE001
            self._attr_target_temperature_step = 0.5

    def _normalise_fan_value(self, value) -> str | None:
        if value is None:
            return None
        value = str(value)
        return FAN_LABELS.get(value, value)

    def _build_fan_modes(self):
        if not self.dp_fan_mode:
            return None
        meta = self.coordinator.mapping.get(self.dp_fan_mode, {})
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        options: list[str] = []
        if isinstance(values, dict):
            rng = values.get("range") or values.get("options")
            if isinstance(rng, list):
                options = [self._normalise_fan_value(v) or str(v) for v in rng]
        # Johnson/Midea app shows these 8 fan choices. Use them as stable profile fallback.
        if not options or options in (["Auto", "Low", "Mid", "High", "Turbo"], ["auto", "low", "middle", "high", "strong"]):
            options = ["Auto", "Mute", "Low", "Mid-Low", "Mid", "Mid-High", "High", "Turbo"]
        return list(dict.fromkeys(options))

    def _fan_command_from_label(self, fan_mode: str):
        reverse = {label: value for value, label in FAN_LABELS.items()}
        # Prefer known Tuya strings. For "Mid" use middle if the device currently reports middle.
        if fan_mode == "Mid":
            return "middle"
        if fan_mode == "Turbo":
            # Some modules use strong for turbo; if current value is strong keep that vocabulary.
            current = str(self.coordinator.get_dp_value(self.dp_fan_mode, ""))
            return "strong" if current == "strong" else "turbo"
        return reverse.get(fan_mode, fan_mode)

    def _find_swing_dp(self) -> str | None:
        # Ignore horizontal swing for this model; user confirmed it appears in app but does not work.
        candidates = (
            "swing_ud", "swing_updown", "swing_vertical", "vertical_swing",
            "wind_swing_ud", "wind_swing", "swing", "air_flow_ud", "airflow_ud",
            "direction", "wind_direction", "wind_dir", "swing_mode",
        )
        dp = self.coordinator.find_dp(*candidates)
        if dp:
            return dp
        # Product-specific fallback: DP133/DP123 often represent vertical airflow on these Tuya AC modules.
        product_id = str(self.coordinator.config.get("product_id") or "")
        category = str(self.coordinator.config.get("category") or "")
        if category == "kt" or product_id == "hrzr8mr0mtgfwwri":
            for fallback in ("133", "123", "131"):
                if fallback in self.coordinator.all_dps():
                    return fallback
        return None

    def _build_swing_modes(self):
        if not self.dp_swing:
            return None
        value = self.coordinator.get_dp_value(self.dp_swing)
        meta = self.coordinator.mapping.get(self.dp_swing, {})
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        options: list[str] = []
        if isinstance(values, dict):
            rng = values.get("range") or values.get("options")
            if isinstance(rng, list):
                options = [SWING_LABELS.get(str(v), str(v)) for v in rng]
        if not options:
            if isinstance(value, bool):
                options = ["Apagado", "Encendido"]
            else:
                # Vertical precision airflow modes seen in the mobile app.
                options = [
                    "Apagado",
                    "Up-Down Flow",
                    "Up Flow",
                    "Down Flow",
                    "Up Fix",
                    "Above Up Fix",
                    "Middle Fix",
                    "Above Down Fix",
                    "Down Fix",
                ]
        return list(dict.fromkeys(options))

    def _find_preset_dps(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for dp in self.coordinator.all_dps():
            code = self.coordinator.dp_code(dp).lower()
            if code.startswith("dp_"):
                continue
            for preset, hints in PRESET_CODE_HINTS.items():
                if any(hint in code for hint in hints):
                    value = self.coordinator.get_dp_value(dp)
                    if isinstance(value, bool):
                        result[preset] = str(dp)
        return result

    def _build_preset_modes(self):
        modes = [PRESET_NONE]
        for preset in (PRESET_SLEEP, PRESET_ECO, PRESET_BOOST):
            if preset in self.preset_dps:
                modes.append(preset)
        return modes

    @property
    def hvac_mode(self):
        if self.dp_switch is not None and self.coordinator.get_dp_value(self.dp_switch) is False:
            return HVACMode.OFF
        mode = self.coordinator.get_dp_value(self.dp_mode, "auto")
        return MODE_TO_HVAC.get(str(mode), HVACMode.AUTO)

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

    @property
    def fan_mode(self):
        if not self.dp_fan_mode:
            return None
        return self._normalise_fan_value(self.coordinator.get_dp_value(self.dp_fan_mode))

    @property
    def swing_mode(self):
        if not self.dp_swing:
            return None
        value = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(value, bool):
            return "Encendido" if value else "Apagado"
        return SWING_LABELS.get(str(value), str(value)) if value is not None else None

    @property
    def preset_mode(self):
        for preset, dp in self.preset_dps.items():
            if self.coordinator.get_dp_value(dp) is True:
                return preset
        return PRESET_NONE

    async def async_set_fan_mode(self, fan_mode: str):
        if not self.dp_fan_mode:
            return
        await self.coordinator.async_set_dp(self.dp_fan_mode, self._fan_command_from_label(fan_mode))

    async def async_set_swing_mode(self, swing_mode: str):
        if not self.dp_swing:
            return
        current = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(current, bool):
            await self.coordinator.async_set_dp(self.dp_swing, swing_mode != "Apagado")
            return
        command = SWING_COMMANDS_BY_LABEL.get(swing_mode, swing_mode)
        # Product-specific numeric fallback for DP133 if no Cloud range is available.
        if self.dp_swing == "133" and command == swing_mode:
            numeric = {
                "Apagado": "0",
                "Up-Down Flow": "1",
                "Up Flow": "2",
                "Down Flow": "3",
                "Up Fix": "2",
                "Above Up Fix": "3",
                "Middle Fix": "4",
                "Above Down Fix": "5",
                "Down Fix": "6",
            }.get(swing_mode)
            if numeric is not None:
                command = numeric
        await self.coordinator.async_set_dp(self.dp_swing, command)

    async def async_set_preset_mode(self, preset_mode: str):
        if preset_mode == PRESET_NONE:
            for dp in self.preset_dps.values():
                await self.coordinator.async_set_dp(dp, False)
            return
        dp = self.preset_dps.get(preset_mode)
        if dp:
            await self.coordinator.async_set_dp(dp, True)

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
        raw_value = int(round(float(temp) * (10 ** self.scale)))
        await self.coordinator.async_set_dp(self.dp_target, raw_value)
