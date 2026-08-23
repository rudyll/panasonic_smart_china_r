"""冰箱（category 0100）状态查询与控制。

冰箱走独立的 FDev* 协议家族，与新风机/空调的 ADev* 协议完全不同（2026-08-22，
devSubTypeId=Fridge-42 实测确认，GET 协议来自松下官方 Web 控制页
https://app.psmartcloud.com/ca/cn/0100/<devSubTypeId>/index.html 的 JS 源码逆向）：
- usrId/deviceId/token 在请求体顶层，不在 params 里（与 LD5C 的 Info 家族一致）
- SET 端点是 FDevSetStatusInfoMqtt（不是 Web 页 JS 里调用的 FDevSetStatusInfo——
  经与独立实现 https://github.com/mcdona1d/panasonic_smart_china/pull/12
  的真实抓包比对并用无副作用回写验证，见 const.py 里的注释）
- SET payload 用 _FRIDGE_SET_KEYS 白名单从当前状态里取值再叠加要改的字段，
  不是不加甄别地整表回写——changeCode/displayCode/controlCode/fcCode/data37-49
  这类字段看着像只读派生码，回写它们没有已知依据，索性不带
"""

import asyncio
import logging
import random
from datetime import timedelta

import async_timeout
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ...api import generate_device_token, relogin_entry
from ...const import (
    AUTH_EXPIRED_ERROR_CODES,
    CONF_DEVICE_ID,
    CONF_SSID,
    CONF_UPDATE_INTERVAL,
    CONF_USR_ID,
    DEFAULT_UPDATE_INTERVAL,
    FDEV_GET_ALARM_URL,
    FDEV_GET_STATUS_URL,
    FDEV_SET_STATUS_URL,
)
from ...exceptions import LoginFailed, ReloginCooldown

_LOGGER = logging.getLogger(__name__)

_MAX_RETRIES = 3

# FDevSetStatusInfoMqtt 的 Read-Modify-Write 白名单：取自独立实现
# https://github.com/mcdona1d/panasonic_smart_china/pull/12 里对冰箱真实抓包整理出的
# _FRIDGE_SET_KEYS（该作者捕获的是另一台 devSubTypeId=Fridge-55 设备，字段集比我们
# Fridge-42 实测到的更丰富）。这里只是全量白名单，真正回写时会先与本机 GET 响应的
# 现有字段取交集，不存在的字段不会凭空补 0。
_FRIDGE_SET_KEYS = (
    "PCTempSet", "PCTempCur", "PCTempCurAlarm",
    "SCS1TempSet", "SCS1TempCur", "SCS1TempCurAlarm",
    "SCS2TempSet", "SCS2TempCur", "SCS2TempCurAlarm",
    "SCB1TempSet", "SCB1TempCur", "SCB1TempCurAlarm",
    "SCB2TempSet", "SCB2TempCur", "SCB2TempCurAlarm",
    "FCTempSet", "FCTempCur", "FCTempCurAlarm",
    "quickFreeze", "quickCooling", "vacation", "quickicing", "icingStop", "icingDeice",
    "eraseOdor", "ecoNaviSet", "speed", "RAModeCur", "SAModeCur",
    "bodyOperating", "iceDetection", "waterLack", "silver", "preservation",
    "nanoe", "freshFrozen", "smartHumi", "autoIcing", "WCModeCur",
    "SCB1ModeCur", "SCB2ModeCur", "SCB1ExtraMode", "SCB2ExtraMode",
    "PCGate1", "PCGate2", "SCGate", "SCB1Gate", "SCB2Gate", "FCGate1", "FCGate2",
    "ICGate", "gateAlarm", "ecoMode", "bodyOffline",
    "waterFresh", "PCMicroFreeze", "SCS1DryStore", "PCMilkStore",
)


def _headers(ssid: str) -> dict:
    return {
        "User-Agent": "SmartApp",
        "Content-Type": "application/json",
        "Cookie": f"SSID={ssid}",
    }


class FridgeCoordinator(DataUpdateCoordinator):
    """轮询 FDevGetStatusInfo + FDevGetAlarmInfo；SET 走 FDevSetStatusInfo。"""

    def __init__(self, hass, entry):
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"panasonic_fridge_{entry.data[CONF_DEVICE_ID]}",
            update_interval=timedelta(seconds=interval),
        )
        self.entry = entry
        self._usr_id = entry.data[CONF_USR_ID]
        self._ssid = entry.data[CONF_SSID]
        self._device_id = entry.data[CONF_DEVICE_ID]

    def _identity_body(self, request_id: int) -> dict | None:
        token = generate_device_token(self._device_id)
        if token is None:
            return None
        return {
            "id": request_id,
            "usrId": self._usr_id,
            "deviceId": self._device_id,
            "token": token,
        }

    async def _post(self, url: str, body: dict):
        session = async_get_clientsession(self.hass)
        async with async_timeout.timeout(10):
            resp = await session.post(url, json=body, headers=_headers(self._ssid), ssl=False)
            return await resp.json()

    async def _fetch_once(self) -> dict:
        body = self._identity_body(1)
        if body is None:
            raise UpdateFailed("无法生成设备 token")
        status_resp = await self._post(FDEV_GET_STATUS_URL, body)
        if not isinstance(status_resp, dict) or not isinstance(status_resp.get("results"), dict):
            return {"__error__": status_resp}
        data = dict(status_resp["results"])

        try:
            alarm_resp = await self._post(FDEV_GET_ALARM_URL, self._identity_body(2))
            if isinstance(alarm_resp, dict) and isinstance(alarm_resp.get("results"), dict):
                data["alarmList"] = alarm_resp["results"].get("alarmList", [])
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("FDevGetAlarmInfo failed for %s: %s", self._device_id, err)

        return data

    async def _async_update_data(self):
        try:
            data = await self._fetch_once()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Fridge fetch failed: {err}") from err

        if "__error__" in data:
            _LOGGER.warning(
                "Fridge response looks bad, attempting silent re-login. Raw=%s",
                data["__error__"],
            )
            try:
                self._ssid = await relogin_entry(self.hass, self.entry)
            except ReloginCooldown as err:
                raise UpdateFailed(str(err)) from err
            except LoginFailed as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            try:
                data = await self._fetch_once()
            except Exception as err:  # noqa: BLE001
                raise UpdateFailed(f"Fridge fetch (post-relogin) failed: {err}") from err
            if "__error__" in data:
                raise ConfigEntryAuthFailed(f"Still bad after re-login: {data['__error__']}")

        return data

    async def async_set_fields(self, **fields) -> None:
        """发 FDevSetStatusInfoMqtt。

        params 用 _FRIDGE_SET_KEYS 白名单里、且本机 GET 响应里确实存在的字段取值，
        叠加要改的字段一起整体发出，而不是只发变化的那一个 —— wiki 记录过 DCERV-03
        因为 SET payload 缺字段导致云端返回成功（todoId）但设备不执行，这里用同样
        的思路规避。只取白名单交集而不是全部已知标量字段，是为了不回写
        changeCode/displayCode/controlCode/fcCode/data37-49 这类看着像只读派生码、
        没有已知写入依据的字段。
        """
        status = self.data or {}
        current = {key: status[key] for key in _FRIDGE_SET_KEYS if key in status}
        params = {**current, **fields}

        token = generate_device_token(self._device_id)
        if token is None:
            raise HomeAssistantError("无法生成设备 token")

        body = {
            "id": 1,
            "usrId": self._usr_id,
            "deviceId": self._device_id,
            "token": token,
            "params": params,
        }

        err = ""
        succeeded = False
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._post(FDEV_SET_STATUS_URL, body)
                err_obj = resp.get("error") if isinstance(resp, dict) else None
                if err_obj:
                    code = str(err_obj.get("code"))
                    if code in AUTH_EXPIRED_ERROR_CODES:
                        self._ssid = await relogin_entry(self.hass, self.entry)
                        continue
                    raise HomeAssistantError(f"请求失败: {err_obj.get('message', err_obj)}")
                succeeded = True
                break
            except asyncio.TimeoutError:
                err = "请求超时"
            except HomeAssistantError:
                raise
            except Exception as e:  # noqa: BLE001
                err = str(e)

            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt + random.uniform(0, 0.5))

        if not succeeded:
            raise HomeAssistantError(f"请求失败（已重试{_MAX_RETRIES}次）: {err}")

        await asyncio.sleep(3)
        await self.async_request_refresh()
