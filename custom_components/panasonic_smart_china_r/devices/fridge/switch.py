"""Switch platform for Panasonic fridge devices (category 0100)."""

import logging
from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FridgeSwitchSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    icon: str | None = None


# 字段名 -> 真实 App UI 标签，来自 App 4.26.0 里 devType=="Fridge-42" 分支的
# modeList.push() 定义（chunk-45153b7b.e461c771.js，2026-08-22 反编译确认）：
#   {nanoe:"纳诺怡", quickCooling:"快速冷却", quickFreeze:"极冻锁鲜"}
# 这是本机型唯一真实存在的三个快捷模式开关。GET 响应里还有 ecoMode/eraseOdor/
# silver/preservation 等字段，但在整个 App 源码里都找不到任何 UI 引用（纯共享
# bean 占位字段，从未被任何机型使用）；autoIcing/smartHumi 有真实 UI，但只在
# Fridge-38/39/40/41 的 modeList 分支里，Fridge-42 分支不包含它们——所以都不收录，
# 避免暴露对这台设备实际不生效的开关。
SWITCH_SPECS: tuple[FridgeSwitchSpec, ...] = (
    FridgeSwitchSpec("nanoe", "纳诺怡", "nanoe", "mdi:air-purifier"),
    FridgeSwitchSpec("quickCooling", "快速冷却", "quick_cooling", "mdi:snowflake-thermometer"),
    FridgeSwitchSpec("quickFreeze", "极冻锁鲜", "quick_freeze", "mdi:snowflake-alert"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    specs = tuple(spec for spec in SWITCH_SPECS if spec.key in data)
    async_add_entities(PanasonicFridgeSwitch(coordinator, entry, spec) for spec in specs)


class PanasonicFridgeSwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, entry, spec: FridgeSwitchSpec):
        super().__init__(coordinator)
        self._spec = spec
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{entry.title} {spec.name_suffix}"
        self._attr_unique_id = f"panasonic_{device_id}_{spec.unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="Fridge",
        )
        if spec.icon:
            self._attr_icon = spec.icon

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)
        if raw is None or raw == "":
            return None
        try:
            return int(raw) == 1
        except (TypeError, ValueError):
            return None

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_fields(**{self._spec.key: 1})

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_fields(**{self._spec.key: 0})
