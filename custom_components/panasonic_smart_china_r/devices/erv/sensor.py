"""Sensor platform for Panasonic fresh-air devices (DCERV series)."""

import logging
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FreshAirSensorSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    device_class: SensorDeviceClass | None
    unit: str | None
    icon: str | None = None


SENSOR_SPECS: tuple[FreshAirSensorSpec, ...] = (
    FreshAirSensorSpec("oaPMC",    "室外 PM2.5",       "oa_pm25",       SensorDeviceClass.PM25,        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
    FreshAirSensorSpec("saPMC",    "送风 PM2.5",       "sa_pm25",       SensorDeviceClass.PM25,        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
    FreshAirSensorSpec("raPMC",    "回风 PM2.5",       "ra_pm25",       SensorDeviceClass.PM25,        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
    FreshAirSensorSpec("oaHumC",   "室外湿度",         "oa_humidity",   SensorDeviceClass.HUMIDITY,    PERCENTAGE),
    FreshAirSensorSpec("raHumC",   "回风湿度",         "ra_humidity",   SensorDeviceClass.HUMIDITY,    PERCENTAGE),
    FreshAirSensorSpec("oaTeC",    "室外温度",         "oa_temp",       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FreshAirSensorSpec("saTeC",    "送风温度",         "sa_temp",       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FreshAirSensorSpec("raTeC",    "回风温度",         "ra_temp",       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS),
    FreshAirSensorSpec("raCO2C",   "回风 CO₂",        "ra_co2",        SensorDeviceClass.CO2,         CONCENTRATION_PARTS_PER_MILLION),
    FreshAirSensorSpec("raTVC",    "回风 TVOC 等级",   "ra_tvoc",       None,                          None,                            icon="mdi:air-filter"),
    FreshAirSensorSpec("oaFilExTL","外滤网剩余寿命",   "oa_filter_life",None,                          UnitOfTime.HOURS,                icon="mdi:air-filter"),
    FreshAirSensorSpec("saFilExTL","送风滤网剩余寿命", "sa_filter_life",None,                          UnitOfTime.HOURS,                icon="mdi:air-filter"),
    FreshAirSensorSpec("raFilExTL","回风滤网剩余寿命", "ra_filter_life",None,                          UnitOfTime.HOURS,                icon="mdi:air-filter"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PanasonicFreshAirSensor(coordinator, entry, spec) for spec in SENSOR_SPECS
    )


class PanasonicFreshAirSensor(CoordinatorEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry, spec: FreshAirSensorSpec):
        super().__init__(coordinator)
        self._spec = spec
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{entry.title} {spec.name_suffix}"
        self._attr_unique_id = f"panasonic_{device_id}_{spec.unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="DCERV",
        )
        if spec.device_class is not None:
            self._attr_device_class = spec.device_class
        if spec.unit is not None:
            self._attr_native_unit_of_measurement = spec.unit
        if spec.icon:
            self._attr_icon = spec.icon

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
                return None
