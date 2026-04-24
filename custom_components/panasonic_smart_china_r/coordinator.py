"""共享的新风机 DataUpdateCoordinator。

sensor 与 select 两个平台都复用同一实例（按 entry.entry_id 存在 hass.data 里）。
SSID 过期时先尝试静默重登一次，失败才抛 ConfigEntryAuthFailed 触发 reauth UI。
"""

import logging
from datetime import timedelta

import async_timeout
from homeassistant.components.persistent_notification import async_create as pn_create
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import relogin_entry, response_looks_bad
from .const import (
    CONF_DEVICE_ID,
    CONF_DEV_SUB_TYPE_ID,
    CONF_SSID,
    CONF_UPDATE_INTERVAL,
    CONF_USR_ID,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .exceptions import LoginFailed, ReloginCooldown

_LOGGER = logging.getLogger(__name__)

URL_GET_DEV = "https://app.psmartcloud.com/App/UsrGetBindDevInfo"


class FreshAirCoordinator(DataUpdateCoordinator):
    """拉取 UsrGetBindDevInfo，按 deviceId 抽取对应设备的 statusAll。"""

    def __init__(self, hass, entry):
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"panasonic_freshair_{entry.data[CONF_DEVICE_ID]}",
            update_interval=timedelta(seconds=interval),
        )
        self._entry = entry
        self._usr_id = entry.data[CONF_USR_ID]
        self._ssid = entry.data[CONF_SSID]
        self._device_id = entry.data[CONF_DEVICE_ID]
        self.erv_profile: str = self._profile_from_sub_type(
            entry.data.get(CONF_DEV_SUB_TYPE_ID, "")
        )
        _LOGGER.info("%s ERV profile (from devSubTypeId): %s", self._device_id, self.erv_profile)

    @staticmethod
    def _profile_from_sub_type(dev_sub_type_id: str) -> str:
        upper = (dev_sub_type_id or "").upper().replace("-", "")
        if upper.startswith("SMALLERV"):
            return "SMALLERV"
        if upper.startswith("MIDERV"):
            return "MIDERV"
        return "DCERV"

    def _build_payload(self):
        session_cache = (self.hass.data.get(DOMAIN) or {}).get("session") or {}
        family_id = session_cache.get("familyId")
        if family_id is None:
            family_id = self._entry.data.get("familyId")
        real_family_id = session_cache.get("realFamilyId")
        if real_family_id is None:
            real_family_id = self._entry.data.get("realFamilyId")
        return family_id, real_family_id

    async def _fetch(self):
        family_id, real_family_id = self._build_payload()
        if family_id is None or real_family_id is None:
            return None

        payload = {
            "id": 3,
            "uiVersion": 4.0,
            "params": {
                "realFamilyId": real_family_id,
                "familyId": family_id,
                "usrId": self._usr_id,
            },
        }
        headers = {
            "User-Agent": "SmartApp",
            "Content-Type": "application/json",
            "Cookie": f"SSID={self._ssid}",
        }
        session = async_get_clientsession(self.hass)
        async with async_timeout.timeout(10):
            resp = await session.post(
                URL_GET_DEV, json=payload, headers=headers, ssl=False
            )
            return await resp.json()

    async def _async_update_data(self):
        try:
            data = await self._fetch()
        except Exception as err:  # noqa: BLE001
            raise UpdateFailed(f"Fresh-air fetch failed: {err}") from err

        if data is None:
            return self.data or {}

        if response_looks_bad(data):
            _LOGGER.warning(
                "Fresh-air response looks bad (errorCode=%s); attempting silent re-login. Raw=%s",
                data.get("errorCode") if isinstance(data, dict) else None,
                data,
            )
            try:
                self._ssid = await relogin_entry(self.hass, self._entry)
            except ReloginCooldown as err:
                pn_create(
                    self.hass,
                    (
                        "松下智家账号疑似被其他设备（手机 App 等）登录踢掉。"
                        "Home Assistant 已暂停轮询 10 分钟，避免跟手机抢占会话。\n\n"
                        "若希望立即切回 HA：前往 **设置 → 设备与服务 → Panasonic Smart China**，"
                        "点击集成右上角菜单 → **重新加载** 即可立即重登。"
                    ),
                    title="Panasonic Smart China 会话被抢占",
                    notification_id=f"pms_session_stolen_{self._entry.entry_id}",
                )
                raise UpdateFailed(str(err)) from err
            except LoginFailed as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            try:
                data = await self._fetch()
            except Exception as err:  # noqa: BLE001
                raise UpdateFailed(f"Fresh-air fetch (post-relogin) failed: {err}") from err
            if data is None or response_looks_bad(data):
                raise ConfigEntryAuthFailed(
                    f"Still bad after re-login: errorCode={data.get('errorCode') if isinstance(data, dict) else None}"
                )

        status_all = None
        for dev in data.get("results", {}).get("devList", []):
            if dev.get("deviceId") == self._device_id:
                status_all = dev.get("params", {}).get("statusAll") or {}
                break

        if status_all is None:
            _LOGGER.debug("Device %s not in devList", self._device_id)
            return self.data or {}

        return status_all
