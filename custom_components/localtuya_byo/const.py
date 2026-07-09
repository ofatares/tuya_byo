"""Constants for Tuya BYO Local."""
from __future__ import annotations

DOMAIN = "localtuya_byo"
PLATFORMS = ["fan", "light", "climate", "switch", "select", "number", "sensor"]

CONF_USER_ID = "user_id"
CONF_NO_CLOUD = "no_cloud"
CONF_DEVICES = "devices"
CONF_LOCAL_KEY = "local_key"
CONF_PROTOCOL_VERSION = "protocol_version"
CONF_MAPPING = "mapping"
CONF_CATEGORY = "category"
CONF_PRODUCT_ID = "product_id"
CONF_PRODUCT_NAME = "product_name"
CONF_IP = "ip"
CONF_KEY = "key"

DATA_COORDINATORS = "coordinators"
STORAGE_DIR = "localtuya_byo"
DEVICES_FILE = "devices.json"

DP_SWITCH = "switch"
DP_SWITCH_LED = "switch_led"
DP_FAN_SWITCH = "fan_switch"
DP_FAN_SPEED = "fan_speed"
DP_FAN_DIRECTION = "fan_direction"
DP_TEMP_SET = "temp_set"
DP_TEMP_CURRENT = "temp_current"
DP_MODE = "mode"
DP_HUMIDITY_CURRENT = "humidity_current"

DP_FAN_BEEP = "fan_beep"
DP_COUNTDOWN_FAN = "countdown_left_fan"
DP_TEMP_VALUE = "temp_value"
DP_WORK_MODE = "work_mode"
DP_TEMP_UNIT = "temp_unit_convert"
DP_FAN_SPEED = "fan_speed"
