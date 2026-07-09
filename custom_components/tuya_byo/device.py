"""TinyTuya-backed local device wrapper."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

import tinytuya
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)
# A fresh, non-persistent connection has a real handshake cost (TCP connect +
# session-key negotiation on protocol 3.4/3.5), which is why every poll used
# to feel sluggish compared to the official app (which keeps one connection
# open). Status polling now reuses a persistent connection (see
# _get_read_device_sync), which makes frequent polling cheap, so we can afford
# a much shorter interval and still reflect changes made from the Tuya app
# quickly without hammering the device with new handshakes every few seconds.
SCAN_INTERVAL = timedelta(seconds=6)


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
        # Persistent connection used ONLY for read-only status polling (see
        # _get_read_device_sync). Writes deliberately keep using a fresh
        # connection per attempt (see _make_device_sync) -- a previous version
        # of this integration reused sockets for writes too and some Tuya 3.5
        # HVAC modules ignored or lost commands as a result. Reusing the
        # connection for reads only gives most of the speed benefit without
        # touching that known write-reliability issue.
        self._read_device = None
        # Remembers which write path (set_status/set_value/set_multiple_values)
        # actually worked last time for this device, so subsequent writes try
        # it first instead of always attempting them in a fixed order.
        self._preferred_write_path: str | None = None

    @property
    def identifiers(self):
        return {("tuya_byo", self.device_id)}

    @property
    def device_info(self):
        return {
            "identifiers": self.identifiers,
            "name": self.name,
            "manufacturer": "Tuya / Smart Life",
            "model": self.config.get("model") or self.config.get("product_name"),
            "sw_version": str(self.version),
        }

    def _make_device_sync(self):
        """Create a fresh TinyTuya device inside executor only.

        We intentionally do not cache the TinyTuya object. Some Tuya 3.5 HVAC
        modules keep stale state or ignore writes when the same object/socket is
        reused. A fresh object per command/status is slower, but far more reliable
        and avoids Home Assistant event-loop blocking warnings.
        """
        dev = tinytuya.Device(self.device_id, self.host, self.key)
        dev.set_version(self.version)
        dev.set_socketPersistent(False)
        return dev

    def _get_read_device_sync(self, fresh: bool = False):
        """Return the cached persistent connection used for status polling.

        Creating a new TinyTuya device object per poll re-does the full
        handshake every time, which is the main reason polling (and therefore
        picking up changes made from the official Tuya app) felt much slower
        than it should. Reusing one connection removes that cost; if it ever
        breaks (device rebooted, briefly dropped Wi-Fi, etc.) we transparently
        reconnect on the next call.
        """
        if fresh or self._read_device is None:
            dev = tinytuya.Device(self.device_id, self.host, self.key)
            dev.set_version(self.version)
            dev.set_socketPersistent(True)
            self._read_device = dev
        return self._read_device

    def _status_sync(self):
        try:
            return self._get_read_device_sync().status()
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Persistent status connection failed (%s), reconnecting", ex)
            self._read_device = None
            return self._get_read_device_sync(fresh=True).status()

    @staticmethod
    def _looks_success(result: Any) -> bool:
        """Best-effort success detection for TinyTuya command responses."""
        if result is None:
            return False
        if isinstance(result, dict):
            if result.get("Error") or result.get("error"):
                return False
            if result.get("success") is True:
                return True
            if result.get("result") is True:
                return True
            # TinyTuya often returns a dict with dps/devId on success.
            if "dps" in result or "devId" in result or "dps" in str(result):
                return True
        return True

    def _write_path_attempts(self, dev, dp_int: int, value: Any) -> dict[str, Any]:
        """Return {path_name: callable} for the three write styles, in the
        order they should be tried this time (preferred path first)."""
        paths = {
            "set_status": lambda: dev.set_status(value, switch=dp_int),
            "set_value": lambda: dev.set_value(dp_int, value),
            "set_multiple_values": (
                (lambda: dev.set_multiple_values({dp_int: value}))
                if hasattr(dev, "set_multiple_values")
                else None
            ),
        }
        preferred = self._preferred_write_path
        if preferred and paths.get(preferred):
            ordered = {preferred: paths[preferred]}
            ordered.update({k: v for k, v in paths.items() if k != preferred})
            return ordered
        return paths

    def _set_dp_sync(self, dp: str | int, value: Any):
        """Write a single DP using all safe TinyTuya command paths.

        Different Tuya firmwares react differently to TinyTuya helpers. For HVAC
        devices in particular, set_status() can be ignored on some modules while
        set_value() works, or vice versa. We try the most direct command path and
        fall back without raising until all paths fail. A short pause between
        fallback attempts avoids hammering the module's local socket handler with
        back-to-back reconnects, which on some firmwares makes things worse
        (slower responses, or the device briefly refusing new connections).

        Once a path is known to work for this device, it's tried first on
        subsequent writes, so the common case is a single attempt instead of
        always working through set_status -> set_value -> set_multiple_values.
        """
        dp_int = int(dp)
        errors: list[str] = []
        dev = self._make_device_sync()
        attempts = self._write_path_attempts(dev, dp_int, value)

        first = True
        for name, call in attempts.items():
            if call is None:
                continue
            if not first:
                time.sleep(0.3)
                dev = self._make_device_sync()
                call = self._write_path_attempts(dev, dp_int, value)[name]
            first = False
            try:
                result = call()
                if self._looks_success(result):
                    self._preferred_write_path = name
                    return result
                errors.append(f"{name} returned {result!r}")
            except Exception as ex:  # noqa: BLE001
                errors.append(f"{name} failed: {ex}")

        raise RuntimeError("; ".join(errors))

    def _set_dps_sync(self, values: dict[int, Any]):
        """Write several DPs in a single local command when possible.

        Sending one combined command instead of N sequential ones (each with its
        own reconnect + status refresh) is both faster and gentler on the module.
        Falls back to writing DPs one by one only if the device/tinytuya version
        can't do a multi-value write.
        """
        try:
            dev = self._make_device_sync()
            if hasattr(dev, "set_multiple_values"):
                result = dev.set_multiple_values(values)
                if self._looks_success(result):
                    return result
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("set_multiple_values failed, falling back to per-DP writes: %s", ex)

        last_result = None
        for dp_int, value in values.items():
            last_result = self._set_dp_sync(dp_int, value)
        return last_result

    async def _async_update_data(self) -> dict[str, Any]:
        last_ex: Exception | None = None
        for attempt in range(2):
            try:
                async with self._lock:
                    status = await self.hass.async_add_executor_job(self._status_sync)
                dps = status.get("dps", status) if isinstance(status, dict) else {}
                data = {str(k): v for k, v in (dps or {}).items()}
                self._enhance_mapping_from_cloud(data)
                return data
            except Exception as ex:  # noqa: BLE001
                last_ex = ex
                if attempt == 0:
                    # One quick retry before giving up: local Tuya sockets
                    # occasionally refuse back-to-back connections, and a
                    # single retry avoids flapping the entity to unavailable.
                    await asyncio.sleep(1.0)
        raise UpdateFailed(str(last_ex)) from last_ex

    async def async_set_dp(self, dp: str | int, value: Any) -> None:
        await self.async_set_dps({dp: value})

    async def async_set_dps(self, values: dict[str | int, Any]) -> None:
        """Write multiple DPs in one local command and refresh state once."""
        int_values = {int(dp): value for dp, value in values.items()}
        async with self._lock:
            await self.hass.async_add_executor_job(self._set_dps_sync, int_values)
            # Force a fresh status read immediately after writing.
            status = await self.hass.async_add_executor_job(self._status_sync)
        dps = status.get("dps", status) if isinstance(status, dict) else {}
        self.async_set_updated_data({str(k): v for k, v in (dps or {}).items()})

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
        # Only applied as a last resort when DP5 is still unmapped -- now that
        # step 1 can resolve real dp_id data from the Things Data Model
        # endpoint, this must not clobber a correctly-identified mapping for
        # devices where DP5 turns out to be something else.
        product_id = str(self.config.get("product_id") or "")
        category = str(self.config.get("category") or "")
        dp5_code = str(self.mapping.get("5", {}).get("code", "dp_5"))
        if (category == "kt" or product_id == "hrzr8mr0mtgfwwri") and dp5_code.startswith("dp_"):
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
