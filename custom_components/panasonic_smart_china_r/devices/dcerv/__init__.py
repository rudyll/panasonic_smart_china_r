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
