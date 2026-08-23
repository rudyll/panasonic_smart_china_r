"""Binary sensor platform for Panasonic fridge devices (category 0100).

温区命名已用真实设备（Fridge-42）App 界面核对（2026-08-23）：PC=冷藏室、
SCB1=变温室（均不是此前以为的"变温室"/"切换室1"，见 sensor.py 顶部注释）。
SCGate 原来猜测是"冷藏室门"，但既然 PC 才是真正的冷藏室，这个猜测就站不住了——
改成中性的"门未关（区域未确认）"，避免和 PC 的门传感器重复认领同一个房间。
"""

import logging
from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FridgeBinarySpec:
    key: str
    name_suffix: str
    unique_suffix: str
    device_class: BinarySensorDeviceClass | None = None
    icon: str | None = None
    invert: bool = False  # True: raw==0 视为 on（例如 bodyOffline==0 表示在线）


BINARY_SPECS: tuple[FridgeBinarySpec, ...] = (
    FridgeBinarySpec("bodyOffline", "设备在线", "body_offline", BinarySensorDeviceClass.CONNECTIVITY, invert=True),
    FridgeBinarySpec("bodyOperating", "本体操作中", "body_operating", icon="mdi:cog-sync"),
    FridgeBinarySpec("voiceOperating", "语音操作中", "voice_operating", icon="mdi:microphone"),
    FridgeBinarySpec("FCTempCurAlarm", "冷冻室温度异常", "fc_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySpec("PCTempCurAlarm", "冷藏室温度异常", "pc_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySpec("SCB1TempCurAlarm", "变温室温度异常", "scb1_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySpec("SCB2TempCurAlarm", "切换室2温度异常（App无对应界面，未确认）", "scb2_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySpec("SCS1TempCurAlarm", "独立温区1温度异常", "scs1_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySpec("SCS2TempCurAlarm", "独立温区2温度异常", "scs2_temp_alarm", BinarySensorDeviceClass.PROBLEM),
    FridgeBinarySpec("FCGate1", "冷冻室门1未关", "fc_gate1", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("FCGate2", "冷冻室门2未关", "fc_gate2", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("PCGate1", "冷藏室门1未关", "pc_gate1", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("PCGate2", "冷藏室门2未关", "pc_gate2", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("SCB1Gate", "变温室门未关", "scb1_gate", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("SCB2Gate", "切换室2门未关（App无对应界面，未确认）", "scb2_gate", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("SCGate", "门未关（区域未确认）", "sc_gate", BinarySensorDeviceClass.DOOR),
    FridgeBinarySpec("waterLack", "缺水", "water_lack", BinarySensorDeviceClass.PROBLEM),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    specs = tuple(spec for spec in BINARY_SPECS if spec.key in data)
    async_add_entities(PanasonicFridgeBinarySensor(coordinator, entry, spec) for spec in specs)


class PanasonicFridgeBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, entry, spec: FridgeBinarySpec):
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
        if spec.device_class is not None:
            self._attr_device_class = spec.device_class
        if spec.icon:
            self._attr_icon = spec.icon

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)
        if raw is None or raw == "":
            return None
        try:
            value = int(raw) != 0
        except (TypeError, ValueError):
            return None
        return (not value) if self._spec.invert else value
