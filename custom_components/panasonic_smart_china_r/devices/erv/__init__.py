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


ERV_PROFILES: dict[str, dict] = {
    "DCERV": {
        "run_mode_get_map": RUN_MODE_GET_MAP,
        "run_mode_set_map": RUN_MODE_SET_MAP,
        "air_volume_map":   AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_dcerv_payload,
    },
    "MIDERV": {
        "run_mode_get_map": MIDERV_RUN_MODE_GET_MAP,
        "run_mode_set_map": MIDERV_RUN_MODE_SET_MAP,
        "air_volume_map":   MIDERV_AIR_VOLUME_MAP,
        "has_run_mode":     True,
        "payload_builder":  build_miderv_payload,
    },
    "SMALLERV": {
        "run_mode_get_map": {},
        "run_mode_set_map": {},
        "air_volume_map":   SMALLERV_AIR_VOLUME_MAP,
        "has_run_mode":     False,
        "payload_builder":  build_smallerv_payload,
    },
}
