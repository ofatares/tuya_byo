"""TinyTuya-backed local device wrapper."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

import tinytuya
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)
SCAN_INTERVAL = timedelta(seconds=15)


class TuyaBYODevice(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator and command wrapper for a Tuya local device."""

    def __init__(self, hass: HomeAssistant, config: dict[str, Any]) -> None:
        super().__init__(hass, _LOGGER, name=f"Tuya BYO {config.get('name')}", update_interval=SCAN_INTERVAL)
        self.config = config
        self.device_id = config["id"]
        self.name = config.get("name", self.device_id)
        self.host = config.get("ip") or config.get("host")
        self.key = config.get("key") or config.get("local_key")
        self.version = float(config.get("version") or config.get("protocol_version") or 3.5)
        self.mapping = config.get("mapping") or {}
        self._device = None
        self._lock = asyncio.Lock()

    @property
    def identifiers(self):
        return {("localtuya_byo", self.device_id)}

    @property
    def device_info(self):
        return {
            "identifiers": self.identifiers,
            "name": self.name,
            "manufacturer": "Tuya / Smart Life",
            "model": self.config.get("model") or self.config.get("product_name"),
            "sw_version": str(self.version),
        }

    def _ensure_device(self):
        if self._device is None:
            dev = tinytuya.Device(self.device_id, self.host, self.key)
            dev.set_version(self.version)
            dev.set_socketPersistent(False)
            self._device = dev
        return self._device

    async def _async_call(self, func, *args, **kwargs):
        async with self._lock:
            return await self.hass.async_add_executor_job(lambda: func(*args, **kwargs))

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            dev = self._ensure_device()
            status = await self._async_call(dev.status)
            dps = status.get("dps", status) if isinstance(status, dict) else {}
            return {str(k): v for k, v in (dps or {}).items()}
        except Exception as ex:  # noqa: BLE001
            raise UpdateFailed(str(ex)) from ex

    async def async_set_dp(self, dp: str | int, value: Any) -> None:
        dev = self._ensure_device()
        await self._async_call(dev.set_value, int(dp), value)
        await self.async_request_refresh()

    def find_dp(self, *codes: str) -> str | None:
        wanted = set(codes)
        for dp, meta in self.mapping.items():
            if meta.get("code") in wanted:
                return str(dp)
        return None

    def get_dp_value(self, dp: str | int, default=None):
        return (self.data or {}).get(str(dp), default)
