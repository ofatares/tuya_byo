"""Utility helpers for Tuya BYO."""
from __future__ import annotations

import ipaddress
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DEVICES_FILE, STORAGE_DIR

_LOGGER = logging.getLogger(__name__)


def private_ip(value: Any) -> str:
    try:
        ip = ipaddress.ip_address(str(value))
        return str(ip) if ip.is_private else ""
    except Exception:  # noqa: BLE001
        return ""


def storage_path(hass: HomeAssistant) -> str:
    return hass.config.path(STORAGE_DIR, DEVICES_FILE)


def load_devices_file(hass: HomeAssistant) -> list[dict[str, Any]]:
    path = Path(storage_path(hass))
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("Could not read %s: %s", path, ex)
        return []


def save_devices_file(hass: HomeAssistant, devices: list[dict[str, Any]]) -> None:
    path = Path(storage_path(hass))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(devices, indent=2, ensure_ascii=False), encoding="utf-8")
