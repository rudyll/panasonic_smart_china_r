"""Number platform for Panasonic fridge devices (category 0100) — temperature setpoints.

温区命名已用真实设备（Fridge-42）App 界面核对（2026-08-23）：PC 字段实际对应
App 的"冷藏室"，SCB1 字段实际对应 App 的"变温室"（此前误标成"变温室"/"切换室1"）。
SCB2 在这台设备的 App 上没有对应的可设温界面，故不提供 SCB2TempSet 的 number
实体——只在 sensor.py 里保留只读展示。
"""

import logging
from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FridgeNumberSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    min_value: float
    max_value: float
    step: float
    icon: str | None = None
    # 变温室（SCB1）专用：direct-temp 模式才能写入，且不能比冷冻室设定温度更低
    # （App 源码 setSCB() 里对这两条都有强制约束，见 devices/fridge/select.py 顶部注释）。
    extra_mode_key: str | None = None
    floor_key: str | None = None


NUMBER_SPECS: tuple[FridgeNumberSpec, ...] = (
    FridgeNumberSpec("FCTempSet", "冷冻室设定温度", "fc_temp_set", -25, -14, 1, "mdi:snowflake-thermometer"),
    FridgeNumberSpec("PCTempSet", "冷藏室设定温度", "pc_temp_set", 2, 7, 1, "mdi:thermometer"),
    FridgeNumberSpec(
        "SCB1TempSet", "变温室设定温度", "scb1_temp_set", -25, 5, 1, "mdi:thermometer",
        extra_mode_key="SCB1ExtraMode", floor_key="FCTempSet",
    ),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    specs = tuple(spec for spec in NUMBER_SPECS if spec.key in data)
    async_add_entities(PanasonicFridgeNumber(coordinator, entry, spec) for spec in specs)


class PanasonicFridgeNumber(CoordinatorEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, entry, spec: FridgeNumberSpec):
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
        self._attr_native_max_value = spec.max_value
        self._attr_native_step = spec.step
        if spec.icon:
            self._attr_icon = spec.icon

    @property
    def available(self) -> bool:
        """变温室（SCB1）只有在“直接设温”（ExtraMode==0）时才可写；命中食材保鲜档位时禁用，
        避免覆盖 App 选的专用档位（见 select.py 里对应的档位选择实体）。
        """
        if not super().available:
            return False
        if self._spec.extra_mode_key is None:
            return True
        data = self.coordinator.data or {}
        raw = data.get(self._spec.extra_mode_key)
        try:
            return int(raw) == 0
        except (TypeError, ValueError):
            return True

    @property
    def native_min_value(self):
        """变温室（SCB1）不能比冷冻室设定温度更低（App 源码里对此有强制 clamp）。"""
        if self._spec.floor_key is None:
            return self._spec.min_value
        data = self.coordinator.data or {}
        raw = data.get(self._spec.floor_key)
        try:
            return max(self._spec.min_value, int(raw))
        except (TypeError, ValueError):
            return self._spec.min_value

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        value = int(value)
        floor = self.native_min_value
        if floor is not None and value < floor:
            _LOGGER.info(
                "%s: 目标 %s 低于冷冻室设定温度 %s，按 App 同款逻辑上调到 %s",
                self._attr_unique_id, value, floor, floor,
            )
            value = int(floor)
        await self.coordinator.async_set_fields(**{self._spec.key: value})
