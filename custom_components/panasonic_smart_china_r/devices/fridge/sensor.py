"""Sensor platform for Panasonic fridge devices (Fridge-15)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import override

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import is_invalid_sensor_value
from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FridgeSensorSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    device_class: SensorDeviceClass | None
    unit: str | None
    icon: str | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    # 若值不在白名单内就返回 None（用于门状态等非数值字段）
    value_filter: set | None = None


# ============ 传感器规格 ============
SENSOR_SPECS: tuple[FridgeSensorSpec, ...] = (
    # ----- 状态码 / 故障码 -----
    FridgeSensorSpec("controlCode", "控制码", "control_code", None, None, icon="mdi:numeric"),
    FridgeSensorSpec("displayCode", "显示码", "display_code", None, None, icon="mdi:numeric"),
    FridgeSensorSpec("changeCode", "变化码", "change_code", None, None, icon="mdi:numeric"),
    FridgeSensorSpec("fcCode", "故障码", "fc_code", None, None, icon="mdi:alert-octagon"),

)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PanasonicFridgeSensor(coordinator, entry, spec) for spec in SENSOR_SPECS
    )


class PanasonicFridgeSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, spec: FridgeSensorSpec):
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
        if spec.unit is not None:
            self._attr_native_unit_of_measurement = spec.unit
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.state_class is not None:
            self._attr_state_class = spec.state_class

    @property
    @override
    def native_value(self):
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)
        if raw is None or raw == "":
            return None
        if is_invalid_sensor_value(self._spec.key, raw):
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return raw  # 非数值原样返回（字符串等）
