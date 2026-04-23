import logging

from homeassistant.components.persistent_notification import async_dismiss as pn_dismiss
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_ID,
    CONF_DEVICE_KIND,
    DEVICE_KIND_FRESH_AIR,
    DOMAIN,
    detect_device_kind,
)
from .coordinator import FreshAirCoordinator

_LOGGER = logging.getLogger(__name__)


def _platforms_for_entry(entry: ConfigEntry) -> list[str]:
    kind = entry.data.get(CONF_DEVICE_KIND) or detect_device_kind(
        entry.data.get(CONF_DEVICE_ID, "")
    )
    if kind == DEVICE_KIND_FRESH_AIR:
        return ["sensor", "select", "switch"]
    return ["climate"]


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
