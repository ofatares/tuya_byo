"""Climate platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
try:
    from homeassistant.components.climate import HVACAction
except Exception:  # noqa: BLE001
    HVACAction = None
try:
    from homeassistant.components.climate.const import PRESET_NONE
except Exception:  # noqa: BLE001
    PRESET_NONE = "none"
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

import logging

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

FAN_LABEL_TO_VALUE = {
    "Auto": "auto",
    "Mute": "mute",
    "Low": "low",
    "Mid-Low": "mid_low",
    "Mid": "middle",
    "Mid-High": "mid_high",
    "High": "high",
    "Turbo": "turbo",
}
FAN_VALUE_TO_LABEL = {v: k for k, v in FAN_LABEL_TO_VALUE.items()}
# Some Tuya products use these aliases internally.
FAN_VALUE_TO_LABEL.update({
    "middle": "Mid",
    "medium": "Mid",
    "great": "Turbo",
    "strong": "Turbo",
    "powerful": "Turbo",
    "silence": "Mute",
    "silent": "Mute",
})

SWING_LABEL_TO_VALUE = {
    "Apagado": "off",
    "Swing vertical": "swing",
    "Up Flow": "up",
    "Down Flow": "down",
    "Up Fix": "up_fix",
    "Above Up Fix": "above_up_fix",
    "Middle Fix": "middle_fix",
    "Above Down Fix": "above_down_fix",
    "Down Fix": "down_fix",
}
SWING_VALUE_TO_LABEL = {v: k for k, v in SWING_LABEL_TO_VALUE.items()}

_LOGGER = logging.getLogger(__name__)

# Codes other than the canonical "switch"/"mode" that different Tuya HVAC
# modules use for the same function. "switch_1" in particular is extremely
# common on AC/controller products and was missing before, which meant
# dp_switch stayed unresolved and the entity fell back to whatever HVAC mode
# was last cached (showing e.g. "Cooling" even though the unit was off).
SWITCH_CODE_ALIASES = ("power", "switch_ac", "switch_1", "Power", "power_switch")
MODE_CODE_ALIASES = ("work_mode", "mode", "mode_1")


def _to_bool(value) -> bool:
    """Convert Tuya bool-like values safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "on", "open", "yes"}
    return False


def _value_from_label(label: str, table: dict[str, str]) -> str:
    return table.get(label, label)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        # Use the same alias set as TuyaBYOClimate.__init__ below, otherwise a
        # device whose mode DP is coded "work_mode" (common on Johnson/Midea
        # controllers) never passes this gate and no climate entity is created.
        if coordinator.find_dp(DP_TEMP_SET, "temp_set", "target_temp") and coordinator.find_dp(
            DP_MODE, *MODE_CODE_ALIASES
        ):
            entities.append(TuyaBYOClimate(coordinator))
    async_add_entities(entities)


class TuyaBYOClimate(CoordinatorEntity, ClimateEntity):
    """Tuya HVAC entity."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
        HVACMode.AUTO,
    ]
    _attr_preset_modes = [PRESET_NONE]
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_climate"
        self._attr_name = coordinator.name
        self._attr_device_info = coordinator.device_info

        self.dp_switch = coordinator.find_dp(DP_SWITCH, *SWITCH_CODE_ALIASES)
        self.dp_target = coordinator.find_dp(DP_TEMP_SET, "temp_set", "target_temp")
        self.dp_current = coordinator.find_dp(DP_TEMP_CURRENT, "temp_current", "current_temperature")
        self.dp_mode = coordinator.find_dp(DP_MODE, *MODE_CODE_ALIASES)
        self.dp_fan_mode = coordinator.find_dp(
            DP_FAN_SPEED,
            "fan_speed_enum",
            "wind_speed",
            "fan_mode",
            "windspeed",
        )
        self.dp_swing = coordinator.find_dp(
            "swing",
            "swing_ud",
            "swing_updown",
            "vertical_swing",
            "wind_swing",
            "air_flow",
            "up_down_sweep",
        )

        self.scale = self._target_scale()
        self._setup_temperature_limits()

        # Diagnostic: shows exactly which physical DP got assigned to which
        # control. Enable debug logging for custom_components.tuya_byo to see
        # this in Settings > System > Logs if a control is missing/wrong.
        _LOGGER.debug(
            "%s: dp_switch=%s dp_mode=%s dp_target=%s dp_current=%s "
            "dp_fan_mode=%s dp_swing=%s raw_mapping=%s raw_data=%s",
            coordinator.name,
            self.dp_switch,
            self.dp_mode,
            self.dp_target,
            self.dp_current,
            self.dp_fan_mode,
            self.dp_swing,
            coordinator.mapping,
            coordinator.data,
        )

        features = ClimateEntityFeature.TARGET_TEMPERATURE
        self._attr_fan_modes = self._build_fan_modes()
        if self._attr_fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
        self._attr_swing_modes = self._build_swing_modes()
        if self._attr_swing_modes:
            features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features = features

    def _dp_meta_values(self, dp: str | None) -> dict:
        meta = self.coordinator.mapping.get(dp, {}) if dp else {}
        vals = meta.get("values", {}) if isinstance(meta, dict) else {}
        return vals if isinstance(vals, dict) else {}

    def _target_meta_values(self) -> dict:
        return self._dp_meta_values(self.dp_target)

    def _target_scale(self) -> int:
        vals = self._target_meta_values()
        try:
            return int(vals.get("scale", 1))
        except Exception:  # noqa: BLE001
            return 1

    def _current_scale(self) -> int:
        # Unlike temp_set, most Tuya HVAC modules report temp_current as a
        # plain, unscaled degree (e.g. "31" means 31.0C), so default to 0
        # instead of reusing the target's scale. If the DP's own metadata
        # explicitly declares a scale, honour it.
        vals = self._dp_meta_values(self.dp_current)
        try:
            return int(vals.get("scale", 0))
        except Exception:  # noqa: BLE001
            return 0

    def _setup_temperature_limits(self) -> None:
        vals = self._target_meta_values()
        divider = 10 ** self.scale
        try:
            self._attr_min_temp = int(vals.get("min", 160)) / divider
        except Exception:  # noqa: BLE001
            self._attr_min_temp = 16
        try:
            self._attr_max_temp = int(vals.get("max", 310)) / divider
        except Exception:  # noqa: BLE001
            self._attr_max_temp = 31
        try:
            self._attr_target_temperature_step = int(vals.get("step", 5)) / divider
        except Exception:  # noqa: BLE001
            self._attr_target_temperature_step = 0.5
        if self._attr_target_temperature_step <= 0:
            self._attr_target_temperature_step = 0.5

    @property
    def hvac_mode(self):
        # Critical: Tuya keeps the last mode even when the unit is off.
        # The real on/off state is DP1/switch, not DP4/mode.
        if self.dp_switch:
            if not _to_bool(self.coordinator.get_dp_value(self.dp_switch, False)):
                return HVACMode.OFF
        mode = str(self.coordinator.get_dp_value(self.dp_mode, "auto"))
        return MODE_TO_HVAC.get(mode, HVACMode.AUTO)

    @property
    def hvac_action(self):
        if HVACAction is None:
            return None
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        if self.hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if self.hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return HVACAction.IDLE

    @property
    def current_temperature(self):
        val = self.coordinator.get_dp_value(self.dp_current)
        try:
            return float(val) / (10 ** self._current_scale())
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
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        options = []
        if isinstance(values, dict):
            rng = values.get("range") or values.get("options")
            if isinstance(rng, list):
                options = [str(v) for v in rng]
        # Johnson/Midea app exposes 8 modes. Use labels in HA, send raw values.
        if not options or set(options).issubset({"auto", "low", "middle", "high", "strong"}):
            return list(FAN_LABEL_TO_VALUE.keys())
        return [FAN_VALUE_TO_LABEL.get(str(v), str(v)) for v in options]

    @property
    def fan_mode(self):
        if not self.dp_fan_mode:
            return None
        value = self.coordinator.get_dp_value(self.dp_fan_mode)
        return FAN_VALUE_TO_LABEL.get(str(value), str(value)) if value is not None else None

    async def async_set_fan_mode(self, fan_mode: str):
        if not self.dp_fan_mode:
            return
        await self.coordinator.async_set_dp(self.dp_fan_mode, _value_from_label(fan_mode, FAN_LABEL_TO_VALUE))

    def _build_swing_modes(self):
        if not self.dp_swing:
            return None
        meta = self.coordinator.mapping.get(self.dp_swing, {})
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        options = []
        if isinstance(values, dict):
            rng = values.get("range") or values.get("options")
            if isinstance(rng, list):
                options = [str(v) for v in rng]
        if str(meta.get("type", "")).lower() in {"boolean", "bool"} or not options:
            # Boolean DP (or range unknown): a plain on/off toggle is all the
            # device actually supports -- presenting the full 8-position list
            # here would let the user pick a position the device will ignore
            # or reject.
            return ["Apagado", "Swing vertical"]
        return [SWING_VALUE_TO_LABEL.get(str(v), str(v)) for v in options]

    @property
    def swing_mode(self):
        if not self.dp_swing:
            return None
        value = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(value, bool):
            return "Swing vertical" if value else "Apagado"
        return SWING_VALUE_TO_LABEL.get(str(value), str(value)) if value is not None else "Apagado"

    async def async_set_swing_mode(self, swing_mode: str):
        if not self.dp_swing:
            return
        current = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(current, bool):
            await self.coordinator.async_set_dp(self.dp_swing, swing_mode != "Apagado")
        else:
            await self.coordinator.async_set_dp(self.dp_swing, _value_from_label(swing_mode, SWING_LABEL_TO_VALUE))

    async def async_set_hvac_mode(self, hvac_mode):
        # OFF must write the power DP only. Do not write "off" to mode DP.
        if hvac_mode == HVACMode.OFF:
            if self.dp_switch:
                await self.coordinator.async_set_dp(self.dp_switch, False)
            return

        # Turning on with a target mode used to be two sequential writes
        # (switch, then mode), each opening its own connection and forcing its
        # own status refresh -- roughly double the round-trip time it takes to
        # turn the unit on. Batch both DPs into a single local command instead.
        values: dict[str, Any] = {}
        if self.dp_switch:
            values[self.dp_switch] = True
        if self.dp_mode and hvac_mode in HVAC_TO_MODE:
            values[self.dp_mode] = HVAC_TO_MODE[hvac_mode]
        if values:
            await self.coordinator.async_set_dps(values)

    async def async_set_temperature(self, **kwargs):
        if ATTR_TEMPERATURE not in kwargs or not self.dp_target:
            return
        temp = kwargs[ATTR_TEMPERATURE]
        raw = int(round(float(temp) * (10 ** self.scale)))
        await self.coordinator.async_set_dp(self.dp_target, raw)
