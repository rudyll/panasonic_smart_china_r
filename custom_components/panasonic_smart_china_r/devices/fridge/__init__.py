"""松下冰箱（category=0100 / devSubTypeId=Fridge-15）共用常量和 payload 构造。

协议来自 App 抓包（2026-09-04）：
- GET 端点: FDevGetStatusInfo  → 身份顶层（无 params 包裹，无 uiVersion），无 xtoken 头
- SET 端点: FDevSetStatusInfo  → 身份顶层 + params 包裹控制字段，无 xtoken 头
- SET skip 规则: 25 个可写字段全部包含；未修改字段填当前状态值（非 255）
- SET 独有标志位: zhencaiSet=0, isTodoLimit=1（GET 不返回）
"""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# ==============================================================
# SET payload 默认字段（必须完整包含抓包请求中的 25 项）
# ==============================================================
_SET_FIELDS: tuple[str, ...] = (
    "zhencaiSet",   # 固定 0
    "isTodoLimit",  # 固定 1
    "ecoNaviSet",
    "quickFreeze",
    "WCModeCur",
    "freshFrozen",
    "quickicing",
    "preservation",
    "RAModeCur",
    "PCTempSet",
    "FCTempSet",
    "nanoe",
    "autoIcing",
    "icingDeice",
    "smartHumi",
    "SCB1ModeCur",
    "SCB1TempSet",
    "SCS1TempSet",
    "SCB2ModeCur",
    "SCB2TempSet",
    "SCS2TempSet",
    "silver",
    "icingStop",
    "SAModeCur",
    "vacation",
)

MAX_RETRIES = 3

# SET 独有字段的固定值（不跟随状态）
_SET_FLAG_DEFAULTS: dict[str, int] = {
    "zhencaiSet": 0,
    "isTodoLimit": 1,
}

# ==============================================================
# 温度设定范围
# ==============================================================
# 冷藏室 (PC): 1~7°C
PC_TEMP_OPTIONS: dict[int, str] = {t: f"{t} °C" for t in range(1, 8)}
# 冷冻室 (FC): -25~-17°C
FC_TEMP_OPTIONS: dict[int, str] = {t: f"{t} °C" for t in range(-25, -16)}

# --------------------------------------------------------------
# 变温室（SCB1 / SCB2）复合模式选项定义
# 映射结构: "显示标签": {"ModeCur": x, "TempSet": y, "SCSTempSet": z}
# --------------------------------------------------------------
SCB_COMPOSITE_OPTIONS: dict[str, dict[str, int]] = {
    # 基础控温模式 (ModeCur=0, SCSTempSet=0, TempSet=-17~7)
    f"{t} °C": {"ModeCur": 0, "TempSet": t, "SCSTempSet": 0}
    for t in range(-17, 8)
}

# 挂载特殊功能模式（注意：将原来的 '℃' 统一改为 '°C'）
SCB_COMPOSITE_OPTIONS.update({
    "新鲜冻结": {"ModeCur": 1, "TempSet": 3, "SCSTempSet": 0},
    "-3 °C微冻": {"ModeCur": 2, "TempSet": 1, "SCSTempSet": 0},
    "干燥臻藏": {"ModeCur": 3, "TempSet": 2, "SCSTempSet": 0},
})

# ==============================================================
# 传感器字段 → 规格配置（名称、单位、图标、无效值）
# ==============================================================
SENSOR_INVALID_VALUES: dict[str, frozenset[int]] = {
    "PCTempCur": frozenset({127, 255}),
    "FCTempCur": frozenset({127, 255}),
    "SCB1TempCur": frozenset({127, 255}),
    "SCB2TempCur": frozenset({127, 255}),
    "PCTempCurAlarm": frozenset({255}),
    "FCTempCurAlarm": frozenset({255}),
    "SCB1TempCurAlarm": frozenset({255}),
    "SCB2TempCurAlarm": frozenset({255}),
    "PCTempSetAlarm": frozenset({255}),
}

def is_invalid_sensor_value(key: str, value: Any) -> bool:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return False
    return numeric in SENSOR_INVALID_VALUES.get(key, ())

# ==============================================================
# SET payload / 头部 / 请求体 构造
# ==============================================================
def build_fridge_payload(current_status: dict, overrides) -> dict:
    """构造 SET 请求的 params 字段。

    Args:
        current_status: 最近一次 GET 返回的 results（用于未修改字段默认值）
        **overrides: 要修改的字段 → 新值
    """
    p: dict[str, Any] = {}
    for field in _SET_FIELDS:
        if field in _SET_FLAG_DEFAULTS:
            p[field] = _SET_FLAG_DEFAULTS[field]
        else:
            cur = current_status.get(field, 0)
            try:
                p[field] = int(cur) if cur is not None and cur != "" else 0
            except (TypeError, ValueError):
                p[field] = 0
    for k, v in overrides.items():
        p[k] = v
    return p

def build_get_body(
        request_id: int, device_id: str, token: str, usr_id: str
) -> dict:
    """构造 GET 请求体（Info 家族顶层身份格式）。"""
    return {
        "id": request_id,
        "usrId": usr_id,
        "deviceId": device_id,
        "token": token,
    }

def build_set_body(
        request_id: int,
        device_id: str,
        token: str,
        usr_id: str,
        params: dict,
) -> dict:
    """构造 SET 请求体（身份顶层 + params 子对象）。"""
    return {
        "id": request_id,
        "usrId": usr_id,
        "deviceId": device_id,
        "token": token,
        "params": params,
    }

def build_headers(ssid: str) -> dict:
    """构造 GET/SET 请求头。"""
    return {
        "User-Agent": "SmartApp",
        "Content-Type": "application/json",
        "Cookie": f"SSID={ssid}",
    }

def refresh_ssid_headers(headers: dict, ssid: str) -> None:
    """重登后就地更新 Cookie。"""
    headers["Cookie"] = f"SSID={ssid}"

# ==============================================================
# 实体配置 specs
# ==============================================================
WC_MODE_OPTIONS: dict[int, str] = {
    0: "蔬果保鲜",
    1: "红酒珍藏",
}

SELECT_MODE_SPECS: tuple[dict, ...] = (
    {
        "field": "WCModeCur",
        "name_suffix": "保鲜模式",
        "unique_suffix": "wc_mode_cur",
        "icon": "mdi:glass-wine",
        "options_map": WC_MODE_OPTIONS,
    },
)

SWITCH_SPECS: tuple[dict, ...] = (
    {"field": "smartHumi", "name_suffix": "智能控湿", "icon": "mdi:water-percent"},
    {"field": "nanoe", "name_suffix": "nanoe 纳诺怡", "icon": "mdi:atom"},
    {"field": "quickFreeze", "name_suffix": "快速冷冻", "icon": "mdi:snowflake"},
    {"field": "autoIcing", "name_suffix": "自动制冰", "icon": "mdi:ice-cream"},
    {"field": "icingDeice", "name_suffix": "制冰清洁", "icon": "mdi:ice-cream"},
    {"field": "ecoNaviSet", "name_suffix": "节能导航", "icon": "mdi:leaf"},
)

# 单字段温度控制 (冷藏室/冷冻室)
SELECT_TEMP_SPECS: tuple[dict, ...] = (
    {
        "field": "PCTempSet",
        "name_suffix": "冷藏室温度设定",
        "unique_suffix": "pc_temp_set",
        "icon": "mdi:thermometer",
        "options_map": PC_TEMP_OPTIONS,
    },
    {
        "field": "FCTempSet",
        "name_suffix": "冷冻室温度设定",
        "unique_suffix": "fc_temp_set",
        "icon": "mdi:thermometer-chevron-down",
        "options_map": FC_TEMP_OPTIONS,
    },
)

# 多字段联动控制 (变温室 1 & 2)
SELECT_SCB_SPECS: tuple[dict, ...] = (
    {
        "mode_field": "SCB1ModeCur",
        "temp_field": "SCB1TempSet",
        "scs_field": "SCS1TempSet",
        "name_suffix": "变温室 1 设定",
        "unique_suffix": "scb1_composite_select",
        "icon": "mdi:thermometer-lines",
        "options_map": SCB_COMPOSITE_OPTIONS,
    },
    {
        "mode_field": "SCB2ModeCur",
        "temp_field": "SCB2TempSet",
        "scs_field": "SCS2TempSet",
        "name_suffix": "变温室 2 设定",
        "unique_suffix": "scb2_composite_select",
        "icon": "mdi:thermometer-lines",
        "options_map": SCB_COMPOSITE_OPTIONS,
    },
)