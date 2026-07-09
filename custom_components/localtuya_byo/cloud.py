"""Minimal Tuya Cloud API client for Tuya BYO Local."""
from __future__ import annotations

import functools
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import requests

_LOGGER = logging.getLogger(__name__)

BASE_URLS = {
    "eu": "https://openapi.tuyaeu.com",
    "us": "https://openapi.tuyaus.com",
    "cn": "https://openapi.tuyacn.com",
    "in": "https://openapi.tuyain.com",
}


def _sign(msg: str, key: str) -> str:
    return hmac.new(msg=msg.encode("latin-1"), key=key.encode("latin-1"), digestmod=hashlib.sha256).hexdigest().upper()


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
        payload += "".join(f"{key}:{headers[key]}\n" for key in headers.get("Signature-Headers", "").split(":") if key in headers)
        payload += "\n/" + url.split("//", 1)[-1].split("/", 1)[-1]
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

    async def async_get_specifications(self, device_id: str) -> dict[str, Any]:
        for url in (
            f"/v1.1/devices/{device_id}/specifications",
            f"/v1.0/devices/{device_id}/specifications",
            f"/v1.0/devices/{device_id}/functions",
        ):
            try:
                resp = await self.request("GET", url)
                if not resp.ok:
                    continue
                data = resp.json()
                if data.get("success"):
                    return data.get("result") or {}
            except Exception as ex:  # noqa: BLE001
                _LOGGER.debug("Spec request failed for %s at %s: %s", device_id, url, ex)
        return {}
