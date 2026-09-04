"""Switch platform for Panasonic fridge devices (Fridge-15)."""

from __future__ import annotations

import logging
from typing import override

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...coordinator import FridgeCoordinator
from ...const import CONF_DEVICE_ID, DOMAIN
from . import SWITCH_SPECS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PanasonicFridgeSwitch(coordinator, entry, spec) for spec in SWITCH_SPECS
    )


class PanasonicFridgeSwitch(CoordinatorEntity, SwitchEntity):
    """Panasonic 冰箱开关实体。"""

    def __init__(self, coordinator: FridgeCoordinator, entry, spec: dict):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._entry = entry
        self._field = spec["field"]
        self._icon = spec["icon"]

        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{spec['name_suffix']}"
        self._attr_unique_id = f"panasonic_{device_id}_{self._field}"
        self._attr_icon = self._icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model=entry.data.get("devSubTypeId", "Fridge"),
        )

    @property
    @override
    def is_on(self) -> bool | None:
        data = self.coordinator.data or {}
        raw = data.get(self._field)
        if raw is None or raw == "":
            return None
        try:
            v = int(raw)
            # skip 值 255 视为未知
            return None if v == 255 else v == 1
        except (TypeError, ValueError):
            return None

    @override
    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_fridge_field({self._field: 1})

    @override
    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_fridge_field({self._field: 0})