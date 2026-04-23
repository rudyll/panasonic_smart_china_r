"""Switch platform for Panasonic fresh-air devices (DCERV-03).

控制开关机（runSta 0=关 1=开）和假日模式（holM 0=关 1=开）。
"""

import asyncio
import logging
import random

import async_timeout
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import generate_device_token, relogin_entry
from .const import CONF_DEVICE_ID, CONF_SSID, CONF_USR_ID, DOMAIN
from .select import _build_dcerv_payload

_LOGGER = logging.getLogger(__name__)

URL_SET = "https://app.psmartcloud.com/App/ADevSetStatusDCERV"

_MAX_RETRIES = 3


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        FreshAirPowerSwitch(coordinator, entry),
        FreshAirHolidaySwitch(coordinator, entry),
    ])


class _FreshAirSwitchBase(CoordinatorEntity, SwitchEntity):

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._req_id = 0

    async def _set_field(self, field: str, value: int) -> None:
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

        params = _build_dcerv_payload(device_id, token, usr_id, **{field: value})
        _LOGGER.debug("%s SET %s=%s", self._attr_unique_id, field, value)

        self._req_id += 1
        set_resp = await self._request(URL_SET, {"id": self._req_id, "params": params}, headers, entry)
        _LOGGER.debug("%s SET response: %s", self._attr_unique_id, set_resp)
        await asyncio.sleep(5)
        await self.coordinator.async_request_refresh()

    async def _request(self, url, payload, headers, entry):
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


class FreshAirPowerSwitch(_FreshAirSwitchBase):
    _attr_icon = "mdi:air-purifier"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{entry.title} 开关机"
        self._attr_unique_id = f"panasonic_{device_id}_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="DCERV-03",
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        raw = data.get("runSta")
        if raw is None or raw == "":
            return None
        try:
            return int(raw) == 1
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_field("runSta", 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_field("runSta", 0)


class FreshAirHolidaySwitch(_FreshAirSwitchBase):
    _attr_icon = "mdi:beach"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{entry.title} 假日模式"
        self._attr_unique_id = f"panasonic_{device_id}_holiday"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="DCERV-03",
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        raw = data.get("holM")
        if raw is None or raw == "":
            return None
        try:
            v = int(raw)
            return None if v == 255 else v == 1
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_field("holM", 1)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_field("holM", 0)
