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

from .api import generate_device_token, relogin_entry, response_looks_bad
from .const import (
    CONF_DEVICE_ID,
    CONF_DEV_SUB_TYPE_ID,
    CONF_SSID,
    CONF_UPDATE_INTERVAL,
    CONF_USR_ID,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    get_dcerv_endpoints,
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
        # 温度/湿度是否以 0.2 分辨率放大 5 倍上报（显示值 = 原始值 / 5）。
        # 部分机型（如 DCERV-03）直接返回真实单位，无需还原。
        # 同一设备应保持一致：只要任一温/湿度字段超过物理量上限（100），
        # 即判定全设备为放大上报，统一还原。默认 True（放大为常见情况）。
        self.th_scaled: bool = True
        _LOGGER.info("%s ERV profile (from devSubTypeId): %s", self._device_id, self.erv_profile)

    @staticmethod
    def _profile_from_sub_type(dev_sub_type_id: str) -> str:
        upper = (dev_sub_type_id or "").upper().replace("-", "")
        if upper.startswith("SMALLERV"):
            return "SMALLERV"
        if upper.startswith("MIDERV"):
            return "MIDERV"
        if upper.startswith("NEWDCERV"):
            return "NEWDCERV"
        # LD6C（FV-25ZDP2C 等）走 MidERV 端点和 profile，
        # DCERV 端点对该机型只返回填充值（oaTeC=127、oaHumC=255 等）。
        if upper.startswith("LD6C"):
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

    async def _fetch_live(self):
        """拉取设备专属实时端点 ADevGetStatus*。

        返回云端原始 JSON；结构异常/认证失败时返回 None（交由调用方兜底）。
        这个端点返回的是真实传感器读数（oaPMC/oaTeC 等），不像
        UsrGetBindDevInfo.statusAll 那样把未刷新的字段填成 65535/255 哨兵。
        """
        get_url, _ = get_dcerv_endpoints(
            self._entry.data.get(CONF_DEV_SUB_TYPE_ID, "")
        )
        token = generate_device_token(self._device_id)
        if token is None:
            _LOGGER.debug("Live fetch skipped: cannot generate device token")
            return None

        payload = {
            "id": 1,
            "uiVersion": 4.0,
            "params": {
                "usrId": self._usr_id,
                "deviceId": self._device_id,
                "token": token,
            },
        }
        headers = {
            "User-Agent": "SmartApp",
            "Content-Type": "application/json",
            "Cookie": f"SSID={self._ssid}",
        }
        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                resp = await session.post(
                    get_url, json=payload, headers=headers, ssl=False
                )
                data = await resp.json()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Live fetch error on %s: %s", get_url, err)
            return None
        return data

    async def _fetch_cached(self):
        """兜底：拉取 UsrGetBindDevInfo 并抽取本设备的 statusAll。

        这是旧逻辑，statusAll 是云端缓存快照，传感器字段常为哨兵值；
        仅在实时端点不可用（token 生成失败/端点不支持/网络异常）时兜底使用。
        """
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
        try:
            async with async_timeout.timeout(10):
                resp = await session.post(
                    URL_GET_DEV, json=payload, headers=headers, ssl=False
                )
                data = await resp.json()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Cached fetch error: %s", err)
            return None

        if not isinstance(data, dict) or response_looks_bad(data):
            return data if isinstance(data, dict) else None

        for dev in data.get("results", {}).get("devList", []):
            if dev.get("deviceId") == self._device_id:
                return dev.get("params", {}).get("statusAll") or {}
        return None

    async def _async_update_data(self):
        # 优先读实时端点，拿到真实传感器读数
        data = await self._fetch_live()

        if data is None or response_looks_bad(data):
            if response_looks_bad(data):
                _LOGGER.warning(
                    "Fresh-air live response looks bad (errorCode=%s); attempting silent re-login. Raw=%s",
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
                data = await self._fetch_live()
            # 实时端点彻底不可用 → 兜底读缓存的 statusAll
            if data is None or response_looks_bad(data):
                _LOGGER.warning(
                    "Live ADevGetStatus* unavailable; falling back to UsrGetBindDevInfo.statusAll"
                )
                cached = await self._fetch_cached()
                if cached is None:
                    raise ConfigEntryAuthFailed(
                        "Live endpoint and UsrGetBindDevInfo both failed"
                    )
                self.th_scaled = self._detect_th_scaling(cached)
                return cached

        results = data.get("results") if isinstance(data, dict) else None
        if not isinstance(results, dict) or not results:
            _LOGGER.debug("Live response results empty; falling back to cached")
            cached = await self._fetch_cached()
            if cached is None:
                return self.data or {}
            self.th_scaled = self._detect_th_scaling(cached)
            return cached

        # 判定温度/湿度是否放大上报（跨传感器一致，避免对单字段阈值误判）。
        self.th_scaled = self._detect_th_scaling(results)
        return results

    @staticmethod
    def _detect_th_scaling(status_all: dict) -> bool:
        """只要任一温/湿度原始值超过物理量上限（100），即视为全设备放大上报。"""
        norm = {k.lower(): v for k, v in status_all.items()}
        for key in ("oatec", "satec", "ratec", "oahumc", "rahumc", "sahumc"):
            raw = norm.get(key)
            if raw in (None, ""):
                continue
            try:
                if float(raw) > 100:
                    return True
            except (TypeError, ValueError):
                continue
        return False
