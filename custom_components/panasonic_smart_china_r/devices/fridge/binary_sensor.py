"""Binary sensor platform for Panasonic fridge devices (Fridge-15)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import is_invalid_sensor_value
from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FridgeBinarySensorSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    device_class: BinarySensorDeviceClass | None
    # 哪种原始值代表 "ON" (True) 状态。例如门：1 是开；报警：1 是报警
    on_value: int | str = 1


# ============ 二进制传感器规格 ============
BINARY_SENSOR_SPECS: tuple[FridgeBinarySensorSpec, ...] = (
    # ----- 温度报警（1=报警，0=正常）-----
    FridgeBinarySensorSpec("PCTempCurAlarm", "冷藏室温度报警", "pc_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySensorSpec("FCTempCurAlarm", "冷冻室温度报警", "fc_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySensorSpec("SCB1TempCurAlarm", "变温室 1 温度报警", "scb1_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySensorSpec("SCB2TempCurAlarm", "变温室 2 温度报警", "scb2_temp_alarm", BinarySensorDeviceClass.PROBLEM),

    # ----- 门状态（1=开门，0=关门）-----
    FridgeBinarySensorSpec("PCGate1", "冷藏室 1 门状态", "pc_gate_1", BinarySensorDeviceClass.DOOR),
    FridgeBinarySensorSpec("PCGate2", "冷藏室 2 门状态", "pc_gate_2", BinarySensorDeviceClass.DOOR),
    FridgeBinarySensorSpec("FCGate1", "冷冻门 1 状态", "fc_gate_1", BinarySensorDeviceClass.DOOR),
    FridgeBinarySensorSpec("SCB1Gate", "变温室 1 门状态", "scb1_gate", BinarySensorDeviceClass.DOOR),
    FridgeBinarySensorSpec("SCB2Gate", "变温室 2 门状态", "scb2_gate", BinarySensorDeviceClass.DOOR),

    # ----- 检测类状态 -----
    FridgeBinarySensorSpec("bodyOffline", "运行状态", "body_offline", BinarySensorDeviceClass.CONNECTIVITY, on_value=0),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PanasonicFridgeBinarySensor(coordinator, entry, spec) for spec in BINARY_SENSOR_SPECS
    )


class PanasonicFridgeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, spec: FridgeBinarySensorSpec):
        super().__init__(coordinator)
        self._spec = spec
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{spec.name_suffix}"
        self._attr_unique_id = f"panasonic_{device_id}_{spec.unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model=entry.data.get("devSubTypeId", "Fridge"),
        )
        if spec.device_class is not None:
            self._attr_device_class = spec.device_class

    @property
    @override
    def is_on(self) -> bool | None:
        """返回二进制传感器的开/关状态."""
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)

        # 基础无效值过滤
        if raw is None or raw == "":
            return None
        if is_invalid_sensor_value(self._spec.key, raw):
            return None

        # 统一转为整型或字符串进行比对
        try:
            return int(raw) == int(self._spec.on_value)
        except (TypeError, ValueError):
            return str(raw) == str(self._spec.on_value)
