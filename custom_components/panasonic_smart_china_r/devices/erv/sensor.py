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
    # 云端返回值 = 显示值 × scale。温度/湿度为 0.2 分辨率（放大 5 倍），
    # 例如 127 -> 25.4°C、255 -> 51%RH。
    scale: float = 1.0
    # 视为“无传感器/无效”的哨兵原始值（255=0xFF，65535=0xFFFF）。
    sentinel: tuple = ()
    # 是否保留 1 位小数（温度/湿度）。
    decimal: bool = False


# 哨兵值：松下协议里“无传感器/无效”。单字节字段用 0xFF=255，
# 双字节字段用 0xFFFF=65535（参考 dkong5ssss 项目默认值）。
_SENTINEL_WORD = (65535,)
_SENTINEL_BYTE = (255, 65535)

SENSOR_SPECS: tuple[FreshAirSensorSpec, ...] = (
    FreshAirSensorSpec("oaPMC",    "室外 PM2.5",       "oa_pm25",       SensorDeviceClass.PM25,        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, sentinel=_SENTINEL_WORD),
    FreshAirSensorSpec("saPMC",    "送风 PM2.5",       "sa_pm25",       SensorDeviceClass.PM25,        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, sentinel=_SENTINEL_WORD),
    FreshAirSensorSpec("raPMC",    "回风 PM2.5",       "ra_pm25",       SensorDeviceClass.PM25,        CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, sentinel=_SENTINEL_WORD),
    FreshAirSensorSpec("oaHumC",   "室外湿度",         "oa_humidity",   SensorDeviceClass.HUMIDITY,    PERCENTAGE, scale=5, decimal=True, sentinel=_SENTINEL_BYTE),
    FreshAirSensorSpec("raHumC",   "回风湿度",         "ra_humidity",   SensorDeviceClass.HUMIDITY,    PERCENTAGE, scale=5, decimal=True, sentinel=_SENTINEL_BYTE),
    FreshAirSensorSpec("oaTeC",    "室外温度",         "oa_temp",       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, scale=5, decimal=True, sentinel=_SENTINEL_BYTE),
    FreshAirSensorSpec("saTeC",    "送风温度",         "sa_temp",       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, scale=5, decimal=True, sentinel=_SENTINEL_BYTE),
    FreshAirSensorSpec("raTeC",    "回风温度",         "ra_temp",       SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, scale=5, decimal=True, sentinel=_SENTINEL_BYTE),
    FreshAirSensorSpec("raCO2C",   "回风 CO₂",        "ra_co2",        SensorDeviceClass.CO2,         CONCENTRATION_PARTS_PER_MILLION, sentinel=_SENTINEL_WORD),
    FreshAirSensorSpec("raTVC",    "回风 TVOC 等级",   "ra_tvoc",       None,                          None,                            icon="mdi:air-filter", sentinel=_SENTINEL_BYTE),
    FreshAirSensorSpec("oaFilExTL","外滤网剩余寿命",   "oa_filter_life",None,                          UnitOfTime.HOURS,                icon="mdi:air-filter", sentinel=_SENTINEL_WORD),
    FreshAirSensorSpec("saFilExTL","送风滤网剩余寿命", "sa_filter_life",None,                          UnitOfTime.HOURS,                icon="mdi:air-filter", sentinel=_SENTINEL_WORD),
    FreshAirSensorSpec("raFilExTL","回风滤网剩余寿命", "ra_filter_life",None,                          UnitOfTime.HOURS,                icon="mdi:air-filter", sentinel=_SENTINEL_WORD),
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
        # 云端不同机型/端点字段大小写不一致（如 raCo2C / raTvC），统一按小写匹配，
        # 否则实体取不到值、恒为 unavailable。
        norm = {k.lower(): v for k, v in data.items()}
        raw = norm.get(self._spec.key.lower())
        if raw is None or raw == "":
            return None
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return None
        if self._spec.sentinel and val in self._spec.sentinel:
            return None
        # 温度/湿度是否按放大倍率还原由 coordinator 按设备判定（跨传感器一致），
        # 避免对单字段阈值误判导致 0–20°C 区间数值被错误放大。
        if self._spec.scale and self._spec.scale != 1 and self.coordinator.th_scaled:
            val = val / self._spec.scale
        if self._spec.decimal:
            return round(val, 1)
        return int(round(val))
