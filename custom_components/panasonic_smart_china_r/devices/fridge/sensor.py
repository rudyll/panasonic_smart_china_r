"""Sensor platform for Panasonic fridge devices (category 0100)."""

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FridgeSensorSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    icon: str | None = None
    is_measurement: bool = True


# FC=冷冻室，PC=变温室，SCB1/SCB2=可变冷冻/冷藏切换室，SCS1/SCS2=部分机型才有的独立温区。
TEMP_SENSOR_SPECS: tuple[FridgeSensorSpec, ...] = (
    FridgeSensorSpec("FCTempCur", "冷冻室温度", "fc_temp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FridgeSensorSpec("PCTempCur", "变温室温度", "pc_temp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FridgeSensorSpec("SCB1TempCur", "切换室1温度", "scb1_temp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FridgeSensorSpec("SCB2TempCur", "切换室2温度", "scb2_temp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FridgeSensorSpec("SCS1TempCur", "独立温区1温度", "scs1_temp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FridgeSensorSpec("SCS2TempCur", "独立温区2温度", "scs2_temp", SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
)

# SCB1TempSet/SCB2TempSet 现在是可写的 number 实体（见 number.py），不再重复放只读 sensor。

MODE_SENSOR_SPECS: tuple[FridgeSensorSpec, ...] = (
    FridgeSensorSpec("SCB1ModeCur", "切换室1模式", "scb1_mode", icon="mdi:fridge-variant", is_measurement=False),
    FridgeSensorSpec("SCB2ModeCur", "切换室2模式", "scb2_mode", icon="mdi:fridge-variant", is_measurement=False),
)

ALL_SPECS = TEMP_SENSOR_SPECS + MODE_SENSOR_SPECS


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    specs = tuple(spec for spec in ALL_SPECS if spec.key in data)
    entities = [PanasonicFridgeSensor(coordinator, entry, spec) for spec in specs]
    entities.append(PanasonicFridgeAlarmCountSensor(coordinator, entry))
    async_add_entities(entities)


class PanasonicFridgeSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, spec: FridgeSensorSpec):
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
        if spec.unit is not None:
            self._attr_native_unit_of_measurement = spec.unit
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.is_measurement:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            try:
                return float(raw)
            except (TypeError, ValueError):
                return str(raw)


class PanasonicFridgeAlarmCountSensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{entry.title} 报警数量"
        self._attr_unique_id = f"panasonic_{device_id}_alarm_count"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="Fridge",
        )

    @property
    def native_value(self):
        alarms = (self.coordinator.data or {}).get("alarmList")
        return len(alarms) if isinstance(alarms, list) else None

    @property
    def extra_state_attributes(self):
        alarms = (self.coordinator.data or {}).get("alarmList")
        return {"alarms": alarms} if isinstance(alarms, list) else None
