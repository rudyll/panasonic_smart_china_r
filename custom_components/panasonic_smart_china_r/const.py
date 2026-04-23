from homeassistant.components.climate.const import (
    HVACMode,
    FAN_AUTO,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
)

DOMAIN = "panasonic_smart_china_r"

CONF_USR_ID = "usrId"
CONF_DEVICE_ID = "deviceId"
CONF_TOKEN = "token"
CONF_SSID = "SSID"
CONF_SENSOR_ID = "sensor_entity_id"
CONF_CONTROLLER_MODEL = "controller_model"
CONF_DEVICE_KIND = "device_kind"
CONF_UPDATE_INTERVAL = "update_interval"

# 轮询间隔（秒）：默认 60，允许 60-900 之间调整
DEFAULT_UPDATE_INTERVAL = 60
MIN_UPDATE_INTERVAL = 60
MAX_UPDATE_INTERVAL = 900

# 云端 SSID 过期/认证错误时返回的 code（可能在顶层 errorCode，或嵌套 error.code）
# 4102 = "认证错误"（2026-04-18 实测 UsrGetBindDevInfo 在 SSID 被踢后返回）
AUTH_EXPIRED_ERROR_CODES = {"3003", "3004", "4102"}

# deviceId 中间段的 category 码
CATEGORY_AC = "0900"
CATEGORY_FRESH_AIR = "0800"

DEVICE_KIND_AC = "ac"
DEVICE_KIND_FRESH_AIR = "fresh_air"


def detect_device_kind(device_id: str) -> str | None:
    """Infer device kind from the category segment of deviceId (MAC_CATEGORY_SUFFIX)."""
    parts = device_id.split("_")
    if len(parts) < 2:
        return None
    return {
        CATEGORY_AC: DEVICE_KIND_AC,
        CATEGORY_FRESH_AIR: DEVICE_KIND_FRESH_AIR,
    }.get(parts[1])

# 自定义风速常量
FAN_MIN = "Min"    # 最低
FAN_MAX = "Max"    # 最高
FAN_MUTE = "Quiet" # 静音

# === 控制器配置数据库 ===
SUPPORTED_CONTROLLERS = {
    "CZ-RD501DW2": {
        "name": "松下风管机线控器 CZ-RD501DW2",
        "temp_scale": 2,
        "hvac_mapping": {
            HVACMode.COOL: 3,
            HVACMode.HEAT: 4,
            HVACMode.DRY: 2,
            HVACMode.AUTO: 0,
        },
        # 基础风速映射 (windSet 数值)
        "fan_mapping": {
            FAN_AUTO: 10,   # 自动
            FAN_MIN: 3,     # 最低
            FAN_LOW: 4,     # 低
            FAN_MEDIUM: 5,  # 中
            FAN_HIGH: 6,    # 高
            FAN_MAX: 7,     # 最高
        },
        # 特殊模式覆盖 (仅定义静音即可，其他走通用逻辑)
        "fan_payload_overrides": {
            FAN_MUTE: {"windSet": 10, "muteMode": 1}
        }
    }
}