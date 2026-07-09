"""Light platform for Tuya BYO."""
from __future__ import annotations

import logging

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATORS, DOMAIN, DP_SWITCH_LED, DP_TEMP_VALUE

_LOGGER = logging.getLogger(__name__)

# Tuya's tunable-white light DP (e.g. the ceiling-fan light) reports a plain
# relative integer range (0 = warmest .. max = coolest), not real Kelvin
# values. These are the conventional warm/cool endpoints used by virtually
# every consumer tunable-white product, so the slider lands on sensible
# values without needing device-specific calibration.
MIN_KELVIN = 2700
MAX_KELVIN = 6500

COLOR_TEMP_CODE_ALIASES = (DP_TEMP_VALUE, "temp_value", "colour_temp", "color_temp", "temp_value_v2")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    entities = []
    for dev_id, coordinator in hass.data[DOMAIN][DATA_COORDINATORS].items():
        if coordinator.find_dp(DP_SWITCH_LED):
            entities.append(TuyaBYOLight(coordinator))
    async_add_entities(entities)


class TuyaBYOLight(CoordinatorEntity, LightEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self.dp_switch = coordinator.find_dp(DP_SWITCH_LED)
        self.dp_color_temp = coordinator.find_dp(*COLOR_TEMP_CODE_ALIASES)
        self._ct_min = 0.0
        self._ct_max = 1000.0

        if self.dp_color_temp:
            meta = coordinator.mapping.get(self.dp_color_temp, {})
            values = meta.get("values", {}) if isinstance(meta, dict) else {}
            if isinstance(values, dict):
                self._ct_min = float(values.get("min", 0))
                self._ct_max = float(values.get("max", 1000))
            if self._ct_max <= self._ct_min:
                self._ct_max = self._ct_min + 1
            # Not dimmable in intensity on this device, only in color
            # temperature -- HA's color-mode model doesn't have a
            # "color-temp-only, no brightness" mode, so COLOR_TEMP is the
            # closest fit. Brightness is simply not implemented below.
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_min_color_temp_kelvin = MIN_KELVIN
            self._attr_max_color_temp_kelvin = MAX_KELVIN
        else:
            # Plain on/off panel LED -- HA still requires supported_color_modes
            # to be declared even in that case, otherwise entity registration
            # raises HomeAssistantError and the whole light platform setup
            # for this config entry fails.
            self._attr_supported_color_modes = {ColorMode.ONOFF}
            self._attr_color_mode = ColorMode.ONOFF

        self._attr_unique_id = f"{coordinator.device_id}_light"
        self._attr_name = f"{coordinator.name} luz"
        self._attr_device_info = coordinator.device_info

        # Diagnostic dump of the resolved DP mapping, mirroring climate.py --
        # enable debug logging for custom_components.tuya_byo to check this
        # in Settings > System > Logs if the color-temp control is missing
        # or wrong for a specific device.
        _LOGGER.debug(
            "%s: dp_switch=%s dp_color_temp=%s ct_min=%s ct_max=%s raw_mapping=%s raw_data=%s",
            self._attr_name,
            self.dp_switch,
            self.dp_color_temp,
            self._ct_min,
            self._ct_max,
            coordinator.mapping,
            coordinator.data,
        )

    @property
    def is_on(self):
        return bool(self.coordinator.get_dp_value(self.dp_switch, False))

    @property
    def color_temp_kelvin(self):
        if not self.dp_color_temp:
            return None
        raw = self.coordinator.get_dp_value(self.dp_color_temp)
        if raw is None:
            return None
        try:
            ratio = (float(raw) - self._ct_min) / (self._ct_max - self._ct_min)
        except (TypeError, ZeroDivisionError):
            return None
        ratio = min(1.0, max(0.0, ratio))
        # Tuya convention: 0 = warmest (lowest Kelvin), max = coolest (highest Kelvin).
        return round(MIN_KELVIN + ratio * (MAX_KELVIN - MIN_KELVIN))

    async def async_turn_on(self, **kwargs):
        values: dict[str, object] = {self.dp_switch: True}
        kelvin = kwargs.get("color_temp_kelvin")
        if self.dp_color_temp and kelvin is not None:
            ratio = (kelvin - MIN_KELVIN) / (MAX_KELVIN - MIN_KELVIN)
            ratio = min(1.0, max(0.0, ratio))
            values[self.dp_color_temp] = round(self._ct_min + ratio * (self._ct_max - self._ct_min))
        await self.coordinator.async_set_dps(values)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_dp(self.dp_switch, False)
