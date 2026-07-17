import logging

import async_timeout
from homeassistant.components.persistent_notification import async_dismiss as pn_dismiss
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_KIND,
    CONF_DEV_SUB_TYPE_ID,
    CONF_SSID,
    CONF_USR_ID,
    DEVICE_KIND_FRESH_AIR,
    DOMAIN,
    detect_device_kind,
)
from .coordinator import FreshAirCoordinator

_LOGGER = logging.getLogger(__name__)

URL_GET_DEV = "https://app.psmartcloud.com/App/UsrGetBindDevInfo"


def _platforms_for_entry(entry: ConfigEntry) -> list[str]:
    kind = entry.data.get(CONF_DEVICE_KIND) or detect_device_kind(
        entry.data.get(CONF_DEVICE_ID, "")
    )
    if kind == DEVICE_KIND_FRESH_AIR:
        return ["sensor", "select", "switch"]
    return ["climate"]


async def _migrate_dev_sub_type_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """旧版 config entry 可能没有持久化 devSubTypeId（空字符串）。

    没有 devSubTypeId 时 coordinator 会 fallback 到 DCERV 端点，
    导致部分机型（如 LD6C）从错误的端点拉取到填充值而非真实传感器读数。
    这里在 setup 时从 UsrGetBindDevInfo 补全 devSubTypeId 并写回 entry.data。
    """
    if entry.data.get(CONF_DEV_SUB_TYPE_ID):
        return

    device_id = entry.data.get(CONF_DEVICE_ID, "")
    usr_id = entry.data.get(CONF_USR_ID, "")
    ssid = entry.data.get(CONF_SSID, "")
    family_id = entry.data.get("familyId")
    real_family_id = entry.data.get("realFamilyId")
    if (
        not device_id
        or not usr_id
        or not ssid
        or family_id is None
        or real_family_id is None
    ):
        return

    headers = {
        "User-Agent": "SmartApp",
        "Content-Type": "application/json",
        "Cookie": f"SSID={ssid}",
    }
    payload = {
        "id": 3,
        "uiVersion": 4.0,
        "params": {
            "realFamilyId": real_family_id,
            "familyId": family_id,
            "usrId": usr_id,
        },
    }
    session = async_get_clientsession(hass)
    try:
        async with async_timeout.timeout(10):
            resp = await session.post(
                URL_GET_DEV, json=payload, headers=headers, ssl=False
            )
            data = await resp.json()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("devSubTypeId migration fetch failed: %s", err)
        return

    if not isinstance(data, dict):
        _LOGGER.warning("devSubTypeId migration returned a non-object response")
        return

    results = data.get("results")
    if not isinstance(results, dict):
        return

    for dev in results.get("devList", []):
        if dev.get("deviceId") == device_id:
            sub_type = dev.get("params", {}).get("devSubTypeId", "")
            if sub_type:
                new_data = {**entry.data, CONF_DEV_SUB_TYPE_ID: sub_type}
                hass.config_entries.async_update_entry(entry, data=new_data)
                _LOGGER.info(
                    "Migrated devSubTypeId for %s: '%s'", device_id, sub_type
                )
            return


async def async_setup(hass: HomeAssistant, config: dict):
    # 全局 Session 缓存：{'usrId', 'SSID', 'familyId', 'realFamilyId', 'devices'}
    hass.data.setdefault(DOMAIN, {"session": None})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    hass.data.setdefault(DOMAIN, {"session": None})

    # 手动重载 entry = 用户明确想立即切回 HA，清掉冷却让首次刷新能重登
    hass.data[DOMAIN].pop("last_relogin_ts", None)
    pn_dismiss(hass, f"pms_session_stolen_{entry.entry_id}")

    kind = entry.data.get(CONF_DEVICE_KIND) or detect_device_kind(
        entry.data.get(CONF_DEVICE_ID, "")
    )

    # 新风机：所有平台共享同一个 Coordinator，按 entry_id 存在 hass.data 下
    if kind == DEVICE_KIND_FRESH_AIR:
        await _migrate_dev_sub_type_id(hass, entry)
        coordinator = FreshAirCoordinator(hass, entry)
        await coordinator.async_config_entry_first_refresh()
        hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(
        entry, _platforms_for_entry(entry)
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """选项变更时热重载 entry，让新的轮询间隔立即生效。"""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, _platforms_for_entry(entry)
    )
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
