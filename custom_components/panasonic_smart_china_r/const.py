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
CONF_DEV_SUB_TYPE_ID = "devSubTypeId"
CONF_UPDATE_INTERVAL = "update_interval"

# 轮询间隔（秒）：默认 60，允许 60-900 之间调整
DEFAULT_UPDATE_INTERVAL = 60
MIN_UPDATE_INTERVAL = 5
MAX_UPDATE_INTERVAL = 900

# 云端 SSID 过期/认证错误时返回的 code（可能在顶层 errorCode，或嵌套 error.code）
# 4102 = "认证错误"（2026-04-18 实测 UsrGetBindDevInfo 在 SSID 被踢后返回）
AUTH_EXPIRED_ERROR_CODES = {"3003", "3004", "4102"}

# deviceId 中间段的 category 码
CATEGORY_AC = "0900"
CATEGORY_FRESH_AIR = {"0800", "0850"}  # 0850 = SmallERV 小型新风
CATEGORY_FRIDGE = "0100"

DEVICE_KIND_AC = "ac"
DEVICE_KIND_FRESH_AIR = "fresh_air"
DEVICE_KIND_FRIDGE = "fridge"


_BASE_URL = "https://app.psmartcloud.com/App/"

# 冰箱走独立的 FDev* 协议家族，与新风机/空调的 ADev* 完全不同：
# GET 端点从松下官方 Web 控制页（https://app.psmartcloud.com/ca/cn/0100/<devSubTypeId>/index.html）
# 的 JS 源码逆向确认（2026-08-22，devSubTypeId=Fridge-42 实测）。
#
# SET 端点最初误用了 Web 页 JS 里调用的 FDevSetStatusInfo（云端接受请求但未必真的
# 下发给设备——wiki 里 DCERV-03 就吃过这个亏）。经与独立实现
# https://github.com/mcdona1d/panasonic_smart_china/pull/12（作者对冰箱走过真实抓包，
# 非静态 JS 推断）比对，真正的控制端点带 Mqtt 后缀；已用无副作用探测验证：把当前
# 状态原样回写给 FDevSetStatusInfoMqtt（不改变任何字段值），实测在本设备
# （Fridge-42）上返回 200 且无 error，端点确认存在。
FDEV_GET_STATUS_URL = _BASE_URL + "FDevGetStatusInfo"
FDEV_SET_STATUS_URL = _BASE_URL + "FDevSetStatusInfoMqtt"
FDEV_GET_ALARM_URL = _BASE_URL + "FDevGetAlarmInfo"

# devSubTypeId 前缀 → (GET端点完整URL, SET端点完整URL)
_DCERV_ENDPOINT_MAP: dict[str, tuple[str, str]] = {
    "DCERV":    (_BASE_URL + "ADevGetStatusDCERV",    _BASE_URL + "ADevSetStatusDCERV"),
    "NEWDCERV": (_BASE_URL + "ADevGetStatusNewDCERV", _BASE_URL + "ADevSetStatusNewDCERV"),
    "MIDERV":   (_BASE_URL + "ADevGetStatusMidERV",   _BASE_URL + "ADevSetStatusMidERV"),
    "SMALLERV": (_BASE_URL + "ADevGetStatusSmallERV", _BASE_URL + "ADevSetStatusSmallERV"),
    "LD5C":     (_BASE_URL + "ADevGetStatusInfoLD5C", _BASE_URL + "ADevSetStatusInfoLD5C"),
    "LD6C":     (_BASE_URL + "ADevGetStatusLD6C",     _BASE_URL + "ADevSetStatusLD6C"),
}

# LD5C 的 Info 端点只返回有效的控制字段，传感器字段全是占位值；
# 真实读数来自 MidERV 端点，轮询时按白名单合并。
LD5C_AUX_GET_URL = _BASE_URL + "ADevGetStatusMidERV"


def get_dcerv_endpoints(dev_sub_type_id: str) -> tuple[str, str]:
    """按 devSubTypeId 返回 (GET URL, SET URL)，未识别时 fallback 到 DCERV。"""
    upper = (dev_sub_type_id or "").upper().replace("-", "")
    for prefix, urls in _DCERV_ENDPOINT_MAP.items():
        if upper.startswith(prefix):
            return urls
    return _DCERV_ENDPOINT_MAP["DCERV"]


def detect_device_kind(device_id: str) -> str | None:
    """Infer device kind from the category segment of deviceId (MAC_CATEGORY_SUFFIX)."""
    parts = device_id.split("_")
    if len(parts) < 2:
        return None
    cat = parts[1]
    if cat == CATEGORY_AC:
        return DEVICE_KIND_AC
    if cat in CATEGORY_FRESH_AIR:
        return DEVICE_KIND_FRESH_AIR
    if cat == CATEGORY_FRIDGE:
        return DEVICE_KIND_FRIDGE
    return None

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
