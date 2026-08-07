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

# LD6C（FV-25/35/50ZDP2C）映射来自松下 App 的 Ld6cBeanConvert。
LD6C_RUN_MODE_GET_MAP: dict[int, str] = {
    1: "热交换",
    4: "内循环",
    6: "自动ECO",
    7: "消毒",
}

LD6C_RUN_MODE_SET_MAP: dict[str, int] = {
    label: value for value, label in LD6C_RUN_MODE_GET_MAP.items()
}

LD6C_AIR_VOLUME_MAP: dict[int, str] = {0: "静音", 1: "低", 2: "高"}

# LD5C（FY-25ZDP1C）协议来自松下官方 Web 控制页
# https://app.psmartcloud.com/ca/cn/0800/LD5C/index.html 的 js/common/api_utility.js，
# 由 dkong5ssss 定位并经 FY-25ZDP1C 用户实机验证（本仓库 issue #11）。
# 该页无证书固定，JS 源码即官方协议：Info 家族端点 + 长驼峰字段名。
LD5C_RUN_MODE_GET_MAP: dict[int, str] = {
    0: "热交换",
    2: "内循环",
    5: "外循环",
}

LD5C_RUN_MODE_SET_MAP: dict[str, int] = {
    label: value for value, label in LD5C_RUN_MODE_GET_MAP.items()
}

LD5C_AIR_VOLUME_MAP: dict[int, str] = {1: "低", 2: "中", 3: "高"}

# Info GET 返回的长驼峰字段 → 实体代码使用的内部短字段名。
LD5C_STATUS_FIELD_MAP: dict[str, str] = {
    "runningStatus": "runSta",
    "runningMode": "runM",
    "airVolume": "airVo",
    "holidayMode": "holM",
    "oaPM25Cur": "oaPMC",
    "saPM25Cur": "saPMC",
    "raPM25Cur": "raPMC",
    "oaTempCur": "oaTeC",
    "saTempCur": "saTeC",
    "raTempCur": "raTeC",
    "oaHumidityCur": "oaHumC",
    "saHumidityCur": "saHumC",
    "raHumidityCur": "raHumC",
}

# 内部短字段名 → LD5C SET payload 的长驼峰字段名。
LD5C_SET_FIELD_MAP: dict[str, str] = {
    "runSta": "runningStatus",
    "runM": "runningMode",
    "airVo": "airVolume",
    "holM": "holidayMode",
}

# Info GET 的传感器字段在本机型全部返回占位值，真实读数只能从 MidERV 端点取。
LD5C_AUX_SENSOR_KEYS: tuple[str, ...] = ("oaPMC", "oaHumC", "oaTeC", "raFilExTL")

# SmallERV 风量来自 App 的 MiniErvBeanConvert。
SMALLERV_AIR_VOLUME_MAP: dict[int, str] = {0: "低", 1: "高"}

# 仅对已由专用端点报告和 App 截图确认的机型收敛传感器集合。
# 未列出的 profile 暂保留现有通用集合，等待各自设备报告后再收敛。
SENSOR_KEYS_BY_PROFILE: dict[str, tuple[str, ...]] = {
    "DCERV": (
        "oaPMC", "saPMC", "raPMC", "oaHumC", "raHumC",
        "oaTeC", "saTeC", "raTeC", "raCO2C", "raTVC",
        "oaFilExTL", "saFilExTL", "raFilExTL",
    ),
    "LD6C": (
        "oaPMC", "raPMC", "oaHumC", "oaTeC",
        "oaFilExTL", "saFilExTL", "raFilExTL", "resFilExTL",
    ),
    # FY-25ZDP1C 实机只提供室外三项和回风滤网寿命，其余字段是占位值。
    "LD5C": LD5C_AUX_SENSOR_KEYS,
}

# 这些机型的实时状态由各自专用端点提供；设备列表里的 statusAll 是云端缓存，
# 控制命令执行后不会刷新，也可能缺少送风温度、滤网寿命等字段。
LIVE_STATUS_PROFILES = frozenset({"DCERV", "LD6C", "LD5C"})

# 占位值必须按字段判断，不能全局过滤：例如 PM2.5 的 255 可能是真实读数，
# 而温度的 127、湿度的 255、PM2.5/CO₂ 的 65535 是协议无效值。
SENSOR_INVALID_VALUES: dict[str, frozenset[int]] = {
    "oaPMC": frozenset({65535}),
    "saPMC": frozenset({65535}),
    "raPMC": frozenset({65535}),
    "oaHumC": frozenset({255}),
    "saHumC": frozenset({255}),
    "raHumC": frozenset({255}),
    "oaTeC": frozenset({127, 255}),
    "saTeC": frozenset({127, 255}),
    "raTeC": frozenset({127, 255}),
    "raCO2C": frozenset({65535}),
    "raTVC": frozenset({255}),
    "oaFilExTL": frozenset({65535}),
    "saFilExTL": frozenset({65535}),
    "raFilExTL": frozenset({65535}),
    "resFilExTL": frozenset({65535}),
}


def is_invalid_sensor_value(key: str, value) -> bool:
    """Return whether value is a protocol sentinel for this sensor field."""
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        return False
    return numeric in SENSOR_INVALID_VALUES.get(key, ())


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
    """构造 App `MiniErvDevStatusSetBean` 对应的完整 SET payload。"""
    p: dict = {
        "deviceId": device_id, "token": token, "usrId": usr_id,
        "runSta": 255, "airVo": 255,
        # App Bean 唯一不是 skip 值的默认字段。
        "filSet": 0, "oaFilExPM": 255, "saFilEx": 255,
        "holM": 255,
    }
    for i in range(1, 7):
        # MiniErvDevStatusSetBean 将小时和分钟也覆盖为 255。
        for prefix in ("tSta", "tSet", "tH", "tMin", "tWeek"):
            p[f"{prefix}{i}"] = 255
    p.update(overrides)
    return p


def build_newdcerv_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
    """构造 App `NewDevSetBean` 对应的完整 SET payload。"""
    fields = (
        "runSta", "runM", "airVo", "preM", "holM", "autoSen", "nanoe",
        "oaPMC", "pmFstFilCl", "pmFstFilEx", "oaFilEx", "returnInFilEx",
        "InLoopFilEx",
    )
    p: dict = {
        "deviceId": device_id,
        "token": token,
        "usrId": usr_id,
        **{field: 255 for field in fields},
    }
    for i in range(1, 7):
        p[f"tSta{i}"] = 255
        p[f"tSet{i}"] = 255
        p[f"tH{i}"] = 127
        p[f"tMin{i}"] = 127
        p[f"tWeek{i}"] = 255
    p.update(overrides)
    return p


def build_ld6c_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
    """构造 App `Ld6cDevStateSetBean` 对应的完整 SET payload。"""
    fields = (
        "runSta", "runM", "airVo", "winDir", "heatM", "nanoe",
        "preSet", "preM", "holM", "pmSen", "co2Sen", "tvSen",
        "saFilCl", "oaFilCl", "resFilCl", "saFilEX", "oaFilEx",
        "resFilEx", "saFilSet", "tSet", "slfSendW", "slfOutW",
        "airBind", "clFilReset", "saFilExReset",
        "oaFilExReset", "raFilExReset", "resFilExReset", "dehumid",
        "humidSet", "breathLight",
    )
    p: dict = {
        "deviceId": device_id,
        "token": token,
        "usrId": usr_id,
        **{field: 255 for field in fields},
    }
    for i in range(1, 7):
        for prefix in ("tSta", "tM", "tWind", "tSet", "tH", "tMin", "tWeek"):
            p[f"{prefix}{i}"] = 255
    for i in range(1, 11):
        p[f"res{i}"] = 255
    p.update(overrides)
    return p


def build_ld5c_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
    """构造官方 Web 控制页 `ADevSetStatusInfoLD5C` 的完整 SET payload。

    与其他机型不同，Info 家族端点把 usrId/deviceId/token 放在请求体顶层而不是
    params 里，所以这里只返回控制字段；身份字段由 `build_set_body` 补上。
    overrides 用内部短字段名（runSta/runM/airVo/holM），这里翻译成官方长字段名。
    """
    fields = (
        "runningStatus", "runningMode", "airVolume", "heatingMode",
        "pPressureMode", "holidayMode", "autoSensitivity", "oaFilterExist",
        "saFilterClCycle", "oaFilterClCycle", "saFilterExCycle",
        "oaFilterExCycle", "saFilterExist",
        "onTimerSetting", "offTimerSetting",
    )
    p: dict = {field: 255 for field in fields}
    # 定时器的时/分用 127 表示保持不变。
    for field in ("onTimerHour", "onTimerMinute", "offTimerHour", "offTimerMinute"):
        p[field] = 127
    for field, value in overrides.items():
        p[LD5C_SET_FIELD_MAP.get(field, field)] = value
    return p


def normalize_status(profile_name: str, results: dict) -> dict:
    """把专用端点返回的字段名翻译成实体代码使用的内部字段名。"""
    if profile_name != "LD5C":
        return results
    normalized = {
        key: value
        for key, value in results.items()
        if key not in LD5C_STATUS_FIELD_MAP
    }
    for external, internal in LD5C_STATUS_FIELD_MAP.items():
        if external in results:
            normalized[internal] = results[external]
    return normalized


def build_status_body(profile: dict, request_id: int, device_id: str, token: str, usr_id: str) -> dict:
    """按 profile 的约定构造状态查询请求体。"""
    if profile.get("identity_top_level"):
        return {
            "id": request_id,
            "usrId": usr_id,
            "deviceId": device_id,
            "token": token,
        }
    return {
        "id": request_id,
        "uiVersion": 4.0,
        "params": {"usrId": usr_id, "deviceId": device_id, "token": token},
    }


def build_set_body(profile: dict, request_id: int, device_id: str, token: str, usr_id: str, params: dict) -> dict:
    """按 profile 的约定构造控制请求体。

    profile 里写死 `set_request_id` 的机型（LD5C）用固定值，与官方 Web 控制页
    发出的请求保持一致；其余机型沿用调用方的自增序号。
    """
    body_id = profile.get("set_request_id", request_id)
    if profile.get("identity_top_level"):
        return {
            "id": body_id,
            "usrId": usr_id,
            "deviceId": device_id,
            "token": token,
            "params": params,
        }
    return {"id": body_id, "params": params}


def build_headers(profile: dict, ssid: str) -> dict:
    """构造请求头；Info 家族端点还需要 Web 控制页使用的 xtoken 头。"""
    headers = {
        "User-Agent": "SmartApp",
        "Content-Type": "application/json",
        "Cookie": f"SSID={ssid}",
    }
    if profile.get("auth_xtoken"):
        headers["xtoken"] = f"SSID={ssid}"
    return headers


def refresh_ssid_headers(headers: dict, ssid: str) -> None:
    """重登后就地更新请求头里的所有 SSID 字段。"""
    headers["Cookie"] = f"SSID={ssid}"
    if "xtoken" in headers:
        headers["xtoken"] = f"SSID={ssid}"


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
     "suffix": "pressure_level",   "name_suffix": "正压强度",        "icon": "mdi:gauge-low",
     "available_when": {"field": "preSet", "value": 1}},
    {"field": "userSupWind",  "get_map": {0: "0%", 20: "20%", 40: "40%", 60: "60%", 80: "80%", 100: "100%"},
     "suffix": "supply_wind",      "name_suffix": "自定义送风量",    "icon": "mdi:arrow-up-circle-outline",
     "available_when": {"field": "preSet", "value": 2}},
    {"field": "userExhWind",  "get_map": {0: "0%", 20: "20%", 40: "40%", 60: "60%", 80: "80%", 100: "100%"},
     "suffix": "exhaust_wind",     "name_suffix": "自定义排风量",    "icon": "mdi:arrow-down-circle-outline",
     "available_when": {"field": "preSet", "value": 2}},
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
    "NEWDCERV": {
        "run_mode_get_map": RUN_MODE_GET_MAP,
        "run_mode_set_map": RUN_MODE_SET_MAP,
        "air_volume_map":   AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_newdcerv_payload,
        # App SET 请求会回传当前室外 PM2.5，控制时从 coordinator 状态复制。
        "copy_status_fields": ("oaPMC",),
        # 滤网周期等值域仍待实机确认，先不暴露错误的 DCERV 控件。
        "extra_selects":    [],
    },
    "MIDERV": {
        "run_mode_get_map": MIDERV_RUN_MODE_GET_MAP,
        "run_mode_set_map": MIDERV_RUN_MODE_SET_MAP,
        "air_volume_map":   MIDERV_AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_miderv_payload,
        "extra_selects":    _MIDERV_EXTRA_SELECTS,
    },
    "LD6C": {
        "run_mode_get_map": LD6C_RUN_MODE_GET_MAP,
        "run_mode_set_map": LD6C_RUN_MODE_SET_MAP,
        "air_volume_map":   LD6C_AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_ld6c_payload,
        # 其他设置的值域需由专用端点实测后再开放，避免发送错误控制值。
        "extra_selects":    [],
    },
    "LD5C": {
        "run_mode_get_map": LD5C_RUN_MODE_GET_MAP,
        "run_mode_set_map": LD5C_RUN_MODE_SET_MAP,
        "air_volume_map":   LD5C_AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_ld5c_payload,
        "extra_selects":    [],
        # Info 家族端点的请求形状与其他机型不同。
        "identity_top_level": True,
        "auth_xtoken":        True,
        "status_request_id":  2,
        "set_request_id":     0,
        "aux_sensor_keys":    LD5C_AUX_SENSOR_KEYS,
        # 假日模式在 SET bean 里有对应字段，但尚未实机验证，先不暴露控件。
        "has_holiday":        False,
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
