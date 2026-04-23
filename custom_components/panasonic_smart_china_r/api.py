"""云端交互辅助：登录、静默重登、token 计算。

为什么单独抽：
- 同一套逻辑 config_flow（首次登录）、climate/coordinator（SSID 过期时静默重登）都要用。
- config_flow 里的登录流程本来有重复，这里提取为 `authenticate()`。
- 静默重登用 `relogin_entry(hass, entry)`：读 entry.data 里的账号密码，
  登录后把新 SSID/familyId 原地写回 entry.data 并更新 DOMAIN 全局 session 缓存。
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import aiohttp
import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    AUTH_EXPIRED_ERROR_CODES,
    CONF_SSID,
    CONF_USR_ID,
    DOMAIN,
)
from .exceptions import LoginFailed, ReloginCooldown

_LOGGER = logging.getLogger(__name__)

URL_GET_TOKEN = "https://app.psmartcloud.com/App/UsrGetToken"
URL_LOGIN = "https://app.psmartcloud.com/App/UsrLogin"
URL_GET_DEV = "https://app.psmartcloud.com/App/UsrGetBindDevInfo"

# 静默重登冷却：松下云端单会话互踢，HA 每 60s 轮询一抢就把手机 app 踢掉。
# 冷却期内 relogin_entry 直接返回当前 SSID 不再登录，让手机 app 能稳定用一段时间。
RELOGIN_COOLDOWN_SECONDS = 600


def _extract_error_code(json_data: dict[str, Any]) -> str | None:
    """从两种错误格式里抽出 code：
    - 顶层 `errorCode`（老空调端点）
    - 嵌套 `error.code`（新风 UsrGetBindDevInfo，2026-04-18 实测）
    """
    if not isinstance(json_data, dict):
        return None
    ec = json_data.get("errorCode")
    if ec is not None:
        return str(ec)
    err = json_data.get("error")
    if isinstance(err, dict) and "code" in err:
        return str(err["code"])
    return None


def is_auth_expired(json_data: dict[str, Any] | None) -> bool:
    """云端响应是不是 SSID 过期 / 认证错误（可触发静默重登）。"""
    if not isinstance(json_data, dict):
        return False
    code = _extract_error_code(json_data)
    return code is not None and code in AUTH_EXPIRED_ERROR_CODES


def response_looks_bad(json_data: dict[str, Any] | None) -> bool:
    """响应结构不像是成功返回 —— 用来兜底触发重登。

    规则：任一错误码（顶层 errorCode 或 error.code）存在且非 "0"/""，或 `results` 缺失。
    """
    if not isinstance(json_data, dict):
        return True
    code = _extract_error_code(json_data)
    if code is not None and code not in ("0", ""):
        return True
    if "results" not in json_data:
        return True
    return False


def generate_device_token(device_id: str) -> str | None:
    """双层 SHA512：deviceId(MAC_CATEGORY_SUFFIX) → token。
    MAC/category 转大写；suffix 保持原始大小写——实测全转大写 token 校验失败。
    JS 源码 toUpperCase 对该设备型号不适用。
    """
    try:
        parts = device_id.split("_")
        if len(parts) != 3:
            _LOGGER.error("Invalid deviceId format: %s", device_id)
            return None
        mac = parts[0].upper()
        category = parts[1].upper()
        suffix = parts[2]  # 原始大小写，不能改
        if len(mac) < 6:
            _LOGGER.error("Invalid MAC in deviceId: %s", device_id)
            return None
        stoken = mac[6:] + "_" + category + "_" + mac[:6]
        inner = hashlib.sha512(stoken.encode()).hexdigest()
        return hashlib.sha512((inner + "_" + suffix).encode()).hexdigest()
    except Exception as e:  # noqa: BLE001
        _LOGGER.error("Token generation failed for %s: %s", device_id, e)
        return None


async def authenticate(
    session: aiohttp.ClientSession, username: str, password: str
) -> dict[str, Any]:
    """走完整 GetToken → Login → GetDev 流程。

    返回 dict：usrId, ssId, familyId, realFamilyId, devices。
    任何一步失败抛 LoginFailed。
    """
    headers = {"User-Agent": "SmartApp", "Content-Type": "application/json"}

    async with async_timeout.timeout(10):
        async with session.post(
            URL_GET_TOKEN,
            json={"id": 1, "uiVersion": 4.0, "params": {"usrId": username}},
            headers=headers,
            ssl=False,
        ) as resp:
            data = await resp.json()
        if "results" not in data:
            raise LoginFailed(f"GetToken failed: {data}")
        token_start = data["results"]["token"]

    pwd_md5 = hashlib.md5(password.encode()).hexdigest().upper()
    inter = hashlib.md5((pwd_md5 + username).encode()).hexdigest().upper()
    final = hashlib.md5((inter + token_start).encode()).hexdigest().upper()

    async with async_timeout.timeout(10):
        async with session.post(
            URL_LOGIN,
            json={
                "id": 2,
                "uiVersion": 4.0,
                "params": {
                    "telId": "00:00:00:00:00:00",
                    "checkFailCount": 0,
                    "usrId": username,
                    "pwd": final,
                },
            },
            headers=headers,
            ssl=False,
        ) as resp:
            login_res = await resp.json()
        if "results" not in login_res:
            raise LoginFailed(f"Login failed: {login_res}")

    res = login_res["results"]
    real_usr_id = res["usrId"]
    ssid = res["ssId"]
    family_id = res.get("familyId")
    real_family_id = res.get("realFamilyId")

    devices: dict[str, Any] = {}
    async with async_timeout.timeout(10):
        async with session.post(
            URL_GET_DEV,
            json={
                "id": 3,
                "uiVersion": 4.0,
                "params": {
                    "realFamilyId": real_family_id,
                    "familyId": family_id,
                    "usrId": real_usr_id,
                },
            },
            headers={**headers, "Cookie": f"SSID={ssid}"},
            ssl=False,
        ) as resp:
            dev_res = await resp.json()
    if "results" in dev_res and "devList" in dev_res["results"]:
        for dev in dev_res["results"]["devList"]:
            devices[dev["deviceId"]] = dev["params"]

    return {
        "usrId": real_usr_id,
        "ssId": ssid,
        "familyId": family_id,
        "realFamilyId": real_family_id,
        "devices": devices,
    }


async def relogin_entry(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """用 entry 里保存的账号密码静默重登，把新 SSID 写回 entry.data。

    返回新的 SSID。失败抛 LoginFailed（调用方可再包成 ConfigEntryAuthFailed 触发 reauth UI）。
    """
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    if not username or not password:
        raise LoginFailed("No stored credentials; reauth required")

    # 冷却窗口：避免跟手机 app 乒乓抢 session
    domain_bucket = hass.data.setdefault(DOMAIN, {})
    last_ts = domain_bucket.get("last_relogin_ts", 0)
    now = time.monotonic()
    if now - last_ts < RELOGIN_COOLDOWN_SECONDS:
        raise ReloginCooldown(
            f"Skip relogin: phone likely has session, retry in {RELOGIN_COOLDOWN_SECONDS - int(now - last_ts)}s"
        )
    domain_bucket["last_relogin_ts"] = now

    session = async_get_clientsession(hass)
    result = await authenticate(session, username, password)

    new_data = {**entry.data}
    new_data[CONF_USR_ID] = result["usrId"]
    new_data[CONF_SSID] = result["ssId"]
    if result.get("familyId") is not None:
        new_data["familyId"] = result["familyId"]
    if result.get("realFamilyId") is not None:
        new_data["realFamilyId"] = result["realFamilyId"]
    hass.config_entries.async_update_entry(entry, data=new_data)

    # 同步更新全局 session 缓存
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["session"] = {
        CONF_USR_ID: result["usrId"],
        CONF_SSID: result["ssId"],
        "familyId": result.get("familyId"),
        "realFamilyId": result.get("realFamilyId"),
        "devices": result["devices"],
    }
    _LOGGER.info("Silently re-logged in for entry %s", entry.entry_id)
    return result["ssId"]
