"""Tuya Cloud API client for Tuya BYO.

This module intentionally asks Tuya Cloud for several model/specification/status
endpoints and normalises the different response shapes. Tuya products are not
consistent across regions or product categories, so the integration must be
forgiving and diagnostic-friendly.
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import urlsplit

import requests

_LOGGER = logging.getLogger(__name__)

BASE_URLS = {
    "eu": "https://openapi.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}


def _sign(msg: str, key: str) -> str:
    return hmac.new(
        msg=msg.encode("latin-1"),
        key=key.encode("latin-1"),
        digestmod=hashlib.sha256,
    ).hexdigest().upper()


def _json_loads_maybe(value: Any) -> Any:
    """Parse a JSON string when Tuya returns JSON encoded as text."""
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{\"":
        return value
    try:
        return json.loads(stripped)
    except Exception:  # noqa: BLE001
        return value


def _normalise_values(values: Any) -> dict[str, Any]:
    """Turn Tuya values strings into dictionaries when possible."""
    values = _json_loads_maybe(values)
    if values is None:
        return {}
    if isinstance(values, dict):
        return values
    if isinstance(values, list):
        return {"range": values}
    return {"raw": values}


def _normalise_spec_item(item: dict[str, Any]) -> dict[str, Any]:
    """Normalise Tuya function/status/model entries."""
    item = _json_loads_maybe(item)
    if not isinstance(item, dict):
        return {}

    dp_id = (
        item.get("dp_id")
        or item.get("dpId")
        or item.get("dpid")
        or item.get("id")
        or item.get("pid")
    )
    code = (
        item.get("code")
        or item.get("identifier")
        or item.get("property")
        or item.get("name")
        or item.get("nameCode")
    )
    name = item.get("name") or item.get("desc") or item.get("description") or item.get("label") or code
    typ = (
        item.get("type")
        or item.get("data_type")
        or item.get("dataType")
        or item.get("propertyType")
        or item.get("schemaType")
        or "Unknown"
    )
    mode = item.get("mode") or item.get("accessMode") or item.get("access_mode") or item.get("rwFlag")
    value = item.get("value") if "value" in item else item.get("defaultValue")
    return {
        "dp_id": str(dp_id) if dp_id is not None else None,
        "code": str(code) if code is not None else None,
        "name": str(name) if name is not None else None,
        "type": str(typ),
        "mode": str(mode) if mode is not None else None,
        "value": value,
        "values": _normalise_values(
            item.get("values")
            or item.get("value_range")
            or item.get("valueRange")
            or item.get("schema")
            or item.get("property")
        ),
        "raw": item,
    }


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Extract function/status/property entries from Tuya response payloads.

    Tuya endpoints return many different shapes. Some responses include a JSON
    string under keys such as ``model`` or ``schema``. This extractor recursively
    parses those strings and walks common containers.
    """
    payload = _json_loads_maybe(payload)
    items: list[dict[str, Any]] = []

    if isinstance(payload, list):
        for item in payload:
            item = _json_loads_maybe(item)
            if isinstance(item, dict):
                # If this dict looks like an item, keep it.
                if any(k in item for k in ("code", "identifier", "dp_id", "dpId", "id", "value", "mode")):
                    items.append(item)
                # And still recurse, because services contain properties/actions/events.
                items.extend(_extract_items({k: v for k, v in item.items() if k in ("properties", "actions", "events", "functions", "status", "model", "services")}))
        return items

    if not isinstance(payload, dict):
        return items

    # A single item-shaped dict.
    if any(k in payload for k in ("code", "identifier", "dp_id", "dpId")):
        items.append(payload)

    for key, value in payload.items():
        if key in (
            "functions",
            "function",
            "status",
            "statuses",
            "properties",
            "property",
            "actions",
            "events",
            "services",
            "model",
            "schema",
            "result",
            "data",
            "dps",
            "thingModel",
            "thing_model",
        ):
            items.extend(_extract_items(value))
        elif isinstance(value, str) and value.strip()[:1] in ("{", "["):
            items.extend(_extract_items(value))
    return items


class TuyaCloudApi:
    """Small signed Tuya Cloud API wrapper."""

    def __init__(self, hass, region: str, client_id: str, secret: str, user_id: str) -> None:
        self.hass = hass
        self.base_url = BASE_URLS.get(region, BASE_URLS["eu"])
        self.client_id = client_id
        self.secret = secret
        self.user_id = user_id
        self.access_token = ""
        self.device_list: dict[str, dict[str, Any]] = {}

    def _payload(self, method: str, timestamp: str, url: str, headers: dict[str, str], body: str = "") -> str:
        payload = self.client_id + self.access_token + timestamp
        payload += method + "\n"
        payload += hashlib.sha256(body.encode("utf-8")).hexdigest()
        payload += "\n"
        payload += "".join(
            f"{key}:{headers[key]}\n"
            for key in headers.get("Signature-Headers", "").split(":")
            if key in headers
        )
        payload += "\n" + (urlsplit(url).path or url.split("?", 1)[0])
        if "?" in url:
            payload += "?" + url.split("?", 1)[1]
        return payload

    async def request(self, method: str, url: str, body: Any | None = None, headers: dict[str, str] | None = None):
        headers = headers or {}
        body_str = json.dumps(body) if body is not None else ""
        timestamp = str(int(time.time() * 1000))
        payload = self._payload(method, timestamp, url, headers, body_str)
        req_headers = {
            "client_id": self.client_id,
            "access_token": self.access_token,
            "sign": _sign(payload, self.secret),
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
            **headers,
        }
        full_url = self.base_url + url
        if method == "GET":
            func = functools.partial(requests.get, full_url, headers=req_headers, timeout=20)
        elif method == "POST":
            func = functools.partial(requests.post, full_url, headers=req_headers, data=body_str, timeout=20)
        else:
            raise ValueError(f"Unsupported method {method}")
        return await self.hass.async_add_executor_job(func)

    async def async_get_access_token(self) -> str:
        resp = await self.request("GET", "/v1.0/token?grant_type=1")
        if not resp.ok:
            return f"HTTP {resp.status_code}"
        data = resp.json()
        if not data.get("success"):
            return f"{data.get('code')}: {data.get('msg')}"
        self.access_token = data["result"]["access_token"]
        return "ok"

    async def async_get_devices(self) -> str:
        resp = await self.request("GET", f"/v1.0/users/{self.user_id}/devices")
        if not resp.ok:
            return f"HTTP {resp.status_code}"
        data = resp.json()
        if not data.get("success"):
            return f"{data.get('code')}: {data.get('msg')}"
        self.device_list = {dev["id"]: dev for dev in data.get("result", [])}
        return "ok"

    async def _get_json_result(self, url: str) -> Any | None:
        try:
            resp = await self.request("GET", url)
            if not resp.ok:
                _LOGGER.debug("Tuya Cloud %s returned HTTP %s", url, resp.status_code)
                return None
            data = resp.json()
            if not data.get("success"):
                _LOGGER.debug("Tuya Cloud %s failed: %s %s", url, data.get("code"), data.get("msg"))
                return None
            return data.get("result")
        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug("Tuya Cloud request failed for %s: %s", url, ex)
            return None

    async def async_get_device_description(self, device_id: str, product_id: str | None = None, category: str | None = None) -> dict[str, Any]:
        """Fetch all useful Cloud metadata for one device."""
        endpoints = {
            "specification_iot03": f"/v1.0/iot-03/devices/{device_id}/specification",
            "functions_iot03": f"/v1.0/iot-03/devices/{device_id}/functions",
            "status_iot03": f"/v1.0/iot-03/devices/{device_id}/status",
            "specifications_v11": f"/v1.1/devices/{device_id}/specifications",
            "specifications_v10": f"/v1.0/devices/{device_id}/specifications",
            "functions_v10": f"/v1.0/devices/{device_id}/functions",
            "status_v10": f"/v1.0/devices/{device_id}/status",
            "thing_model_v20": f"/v2.0/cloud/thing/{device_id}/model",
            "thing_shadow_v20": f"/v2.0/cloud/thing/{device_id}/shadow/properties",
            "thing_detail_v20": f"/v2.0/cloud/thing/{device_id}",
        }
        if product_id:
            endpoints.update(
                {
                    "product_functions_iot03": f"/v1.0/iot-03/products/{product_id}/functions",
                    "product_specification_iot03": f"/v1.0/iot-03/products/{product_id}/specification",
                    "product_details_iot03": f"/v1.0/iot-03/products/{product_id}",
                }
            )
        if category:
            endpoints.update(
                {
                    "category_functions_iot03": f"/v1.0/iot-03/categories/{category}/functions",
                    "category_status_iot03": f"/v1.0/iot-03/categories/{category}/status",
                }
            )

        raw: dict[str, Any] = {}
        items: list[dict[str, Any]] = []
        statuses: dict[str, Any] = {}
        by_code: dict[str, dict[str, Any]] = {}
        by_dp: dict[str, dict[str, Any]] = {}

        for name, url in endpoints.items():
            result = await self._get_json_result(url)
            if result is None:
                continue
            raw[name] = result
            extracted = _extract_items(result)
            for item in extracted:
                norm = _normalise_spec_item(item)
                code = norm.get("code")
                dp_id = norm.get("dp_id")
                if code:
                    existing = by_code.get(code, {})
                    merged = {**existing, **{k: v for k, v in norm.items() if v not in (None, "", {})}}
                    by_code[code] = merged
                    items.append(merged)
                    if norm.get("value") is not None:
                        statuses[code] = norm.get("value")
                if dp_id:
                    by_dp[dp_id] = {**by_dp.get(dp_id, {}), **norm}

            # Status endpoints sometimes return [{code,value}] directly.
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, dict) and item.get("code") and "value" in item:
                        statuses[str(item["code"])] = item.get("value")

        return {"raw": raw, "items": list(by_code.values()), "by_code": by_code, "by_dp": by_dp, "status": statuses}

    async def async_get_specifications(self, device_id: str, product_id: str | None = None, category: str | None = None) -> dict[str, Any]:
        """Backward-compatible wrapper."""
        description = await self.async_get_device_description(device_id, product_id, category)
        return {
            "functions": description.get("items", []),
            "by_code": description.get("by_code", {}),
            "by_dp": description.get("by_dp", {}),
            "status_values": description.get("status", {}),
            "raw": description.get("raw", {}),
        }
