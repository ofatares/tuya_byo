"""Config flow for Tuya BYO Local."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_CLIENT_ID, CONF_CLIENT_SECRET, CONF_REGION, CONF_USERNAME
from homeassistant.helpers import config_validation as cv

from .cloud import TuyaCloudApi
from .const import CONF_DEVICES, CONF_USER_ID, DOMAIN
from .util import load_devices_file, private_ip, save_devices_file

_LOGGER = logging.getLogger(__name__)

REGIONS = ["eu", "us", "cn", "in"]

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_REGION, default="eu"): vol.In(REGIONS),
        vol.Required(CONF_CLIENT_ID): cv.string,
        vol.Required(CONF_CLIENT_SECRET): cv.string,
        vol.Required(CONF_USER_ID): cv.string,
        vol.Optional(CONF_USERNAME, default="Tuya BYO Local"): cv.string,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Tuya BYO Local config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                devices = await self._build_devices(user_input)
                await self.async_set_unique_id(user_input[CONF_USER_ID])
                self._abort_if_unique_id_configured()
                data = dict(user_input)
                data[CONF_DEVICES] = {dev["id"]: dev for dev in devices}
                return self.async_create_entry(title=user_input.get(CONF_USERNAME, "Tuya BYO Local"), data=data)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception as ex:  # noqa: BLE001
                _LOGGER.exception("Unexpected error configuring Tuya BYO Local: %s", ex)
                errors["base"] = "unknown"

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    async def _build_devices(self, user_input: dict[str, Any]) -> list[dict[str, Any]]:
        api = TuyaCloudApi(
            self.hass,
            user_input[CONF_REGION],
            user_input[CONF_CLIENT_ID],
            user_input[CONF_CLIENT_SECRET],
            user_input[CONF_USER_ID],
        )
        res = await api.async_get_access_token()
        if res != "ok":
            raise InvalidAuth(res)
        res = await api.async_get_devices()
        if res != "ok":
            raise CannotConnect(res)

        existing = {dev["id"]: dev for dev in load_devices_file(self.hass) if dev.get("id")}
        devices: list[dict[str, Any]] = []

        for dev_id, cloud_dev in api.device_list.items():
            cached = existing.get(dev_id, {})
            specs = await api.async_get_specifications(dev_id)
            mapping = _mapping_from_specs(specs) or cached.get("mapping", {})
            local_ip = private_ip(cloud_dev.get("ip")) or cached.get("ip", "")
            device = {
                "id": dev_id,
                "name": cloud_dev.get("name") or cached.get("name") or dev_id,
                "key": cloud_dev.get("local_key") or cached.get("key") or "",
                "ip": local_ip,
                "version": str(cached.get("version") or "3.5"),
                "category": cloud_dev.get("category") or cached.get("category") or "",
                "product_name": cloud_dev.get("product_name") or cloud_dev.get("productName") or cached.get("product_name") or "",
                "product_id": cloud_dev.get("product_id") or cloud_dev.get("productId") or cached.get("product_id") or "",
                "mapping": mapping,
            }
            devices.append(device)

        save_devices_file(self.hass, devices)
        return devices


def _mapping_from_specs(specs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Convert Tuya Cloud specifications/functions into DP mapping."""
    result: dict[str, dict[str, Any]] = {}
    candidates = []
    if isinstance(specs, dict):
        candidates.extend(specs.get("functions") or [])
        candidates.extend(specs.get("status") or [])
    for item in candidates:
        dp_id = item.get("dp_id") or item.get("id") or item.get("dpId")
        code = item.get("code") or item.get("name")
        if dp_id is None or code is None:
            continue
        values = item.get("values") or {}
        if isinstance(values, str):
            values = {"raw": values}
        result[str(dp_id)] = {"code": code, "type": item.get("type", "Unknown"), "values": values}
    return result

class CannotConnect(Exception):
    """Cannot connect."""

class InvalidAuth(Exception):
    """Invalid auth."""
