"""Select platform for Panasonic fridge devices (Fridge-15)."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ... import FridgeCoordinator
from ...const import CONF_DEVICE_ID, DOMAIN
from . import (
    SELECT_MODE_SPECS,
    SELECT_SCB_SPECS,
    SELECT_TEMP_SPECS,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SelectEntity] = []

    # 1. 普通单字段选择器（冷藏室/冷冻室温度、保鲜模式）
    for spec in SELECT_TEMP_SPECS + SELECT_MODE_SPECS:
        entities.append(FridgeTempSelect(coordinator, entry, spec))

    # 2. 变温室复合选择器（变温室 1 & 2）
    for spec in SELECT_SCB_SPECS:
        entities.append(FridgeSCBSelect(coordinator, entry, spec))

    async_add_entities(entities)


class FridgeTempSelect(CoordinatorEntity, SelectEntity):
    """单字段选择器（冷藏/冷冻温度及基础模式）。"""

    def __init__(self, coordinator: FridgeCoordinator, entry, spec: dict):
        super().__init__(coordinator)
        self._entry = entry
        self._status_key: str = spec["field"]
        self._set_field_name: str = spec["field"]
        self._attr_icon = spec["icon"]

        # 构建类型双重容错的映射表 (支持 int 和 str 键查询)
        self._get_map: dict[int, str] = spec["options_map"]
        self._set_map: dict[str, int] = {
            label: value for value, label in self._get_map.items()
        }
        self._attr_options = list(dict.fromkeys(self._get_map.values()))

        device_id = entry.data[CONF_DEVICE_ID]

        self._attr_name = f"{spec['name_suffix']}"
        self._attr_unique_id = f"panasonic_{device_id}_{spec['unique_suffix']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model=entry.data.get("devSubTypeId", "Fridge"),
        )

    @property
    @override
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}
        raw = data.get(self._status_key)
        if raw is None or raw == "":
            return None
        try:
            raw_int = int(raw)
        except (TypeError, ValueError):
            return None

        label = self._get_map.get(raw_int)
        if label is None:
            _LOGGER.warning(
                "%s 未能映射的数值: %s=%r (有效范围=%s)",
                self._attr_unique_id,
                self._status_key,
                raw_int,
                sorted(self._get_map.keys()),
            )
            return None

        return label if label in self._attr_options else None

    @override
    async def async_select_option(self, option: str) -> None:
        set_value = self._set_map.get(option)
        if set_value is None:
            raise HomeAssistantError(f"未知选项: {option}")

        await self.coordinator.async_set_fridge_field({self._set_field_name: set_value})


class FridgeSCBSelect(CoordinatorEntity, SelectEntity):
    """变温室复合选择器（同时匹配并下发 ModeCur / TempSet / SCSTempSet）。"""

    def __init__(self, coordinator: FridgeCoordinator, entry, spec: dict):
        super().__init__(coordinator)
        self._entry = entry
        self._mode_field: str = spec["mode_field"]
        self._temp_field: str = spec["temp_field"]
        self._scs_field: str = spec["scs_field"]
        self._attr_icon = spec["icon"]

        self._options_map: dict[str, dict[str, int]] = spec["options_map"]
        self._attr_options = list(self._options_map.keys())

        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{spec['name_suffix']}"
        self._attr_unique_id = f"panasonic_{device_id}_{spec['unique_suffix']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model=entry.data.get("devSubTypeId", "Fridge"),
        )

    @property
    @override
    def current_option(self) -> str | None:
        data = self.coordinator.data or {}

        raw_mode = data.get(self._mode_field)
        raw_temp = data.get(self._temp_field)

        if raw_mode is None or raw_temp is None:
            return None

        try:
            cur_mode = int(raw_mode)
            cur_temp = int(raw_temp)
        except (TypeError, ValueError):
            return None

        # 1. 优先匹配特殊模式 (ModeCur > 0)
        if cur_mode > 0:
            for label, config in self._options_map.items():
                if int(config["ModeCur"]) == cur_mode:
                    return label

        # 2. 普通控温模式 (ModeCur == 0)
        if cur_mode == 0:
            target_label = f"{cur_temp} °C"
            if target_label in self._options_map:
                return target_label

        _LOGGER.warning(
            "%s 变温室无法识别的状态: %s=%r, %s=%r",
            self._attr_unique_id,
            self._mode_field,
            cur_mode,
            self._temp_field,
            cur_temp,
        )
        return None

    @override
    async def async_select_option(self, option: str) -> None:
        target_config = self._options_map.get(option)
        if not target_config:
            raise HomeAssistantError(f"未知选项: {option}")

        payload_overrides = {
            self._mode_field: target_config["ModeCur"],
            self._temp_field: target_config["TempSet"],
            self._scs_field: target_config["SCSTempSet"],
        }

        await self.coordinator.async_set_fridge_field(payload_overrides)