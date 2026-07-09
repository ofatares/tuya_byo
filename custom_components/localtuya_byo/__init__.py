"""Tuya BYO Local integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATORS, DOMAIN, PLATFORMS, CONF_DEVICES
from .device import TuyaBYODevice

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tuya BYO Local from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(DATA_COORDINATORS, {})

    devices: dict[str, dict[str, Any]] = entry.data.get(CONF_DEVICES, {})
    for dev_id, dev_cfg in devices.items():
        config = {"id": dev_id, **dev_cfg}
        coordinator = TuyaBYODevice(hass, config)
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][DATA_COORDINATORS][dev_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Tuya BYO Local."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        for dev_id in entry.data.get(CONF_DEVICES, {}):
            hass.data.get(DOMAIN, {}).get(DATA_COORDINATORS, {}).pop(dev_id, None)
    return unloaded
