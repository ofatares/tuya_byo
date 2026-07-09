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
    "mid": "Mid",
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

# Some devices (confirmed via debug log) report vertical sweep as plain
# numeric positions on "up_down_sweep" instead of the semantic strings above.
# Tuya's Cloud API doesn't publish human labels for these, so this mapping is
# inferred from the count/order of the equivalent options in Tuya's own app
# ("Up-Down Flow", "Up Flow", "Down Flow" -- 3 named states + an implicit
# off/base state = 4, matching the DP's range). Verify against the physical
# unit and adjust if a position doesn't match.
SWEEP_VALUE_TO_LABEL = {
    "0": "Apagado",
    "1": "Vaivén completo",
    "2": "Solo zona superior",
    "3": "Solo zona inferior",
}
SWEEP_LABEL_TO_VALUE = {v: k for k, v in SWEEP_VALUE_TO_LABEL.items()}

# "up_down_freeze" (vertical swing fixed/parked position, separate from the
# sweep on/off state above) -- folded into the same climate swing_mode list
# instead of a separate select entity, per user request. "0"/Sin fijar is
# intentionally left out here: it's represented by the shared "Apagado" entry
# built in _build_swing_modes() so there's only one "off" option, not two.
FREEZE_VALUE_TO_LABEL = {
    "1": "Fijo: Arriba",
    "2": "Fijo: Zona superior",
    "3": "Fijo: Zona media",
    "4": "Fijo: Zona inferior",
    "5": "Fijo: Abajo",
}
FREEZE_LABEL_TO_VALUE = {v: k for k, v in FREEZE_VALUE_TO_LABEL.items()}

# "sleep" DP values, seen on Gree/Midea-derived Tuya AC modules: a sleep
# temperature curve selector, not a plain on/off. Fairly standard/well-known
# convention, but still worth confirming against the physical unit.
SLEEP_VALUE_TO_LABEL = {
    "off": "Ninguno",
    "normal": "Sleep",
    "old": "Sleep (personas mayores)",
    "child": "Sleep (niños)",
}
SLEEP_LABEL_TO_VALUE = {v: k for k, v in SLEEP_VALUE_TO_LABEL.items()}

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
        # "up_down_freeze" (vertical swing fixed/parked position) folded into
        # the same swing_mode control as the sweep DP above, instead of a
        # separate select entity, so both live where the user is already
        # operating the AC.
        self.dp_swing_freeze = coordinator.find_dp("up_down_freeze")
        # "sleep" (temperature-curve selector, not on/off) surfaces inside the
        # climate card as a preset instead of a separate select entity, so
        # it's visible while actually operating the AC.
        self.dp_sleep = coordinator.find_dp("sleep")

        self.scale = self._target_scale()
        self._setup_temperature_limits()

        # Diagnostic: shows exactly which physical DP got assigned to which
        # control. Enable debug logging for custom_components.tuya_byo to see
        # this in Settings > System > Logs if a control is missing/wrong.
        _LOGGER.debug(
            "%s: dp_switch=%s dp_mode=%s dp_target=%s dp_current=%s "
            "dp_fan_mode=%s dp_swing=%s dp_swing_freeze=%s dp_sleep=%s raw_mapping=%s raw_data=%s",
            coordinator.name,
            self.dp_switch,
            self.dp_mode,
            self.dp_target,
            self.dp_current,
            self.dp_fan_mode,
            self.dp_swing,
            self.dp_swing_freeze,
            self.dp_sleep,
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
        self._attr_preset_modes = self._build_preset_modes()
        if self._attr_preset_modes and self._attr_preset_modes != [PRESET_NONE]:
            features |= ClimateEntityFeature.PRESET_MODE
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

    def _swing_tables(self) -> tuple[dict[str, str], dict[str, str]]:
        """Pick the (label->value, value->label) tables for the resolved swing DP.

        Devices whose swing DP is coded "up_down_sweep" report plain numeric
        positions instead of Tuya's usual semantic strings (up/down/up_fix/
        etc), so they need a different translation table.
        """
        meta = self.coordinator.mapping.get(self.dp_swing, {}) if self.dp_swing else {}
        if isinstance(meta, dict) and str(meta.get("code")) == "up_down_sweep":
            return SWEEP_LABEL_TO_VALUE, SWEEP_VALUE_TO_LABEL
        return SWING_LABEL_TO_VALUE, SWING_VALUE_TO_LABEL

    def _swing_is_bool(self) -> bool:
        meta = self.coordinator.mapping.get(self.dp_swing, {}) if self.dp_swing else {}
        return str(meta.get("type", "")).lower() in {"boolean", "bool"}

    def _freeze_options(self) -> list[str]:
        if not self.dp_swing_freeze:
            return []
        meta = self.coordinator.mapping.get(self.dp_swing_freeze, {})
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        rng = []
        if isinstance(values, dict):
            r = values.get("range") or values.get("options")
            if isinstance(r, list):
                rng = [str(v) for v in r]
        return [str(v) for v in rng]

    def _build_swing_modes(self):
        if not self.dp_swing and not self.dp_swing_freeze:
            return None
        options = ["Apagado"]
        if self.dp_swing:
            meta = self.coordinator.mapping.get(self.dp_swing, {})
            values = meta.get("values", {}) if isinstance(meta, dict) else {}
            rng = []
            if isinstance(values, dict):
                r = values.get("range") or values.get("options")
                if isinstance(r, list):
                    rng = [str(v) for v in r]
            if self._swing_is_bool() or not rng:
                # Boolean DP (or range unknown): a plain on/off toggle is all
                # the device actually supports -- presenting the full
                # multi-position list here would let the user pick a position
                # the device will ignore or reject.
                if "Swing vertical" not in options:
                    options.append("Swing vertical")
            else:
                _, value_to_label = self._swing_tables()
                for v in rng:
                    if str(v) == "0":
                        continue  # already covered by the shared "Apagado" entry
                    label = value_to_label.get(str(v), str(v))
                    if label not in options:
                        options.append(label)
        # Fold the fixed/parked position DP into the same list ("Fijo: ...").
        for v in self._freeze_options():
            if v == "0":
                continue  # "sin fijar" -- already covered by "Apagado"
            label = FREEZE_VALUE_TO_LABEL.get(v)
            if label and label not in options:
                options.append(label)
        return options

    @property
    def swing_mode(self):
        if not self.dp_swing and not self.dp_swing_freeze:
            return None
        if self.dp_swing:
            value = self.coordinator.get_dp_value(self.dp_swing)
            if isinstance(value, bool):
                if value:
                    return "Swing vertical"
            elif value is not None and str(value) != "0":
                _, value_to_label = self._swing_tables()
                return value_to_label.get(str(value), str(value))
        if self.dp_swing_freeze:
            value = self.coordinator.get_dp_value(self.dp_swing_freeze)
            if value is not None and str(value) != "0":
                return FREEZE_VALUE_TO_LABEL.get(str(value), str(value))
        return "Apagado"

    async def async_set_swing_mode(self, swing_mode: str):
        if not self.dp_swing and not self.dp_swing_freeze:
            return
        if swing_mode in FREEZE_LABEL_TO_VALUE or swing_mode == "Apagado":
            # A fixed position (or turning everything off) implies the sweep
            # should stop, and vice versa -- write both DPs together in one
            # command so the device doesn't briefly show a contradictory state.
            values: dict[str, Any] = {}
            if self.dp_swing:
                values[self.dp_swing] = False if self._swing_is_bool() else "0"
            if self.dp_swing_freeze:
                values[self.dp_swing_freeze] = FREEZE_LABEL_TO_VALUE.get(swing_mode, "0")
            if values:
                await self.coordinator.async_set_dps(values)
            return
        # A sweep/vaivén option -- only the sweep DP is relevant.
        if not self.dp_swing:
            return
        current = self.coordinator.get_dp_value(self.dp_swing)
        if isinstance(current, bool):
            await self.coordinator.async_set_dp(self.dp_swing, swing_mode != "Apagado")
        else:
            label_to_value, _ = self._swing_tables()
            await self.coordinator.async_set_dp(self.dp_swing, _value_from_label(swing_mode, label_to_value))

    def _build_preset_modes(self):
        if not self.dp_sleep:
            return [PRESET_NONE]
        meta = self.coordinator.mapping.get(self.dp_sleep, {})
        values = meta.get("values", {}) if isinstance(meta, dict) else {}
        rng = values.get("range") if isinstance(values, dict) else None
        if not isinstance(rng, list) or not rng:
            return [PRESET_NONE]
        return [SLEEP_VALUE_TO_LABEL.get(str(v), str(v)) for v in rng]

    @property
    def preset_mode(self):
        if not self.dp_sleep:
            return PRESET_NONE
        value = self.coordinator.get_dp_value(self.dp_sleep)
        return SLEEP_VALUE_TO_LABEL.get(str(value), str(value)) if value is not None else PRESET_NONE

    async def async_set_preset_mode(self, preset_mode: str):
        if not self.dp_sleep:
            return
        await self.coordinator.async_set_dp(self.dp_sleep, _value_from_label(preset_mode, SLEEP_LABEL_TO_VALUE))

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
