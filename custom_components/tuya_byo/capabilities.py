"""Capability resolver for Tuya BYO.

This module turns Tuya function codes into Home Assistant capabilities.  It is
intentionally pattern based because manufacturers use many slightly different
names for the same feature.
"""
from __future__ import annotations

from typing import Any

PRIMARY_CODES = {
    "switch",
    "switch_led",
    "fan_switch",
    "temp_set",
    "temp_current",
    "humidity_current",
    "mode",
    "temp_current_f",
    "temp_set_f",
    "temp_unit_convert",
}

FAN_MODE_CODES = {
    "fan_speed",
    "fan_speed_enum",
    "fan_mode",
    "wind_speed",
    "windspeed",
    "speed",
}

CAPABILITY_PATTERNS: dict[str, tuple[str, ...]] = {
    "sleep": ("sleep", "night", "quiet_sleep", "comfort_sleep"),
    "display": ("display", "screen", "panel", "panel_light", "switch_display", "switch_panel"),
    "led": ("led", "switch_led", "light_display"),
    "mute": ("mute", "silent", "silence", "quiet", "switch_mute", "sound_mute"),
    "swing_vertical": ("swing_ud", "swing_updown", "vertical_swing", "wind_swing_ud", "up_down"),
    "swing_horizontal": ("swing_lr", "swing_leftright", "horizontal_swing", "wind_swing_lr", "left_right"),
    "swing": ("swing", "wind_swing", "swing_mode"),
    "eco": ("eco", "energy", "save", "energy_save", "econo"),
    "turbo": ("turbo", "boost", "powerful", "strong", "jet", "fast"),
    "clean": ("clean", "self_clean", "auto_clean", "mildew", "dry_clean", "inside_clean"),
    "health": ("health", "anion", "ion", "ionizer", "fresh", "uv", "steril", "plasma"),
    "beep": ("beep", "sound", "buzzer", "voice"),
    "child_lock": ("child", "lock", "child_lock"),
    "timer": ("timer", "countdown", "countdown_left"),
    "brightness": ("brightness", "bright", "bright_value"),
    "color_temperature": ("temp_value", "colour_temp", "color_temp", "temperature_color"),
}

CAPABILITY_LABELS = {
    "sleep": "sleep",
    "display": "display",
    "led": "led",
    "mute": "mute",
    "swing": "swing",
    "swing_vertical": "swing vertical",
    "swing_horizontal": "swing horizontal",
    "eco": "eco",
    "turbo": "turbo",
    "clean": "autolimpieza",
    "health": "health",
    "beep": "beep",
    "child_lock": "bloqueo infantil",
    "timer": "temporizador",
    "brightness": "brillo",
    "color_temperature": "temperatura color",
}

CLIMATE_PRESET_CAPABILITIES = {"sleep", "eco", "turbo"}
CLIMATE_SWING_CAPABILITIES = {"swing", "swing_vertical", "swing_horizontal"}
USER_SWITCH_CAPABILITIES = {"display", "led", "mute", "clean", "health", "beep", "child_lock"}


def normalise_code(code: Any) -> str:
    return str(code or "").strip().lower().replace("-", "_")


def is_diagnostic_code(code: str) -> bool:
    code = normalise_code(code)
    return not code or code.startswith("dp_")


def capability_for_code(code: Any) -> str | None:
    """Return semantic capability for a Tuya code, if one is known."""
    code_l = normalise_code(code)
    if not code_l or code_l.startswith("dp_"):
        return None
    if code_l in FAN_MODE_CODES:
        return "fan_mode"

    # More specific swing names must be tested before generic swing.
    order = (
        "swing_vertical",
        "swing_horizontal",
        "swing",
        "sleep",
        "display",
        "led",
        "mute",
        "eco",
        "turbo",
        "clean",
        "health",
        "beep",
        "child_lock",
        "timer",
        "brightness",
        "color_temperature",
    )
    for cap in order:
        if any(pattern in code_l for pattern in CAPABILITY_PATTERNS[cap]):
            return cap
    return None


def friendly_label(code: Any) -> str:
    cap = capability_for_code(code)
    if cap:
        return CAPABILITY_LABELS.get(cap, cap)
    return normalise_code(code).replace("_", " ")


def meta_type(meta: dict[str, Any]) -> str:
    return str(meta.get("type") or "").lower()


def values_dict(meta: dict[str, Any]) -> dict[str, Any]:
    values = meta.get("values") if isinstance(meta, dict) else {}
    return values if isinstance(values, dict) else {}


def enum_options(meta: dict[str, Any]) -> list[str]:
    values = values_dict(meta)
    options = values.get("range") or values.get("options") or []
    return [str(v) for v in options] if isinstance(options, list) else []


def is_boolean(meta: dict[str, Any], value: Any = None) -> bool:
    return meta_type(meta) in {"boolean", "bool"} or isinstance(value, bool)


def is_enum(meta: dict[str, Any]) -> bool:
    return meta_type(meta) == "enum" or bool(enum_options(meta))


def is_number(meta: dict[str, Any]) -> bool:
    return meta_type(meta) in {"integer", "float", "value", "number"}
