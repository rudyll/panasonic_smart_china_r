"""Select platform for Panasonic fresh-air devices (DCERV-03).

端点：ADevSetStatusDCERV（主云 app.psmartcloud.com/App/）
模式编码（GET/statusAll/SET 三端均实测确认 48-53，2026-04-22）：
  runM: 48=热交换, 49=静音, 50=普通换气, 51=内循环, 52=混风, 53=自动ECO
  airVo: 0=弱, 1=强
"""

import asyncio
import logging
import random

import async_timeout
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import generate_device_token, relogin_entry
from .const import CONF_DEVICE_ID, CONF_SSID, CONF_USR_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

URL_GET = "https://app.psmartcloud.com/App/ADevGetStatusDCERV"
URL_SET = "https://app.psmartcloud.com/App/ADevSetStatusDCERV"

# GET/statusAll/SET 三端均用 48-53（2026-04-22 实测确认）
RUN_MODE_GET_MAP: dict[int, str] = {
    48: "热交换",
    49: "静音",
    50: "普通换气",
    51: "内循环",
    52: "混风",
    53: "自动ECO",
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

def _build_dcerv_payload(device_id: str, token: str, usr_id: str, **overrides) -> dict:
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

_MAX_RETRIES = 3


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        FreshAirModeSelect(coordinator, entry),
        FreshAirVolumeSelect(coordinator, entry),
    ])


class _FreshAirSelect(CoordinatorEntity, SelectEntity):
    _status_key: str = ""
    _get_map: dict[int, str] = {}       # GET 值 → 标签
    _set_map: dict[str, int] | None = None  # 标签 → SET 值（None = 反转 _get_map）
    _set_field: str = ""
    _unique_suffix: str = ""
    _name_suffix: str = ""
    _req_id: int = 0

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_options = list(self._get_map.values())
        self._attr_name = f"{entry.title} {self._name_suffix}"
        self._attr_unique_id = f"panasonic_{device_id}_{self._unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="DCERV-03",
        )

    @property
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}
        raw = data.get(self._status_key)
        _LOGGER.debug(
            "%s current_option: raw=%s coordinator_keys=%s",
            self._attr_unique_id, raw, list(data.keys())[:10],
        )
        if raw is None or raw == "":
            return None
        try:
            result = self._get_map.get(int(raw))
            if result is None:
                _LOGGER.warning("%s unmapped value: %s=%r", self._attr_unique_id, self._status_key, raw)
            return result
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        label_to_set = (
            self._set_map
            if self._set_map is not None
            else {v: k for k, v in self._get_map.items()}
        )
        set_value = label_to_set.get(option)
        if set_value is None:
            raise HomeAssistantError(f"未知选项: {option}")

        entry = self._entry
        device_id = entry.data[CONF_DEVICE_ID]
        token = generate_device_token(device_id)
        if token is None:
            raise HomeAssistantError("无法生成设备 token")

        ssid = entry.data.get(CONF_SSID, "")
        usr_id = entry.data.get(CONF_USR_ID, "")
        headers = {
            "User-Agent": "SmartApp",
            "Content-Type": "application/json",
            "Cookie": f"SSID={ssid}",
        }

        params = _build_dcerv_payload(device_id, token, usr_id, **{self._set_field: set_value})
        _LOGGER.debug(
            "%s SET %s=%s (option=%r)",
            self._attr_unique_id, self._set_field, set_value, option,
        )
        self._req_id += 1
        set_resp = await self._post_with_retry(URL_SET, {"id": self._req_id, "params": params}, headers, entry)
        _LOGGER.debug("%s SET response: %s", self._attr_unique_id, set_resp)
        await self.coordinator.async_request_refresh()

    async def _post_with_retry(self, url, payload, headers, entry):
        session = async_get_clientsession(self.hass)
        err = ""
        for attempt in range(_MAX_RETRIES):
            try:
                async with async_timeout.timeout(10):
                    resp = await session.post(url, json=payload, headers=headers, ssl=False)
                    j = await resp.json()

                err_obj = j.get("error") if isinstance(j, dict) else None
                if err_obj:
                    code = str(err_obj.get("code"))
                    if code in {"3003", "3004", "4102"}:
                        new_ssid = await relogin_entry(self.hass, entry)
                        headers["Cookie"] = f"SSID={new_ssid}"
                        continue
                    raise HomeAssistantError(f"请求失败: {err_obj.get('message', err_obj)}")

                return j

            except asyncio.TimeoutError:
                err = "请求超时"
            except HomeAssistantError:
                raise
            except Exception as e:
                err = str(e)

            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt + random.uniform(0, 0.5))

        raise HomeAssistantError(f"请求失败（已重试{_MAX_RETRIES}次）: {err}")


class FreshAirModeSelect(_FreshAirSelect):
    _status_key = "runM"
    _get_map = RUN_MODE_GET_MAP
    _set_map = RUN_MODE_SET_MAP
    _set_field = "runM"
    _unique_suffix = "run_mode"
    _name_suffix = "运行模式"
    _attr_icon = "mdi:fan-auto"


class FreshAirVolumeSelect(_FreshAirSelect):
    _status_key = "airVo"
    _get_map = AIR_VOLUME_MAP
    _set_field = "airVo"
    _unique_suffix = "air_volume"
    _name_suffix = "风量"
    _attr_icon = "mdi:weather-windy"
