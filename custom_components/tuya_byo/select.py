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
    "sleep": "modo sleep",
    "fresh_air": "aire fresco",
    "energy": "nivel eco",
    "up_down_sweep": "swing vertical (barrido)",
    "left_right_sweep": "swing horizontal (barrido)",
    "up_down_freeze": "swing vertical (posición fija)",
    "left_right_freeze": "swing horizontal (posición fija)",
}

# "up_down_sweep" is also wired directly into the climate entity's native
# swing_mode (see climate.py), so it's excluded here to avoid a duplicate
# entity for the same DP.
CLIMATE_OWNED_CODES = {
    DP_MODE, "fan_speed", "fan_speed_enum", "fan_mode", "wind_speed", "windspeed",
    "up_down_sweep",
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for _dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        for dp in coordinator.all_dps():
            meta = coordinator.dp_meta(dp)
            code = str(meta.get("code", f"dp_{dp}"))
            if code.startswith("dp_"):
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
        self._attr_options = options
        self._attr_unique_id = f"{coordinator.device_id}_{dp}_select"
        label = LABELS.get(code, code.replace("_", " "))
        self._attr_name = f"{coordinator.name} {label}"
        self._attr_device_info = coordinator.device_info

    @property
    def current_option(self):
        value = self.coordinator.get_dp_value(self.dp)
        return str(value) if value is not None else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_dp(self.dp, option)
