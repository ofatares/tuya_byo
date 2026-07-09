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
        super().__init__(
            hass,
            _LOGGER,
            name=f"Tuya BYO {config.get('name')}",
            update_interval=SCAN_INTERVAL,
        )
        self.config = config
        self.device_id = config["id"]
        self.name = config.get("name", self.device_id)
        self.host = config.get("ip") or config.get("host")
        self.key = config.get("key") or config.get("local_key")
        self.version = float(config.get("version") or config.get("protocol_version") or 3.5)
        self.mapping = config.get("mapping") or {}
        self.cloud_model = config.get("cloud_model") or []
        self.cloud_status = config.get("cloud_status") or {}
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

    def _ensure_device_sync(self):
        """Create TinyTuya device inside executor only."""
        if self._device is None:
            dev = tinytuya.Device(self.device_id, self.host, self.key)
            dev.set_version(self.version)
            dev.set_socketPersistent(False)
            self._device = dev
        return self._device

    def _status_sync(self):
        dev = self._ensure_device_sync()
        return dev.status()

    def _set_dp_sync(self, dp: str | int, value: Any):
        dev = self._ensure_device_sync()
        return dev.set_value(int(dp), value)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            async with self._lock:
                status = await self.hass.async_add_executor_job(self._status_sync)
            dps = status.get("dps", status) if isinstance(status, dict) else {}
            data = {str(k): v for k, v in (dps or {}).items()}
            self._enhance_mapping_from_cloud(data)
            return data
        except Exception as ex:  # noqa: BLE001
            raise UpdateFailed(str(ex)) from ex

    async def async_set_dp(self, dp: str | int, value: Any) -> None:
        async with self._lock:
            await self.hass.async_add_executor_job(self._set_dp_sync, dp, value)
        await self.async_request_refresh()

    def find_dp(self, *codes: str) -> str | None:
        wanted = set(codes)
        for dp, meta in self.mapping.items():
            if meta.get("code") in wanted:
                return str(dp)
        return None


    def _enhance_mapping_from_cloud(self, data: dict[str, Any]) -> None:
        """Infer missing DP metadata from Tuya Cloud model/status.

        Best case: Cloud returns dp_id and we can map it exactly.
        Fallback: Cloud returns only code/value; we map only if the current value
        uniquely identifies one local DP. Ambiguous boolean values are left as dp_N.
        """
        # 1) Exact Cloud entries with dp_id.
        for item in self.cloud_model or []:
            if not isinstance(item, dict):
                continue
            dp_id = item.get("dp_id") or item.get("dpId") or item.get("id")
            code = item.get("code") or item.get("identifier") or item.get("name")
            if dp_id is None or not code:
                continue
            dp = str(dp_id)
            self.mapping[dp] = {
                **self.mapping.get(dp, {}),
                "code": str(code),
                "name": item.get("name") or item.get("desc") or str(code),
                "type": item.get("type", self.mapping.get(dp, {}).get("type", "Unknown")),
                "values": item.get("values") or self.mapping.get(dp, {}).get("values", {}),
            }

        # 2) Product-specific safe enrichments discovered from Cloud/local data.
        product_id = str(self.config.get("product_id") or "")
        category = str(self.config.get("category") or "")
        if category == "kt" or product_id == "hrzr8mr0mtgfwwri":
            # Johnson/Midea Tuya modules report DP5 as fan mode. User confirmed.
            self.mapping.setdefault("5", {})
            self.mapping["5"].update({
                "code": "fan_speed_enum",
                "name": "Fan speed",
                "type": "Enum",
                "values": {"range": ["auto", "low", "middle", "high", "strong"]},
            })

        # 3) Value-based unique matching for Cloud status entries with no dp_id.
        mapped_codes = {str(meta.get("code")) for meta in self.mapping.values() if isinstance(meta, dict)}
        unknown_dps = [dp for dp in data if str(self.mapping.get(dp, {}).get("code", f"dp_{dp}")).startswith("dp_")]
        for code, value in (self.cloud_status or {}).items():
            code = str(code)
            if code in mapped_codes:
                continue
            candidates = [dp for dp in unknown_dps if data.get(dp) == value]
            # Avoid guessing booleans when many values are False/True.
            if len(candidates) != 1:
                continue
            dp = candidates[0]
            typ = "Boolean" if isinstance(value, bool) else "Integer" if isinstance(value, int) else "String"
            self.mapping[dp] = {
                **self.mapping.get(dp, {}),
                "code": code,
                "name": code.replace("_", " ").title(),
                "type": typ,
                "values": {},
            }

    def get_dp_value(self, dp: str | int, default=None):
        return (self.data or {}).get(str(dp), default)

    def all_dps(self) -> list[str]:
        """Return all known DPS from mapping and from live status."""
        keys = set(str(k) for k in self.mapping.keys())
        keys.update(str(k) for k in (self.data or {}).keys())
        return sorted(keys, key=lambda item: int(item) if item.isdigit() else item)

    def dp_meta(self, dp: str | int) -> dict[str, Any]:
        """Return metadata for a DP, creating diagnostic metadata for live-only DPS."""
        dp = str(dp)
        meta = self.mapping.get(dp)
        if isinstance(meta, dict):
            return meta
        value = self.get_dp_value(dp)
        if isinstance(value, bool):
            typ = "Boolean"
        elif isinstance(value, int):
            typ = "Integer"
        elif isinstance(value, float):
            typ = "Float"
        elif isinstance(value, str):
            typ = "String"
        else:
            typ = "Unknown"
        return {"code": f"dp_{dp}", "type": typ, "values": {}, "diagnostic": True}

    def dp_code(self, dp: str | int) -> str:
        return str(self.dp_meta(dp).get("code") or f"dp_{dp}")
