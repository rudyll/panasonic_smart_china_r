"""Select platform for Panasonic fresh-air devices (DCERV series)."""

import asyncio
import logging
import random

import async_timeout
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...api import generate_device_token, relogin_entry
from ...const import CONF_DEVICE_ID, CONF_DEV_SUB_TYPE_ID, CONF_SSID, CONF_USR_ID, DOMAIN, get_dcerv_endpoints
from . import ERV_PROFILES

_LOGGER = logging.getLogger(__name__)

_MAX_RETRIES = 3


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    profile = ERV_PROFILES.get(coordinator.erv_profile or "DCERV", ERV_PROFILES["DCERV"])
    entities = [FreshAirVolumeSelect(coordinator, entry, profile)]
    if profile["has_run_mode"]:
        entities.append(FreshAirModeSelect(coordinator, entry, profile))
    async_add_entities(entities)


class _FreshAirSelect(CoordinatorEntity, SelectEntity):
    _status_key: str = ""
    _set_map: dict[str, int] | None = None
    _set_field: str = ""
    _unique_suffix: str = ""
    _name_suffix: str = ""
    _req_id: int = 0

    def __init__(self, coordinator, entry, profile: dict):
        super().__init__(coordinator)
        self._entry = entry
        self._get_map: dict[int, str] = {}
        self._payload_builder = profile["payload_builder"]
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_options = list(dict.fromkeys(self._get_map.values()))  # deduplicate, preserve order
        self._attr_name = f"{entry.title} {self._name_suffix}"
        self._attr_unique_id = f"panasonic_{device_id}_{self._unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="DCERV",
        )

    @property
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}
        raw = data.get(self._status_key)
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
        _, url_set = get_dcerv_endpoints(entry.data.get(CONF_DEV_SUB_TYPE_ID, ""))
        headers = {
            "User-Agent": "SmartApp",
            "Content-Type": "application/json",
            "Cookie": f"SSID={ssid}",
        }

        params = self._payload_builder(device_id, token, usr_id, **{self._set_field: set_value})
        _LOGGER.debug("%s SET %s=%s (option=%r)", self._attr_unique_id, self._set_field, set_value, option)
        self._req_id += 1
        set_resp = await self._post_with_retry(url_set, {"id": self._req_id, "params": params}, headers, entry)
        _LOGGER.debug("%s SET response: %s", self._attr_unique_id, set_resp)
        await asyncio.sleep(5)
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
    _set_field = "runM"
    _unique_suffix = "run_mode"
    _name_suffix = "运行模式"
    _attr_icon = "mdi:fan-auto"

    def __init__(self, coordinator, entry, profile: dict):
        super().__init__(coordinator, entry, profile)
        self._get_map = profile["run_mode_get_map"]
        self._set_map = profile["run_mode_set_map"]
        self._attr_options = list(dict.fromkeys(self._get_map.values()))


class FreshAirVolumeSelect(_FreshAirSelect):
    _status_key = "airVo"
    _set_field = "airVo"
    _unique_suffix = "air_volume"
    _name_suffix = "风量"
    _attr_icon = "mdi:weather-windy"

    def __init__(self, coordinator, entry, profile: dict):
        super().__init__(coordinator, entry, profile)
        self._get_map = profile["air_volume_map"]
        self._attr_options = list(dict.fromkeys(self._get_map.values()))
