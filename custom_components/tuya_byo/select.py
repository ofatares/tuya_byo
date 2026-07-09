"""Select platform for Tuya BYO."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_MODE

LABELS = {
    "fan_direction": "dirección",
    "work_mode": "modo luz",
    "temp_unit_convert": "unidad temperatura",
    "swing_mode": "modo swing",
    "fan_speed_enum": "velocidad ventilador",
    "fan_mode": "modo ventilador",
    "wind_speed": "velocidad ventilador",
    "fresh_air": "aire fresco",
    "energy": "nivel eco",
}

ICONS = {
    "fresh_air": "mdi:air-filter",
    "energy": "mdi:leaf",
    "fan_speed_enum": "mdi:fan",
    "fan_mode": "mdi:fan",
    "wind_speed": "mdi:fan",
    "work_mode": "mdi:palette",
    "fan_direction": "mdi:rotate-3d-variant",
}

# Per-code raw-value -> Spanish label overrides, for DPs whose options are
# plain numbers/codes with no human meaning published by Tuya. Best-effort
# inferred from the equivalent named options in Tuya's own app; verify
# against the physical unit before trusting a specific position.
VALUE_LABELS: dict[str, dict[str, str]] = {}

# Generic raw-value -> Spanish fallback, applied to any select entity whose
# code isn't in VALUE_LABELS above. Tuya's Cloud API returns enum options in
# English regardless of the account's locale, which is why plain selects
# (aire fresco, nivel eco, dirección del ventilador, modo de la luz...) showed
# a mix of Spanish entity names with English option values.
GENERIC_VALUE_LABELS: dict[str, str] = {
    "off": "Apagado",
    "on": "Encendido",
    "auto": "Automático",
    "low": "Bajo",
    "mid": "Medio",
    "middle": "Medio",
    "medium": "Medio",
    "high": "Alto",
    "forward": "Hacia adelante",
    "reverse": "Hacia atrás",
    "white": "Blanco",
    "colour": "Color",
    "color": "Color",
    "scene": "Escena",
    "music": "Música",
    "l1": "Nivel 1",
    "l2": "Nivel 2",
    "l3": "Nivel 3",
}

# "up_down_sweep"/"up_down_freeze" (vertical swing sweep + fixed position) and
# "sleep" are wired directly into the climate entity (native swing_mode /
# preset_mode, see climate.py), so they're excluded here to avoid a duplicate
# entity for the same DP.
CLIMATE_OWNED_CODES = {
    DP_MODE, "fan_speed", "fan_speed_enum", "fan_mode", "wind_speed", "windspeed",
    "up_down_sweep", "up_down_freeze", "sleep",
}

# Internal/administrative or non-functional-on-these-models DPs that aren't
# useful as user-facing controls: billing/display config on the unit's own
# panel (kwh, money, style), a read-only-ish air quality description better
# suited as a sensor, the device's own display temperature unit (HA already
# shows Celsius regardless), an unidentified "wind" duplicate, and horizontal
# swing/freeze which the user confirmed doesn't work on these units.
EXCLUDED_CODES = {
    "airquality", "kwh", "money", "style", "temp_unit_convert", "wind",
    "left_right_sweep", "left_right_freeze",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            if code.startswith("dp_") or code in EXCLUDED_CODES:
                continue
            values = meta.get("values", {}) if isinstance(meta, dict) else {}
            options = values.get("range") if isinstance(values, dict) else None
            # Tuya's Things Data Model reports types as lowercase ('enum',
            # 'bool', 'value'); some other Cloud paths in this integration
            # use a capitalised convention ('Enum'). Compare case-insensitively
            # so real enum DPs aren't silently skipped depending on which
            # source populated the mapping -- this was hiding sleep,
            # fresh_air, energy level, and all four swing sweep/freeze DPs.
            is_enum = str(meta.get("type", "")).lower() == "enum"
            if is_enum and isinstance(options, list) and options and code not in CLIMATE_OWNED_CODES:
                entities.append(TuyaBYOSelect(coordinator, str(dp), code, [str(v) for v in options]))
    async_add_entities(entities)


class TuyaBYOSelect(CoordinatorEntity, SelectEntity):
    def __init__(self, coordinator, dp: str, code: str, options: list[str]) -> None:
        super().__init__(coordinator)
        self.dp = dp
        self.code = code
        specific = VALUE_LABELS.get(code, {})
        self._value_to_label: dict[str, str] = {}
        for value in options:
            if value in specific:
                self._value_to_label[value] = specific[value]
            elif value.lower() in GENERIC_VALUE_LABELS:
                self._value_to_label[value] = GENERIC_VALUE_LABELS[value.lower()]
        self._label_to_value = {v: k for k, v in self._value_to_label.items()}
        self._attr_options = [self._value_to_label.get(o, o) for o in options]
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_select"
        label = LABELS.get(code, code.replace("_", " "))
        self._attr_name = f"{coordinator.name} {label}"
        self._attr_device_info = coordinator.device_info
        icon = ICONS.get(code)
        if icon:
            self._attr_icon = icon

    @property
    def current_option(self):
        value = self.coordinator.get_dp_value(self.dp)
        if value is None:
            return None
        return self._value_to_label.get(str(value), str(value))

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_dp(self.dp, self._label_to_value.get(option, option))
