"""Panasonic Smart China 自定义集成 — 内部异常。"""


class AuthExpired(Exception):
    """云端返回 SSID 已过期（errorCode 3003/3004）。"""


class LoginFailed(Exception):
    """UsrGetToken/UsrLogin 流程失败（账号密码错、网络错等）。"""


class ReloginCooldown(Exception):
    """冷却期内跳过静默重登 —— 让调用方把当次轮询转成 UpdateFailed，而不是触发 reauth UI。"""
