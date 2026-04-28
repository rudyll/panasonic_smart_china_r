"""DCERV 系列新风机共用常量和 payload 构造。"""

# GET/SET 三端均用 48-53（2026-04-22 实测确认）
RUN_MODE_GET_MAP: dict[int, str] = {
    48: "热交换",
    49: "静音",
    50: "普通换气",
    51: "内循环",
    52: "混风",
    53: "自动ECO",
    # 旧固件 / 初始状态可能返回 0-5（与 48-53 一一对应）
    0: "热交换",
    1: "静音",
    2: "普通换气",
    3: "内循环",
    4: "混风",
    5: "自动ECO",
}

RUN_MODE_SET_MAP: dict[str, int] = {
    "热交换": 48,
    "静音": 49,
    "普通换气": 50,
    "内循环": 51,
    "混风": 52,
    "自动ECO": 53,
}

AIR_VOLUME_MAP: dict[int, str] = {
    0: "弱",
    1: "强",
}

# MidERV 运行模式（来自参考仓库实测，值域 0/2/3/4）
MIDERV_RUN_MODE_GET_MAP: dict[int, str] = {
    0: "热交换",
    2: "内循环",
    3: "睡眠",
    4: "自动ECO",
}

MIDERV_RUN_MODE_SET_MAP: dict[str, int] = {
    "热交换": 0,
    "内循环": 2,
    "睡眠": 3,
    "自动ECO": 4,
}

MIDERV_AIR_VOLUME_MAP: dict[int, str] = {1: "低", 2: "中", 3: "高"}

# SmallERV 风量（值 1/3，跳过 2）
SMALLERV_AIR_VOLUME_MAP: dict[int, str] = {1: "低", 3: "高"}


def build_dcerv_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
    """构造 DCERV-03 完整 SET payload（来自 App 源码 DevStatusSetBean）。

    所有字段默认 255（skip），tH/tMin 默认 127，overrides 覆盖需要改的字段。
    """
    p: dict = {
        "deviceId": device_id, "token": token, "usrId": usr_id,
        "runSta": 255, "runM": 255, "airVo": 255,
        "preSet": 255, "preM": 255, "holM": 255,
        "pmSen": 255, "coSen": 255, "tvSen": 255,
        "userSupWind": 255, "userExhWind": 255,
        "aircJoi": 255, "oaFilEx": 255,
    }
    for i in range(1, 7):
        p[f"tSta{i}"]  = 255
        p[f"tM{i}"]    = 255
        p[f"tWind{i}"] = 255
        p[f"tSet{i}"]  = 255
        p[f"tH{i}"]    = 127
        p[f"tMin{i}"]  = 127
        p[f"tWeek{i}"] = 255
    p.update(overrides)
    return p


def build_miderv_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
    """构造 MidERV 完整 SET payload（字段来自参考仓库 SAFE_CONTROL_KEYS）。"""
    p: dict = {
        "deviceId": device_id, "token": token, "usrId": usr_id,
        "runSta": 255, "runM": 255, "airVo": 255,
        "preM": 255, "autoSen": 255, "coldF": 255,
        "saSet": 255, "HeatM": 255, "holM": 255,
        "oaFilCl": 255, "raFilCl": 255, "raFilEx": 255,
        "saFilCl": 255, "oaFilEx": 255, "saFilEx": 255,
        # MidERV 定时器：on/off 各一组，不是 DCERV 的 1-6 循环
        "tOnH": 127, "tOnMin": 127, "tOnSta": 255,
        "tOffH": 127, "tOffMin": 127, "tOffSta": 255,
    }
    p.update(overrides)
    return p


def build_smallerv_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
    """构造 SmallERV 完整 SET payload。"""
    p: dict = {
        "deviceId": device_id, "token": token, "usrId": usr_id,
        "runSta": 255, "airVo": 255,
        "filSet": 255, "oaFilExPM": 255, "saFilEx": 255,
        "tOnH": 127, "tOnMin": 127, "tOnSta": 255,
        "tOffH": 127, "tOffMin": 127, "tOffSta": 255,
        "holM": 255,
    }
    p.update(overrides)
    return p


def detect_erv_profile(status_data: dict) -> str:
    """根据 GET 响应字段特征识别 ERV 机型。"""
    if "filSet" in status_data or "oaFilExPM" in status_data:
        return "SMALLERV"
    # runM 48-53 是 DCERV 独有范围，优先判断，避免被 autoSen/coldF 误判为 MIDERV
    run_m = status_data.get("runM")
    if run_m is not None:
        try:
            if 48 <= int(run_m) <= 53:
                return "DCERV"
        except (TypeError, ValueError):
            pass
    if "autoSen" in status_data or "coldF" in status_data:
        return "MIDERV"
    return "DCERV"


# 各机型额外 select 实体配置
# 每项：field=payload字段, get_map=GET值→显示名, suffix=unique_id后缀, name_suffix=实体名后缀, icon
_DCERV_EXTRA_SELECTS = [
    {"field": "preSet",       "get_map": {0: "标准模式", 1: "正压模式", 2: "自定义模式"},
     "suffix": "pressure_mode",    "name_suffix": "压差模式",        "icon": "mdi:gauge"},
    {"field": "preM",         "get_map": {0: "弱", 1: "中", 2: "强"},
     "suffix": "pressure_level",   "name_suffix": "正压强度",        "icon": "mdi:gauge-low"},
    {"field": "userSupWind",  "get_map": {0: "0%", 20: "20%", 40: "40%", 60: "60%", 80: "80%", 100: "100%"},
     "suffix": "supply_wind",      "name_suffix": "自定义送风量",    "icon": "mdi:arrow-up-circle-outline"},
    {"field": "userExhWind",  "get_map": {0: "0%", 20: "20%", 40: "40%", 60: "60%", 80: "80%", 100: "100%"},
     "suffix": "exhaust_wind",     "name_suffix": "自定义排风量",    "icon": "mdi:arrow-down-circle-outline"},
    {"field": "oaFilEx",      "get_map": {0: "90天", 1: "120天", 2: "150天", 3: "180天"},
     "suffix": "oa_filter_cycle",  "name_suffix": "外滤网更换周期",  "icon": "mdi:air-filter"},
    {"field": "pmSen",        "get_map": {0: "35 µg/m³", 1: "50 µg/m³", 2: "75 µg/m³"},
     "suffix": "pm25_sensitivity", "name_suffix": "PM2.5 触发阈值", "icon": "mdi:blur"},
    {"field": "coSen",        "get_map": {0: "800 ppm", 1: "1000 ppm", 2: "1500 ppm"},
     "suffix": "co2_sensitivity",  "name_suffix": "CO₂ 触发阈值",   "icon": "mdi:molecule-co2"},
    {"field": "tvSen",        "get_map": {0: "低", 1: "高"},
     "suffix": "tvoc_sensitivity", "name_suffix": "TVOC 触发阈值",  "icon": "mdi:air-purifier"},
]

_MIDERV_EXTRA_SELECTS = [
    {"field": "saFilEx",      "get_map": {1: "60天", 2: "90天", 3: "120天"},
     "suffix": "sa_filter_ex",     "name_suffix": "PM2.5滤网更换周期",  "icon": "mdi:air-filter"},
    {"field": "raFilEx",      "get_map": {0: "180天", 1: "210天", 2: "240天", 3: "270天", 4: "300天", 5: "330天", 6: "365天"},
     "suffix": "ra_filter_ex",     "name_suffix": "回风滤网更换周期",    "icon": "mdi:air-filter"},
    {"field": "saFilCl",      "get_map": {0: "30天", 1: "60天"},
     "suffix": "sa_filter_cl",     "name_suffix": "PM2.5滤网清洗提醒",  "icon": "mdi:broom"},
    {"field": "raFilCl",      "get_map": {0: "30天", 1: "60天"},
     "suffix": "ra_filter_cl",     "name_suffix": "回风滤网清洗提醒",    "icon": "mdi:broom"},
]

ERV_PROFILES: dict[str, dict] = {
    "DCERV": {
        "run_mode_get_map": RUN_MODE_GET_MAP,
        "run_mode_set_map": RUN_MODE_SET_MAP,
        "air_volume_map":   AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_dcerv_payload,
        "extra_selects":    _DCERV_EXTRA_SELECTS,
    },
    "MIDERV": {
        "run_mode_get_map": MIDERV_RUN_MODE_GET_MAP,
        "run_mode_set_map": MIDERV_RUN_MODE_SET_MAP,
        "air_volume_map":   MIDERV_AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_miderv_payload,
        "extra_selects":    _MIDERV_EXTRA_SELECTS,
    },
    "SMALLERV": {
        "run_mode_get_map": {},
        "run_mode_set_map": {},
        "air_volume_map":   SMALLERV_AIR_VOLUME_MAP,
        "has_run_mode":     False,
        "payload_builder":  build_smallerv_payload,
        "extra_selects":    [],
    },
}
