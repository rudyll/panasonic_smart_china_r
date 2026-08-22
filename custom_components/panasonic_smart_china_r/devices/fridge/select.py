"""Select platform for Panasonic fridge devices (category 0100) — SCB1/SCB2 食材保鲜档位。

SCB1/SCB2 是可变冷冻/冷藏切换室。SCB*ExtraMode 不是普通开关，而是「直接设温 / 10 种
食材保鲜档位」的互斥选择：0 = 直接设温（此时 SCB*TempSet 的数值写入才生效，见
number.py），1-10 = 命中对应食材后 App 会提示切换的专用档位，每档背后有一套固定的
（模式, 温度）组合，不建议再叠加手动温度写入。

档位名称和 MODE 序号来自 App 4.26.0（devSubTypeId=Fridge-42）的
chunk-365722ae.6a9add35.js 里 setSCB() 函数的 `n` 数组，2026-08-22 反编译确认。
"""

import logging
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

# index -> 档位名称（index 0 = 直接设温，对应 number.py 里的 SCB*TempSet 可写状态）
EXTRA_MODE_OPTIONS: dict[int, str] = {
    0: "直接设温",
    1: "-3°c微冻",
    2: "养生五谷",
    3: "高级干货",
    4: "低温发酵",
    5: "高级臻品",
    6: "腌制料理",
    7: "婴幼辅食",
    8: "母乳珍藏",
    9: "暖存养胃",
    10: "牛肉熟成",
}
_NAME_TO_INDEX = {name: idx for idx, name in EXTRA_MODE_OPTIONS.items()}


@dataclass(frozen=True)
class FridgeSelectSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    icon: str = "mdi:fridge-variant"


SELECT_SPECS: tuple[FridgeSelectSpec, ...] = (
    FridgeSelectSpec("SCB1ExtraMode", "切换室1档位", "scb1_extra_mode"),
    FridgeSelectSpec("SCB2ExtraMode", "切换室2档位", "scb2_extra_mode"),
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    data = coordinator.data or {}
    specs = tuple(spec for spec in SELECT_SPECS if spec.key in data)
    async_add_entities(PanasonicFridgeExtraModeSelect(coordinator, entry, spec) for spec in specs)


class PanasonicFridgeExtraModeSelect(CoordinatorEntity, SelectEntity):
    _attr_options = list(EXTRA_MODE_OPTIONS.values())

    def __init__(self, coordinator, entry, spec: FridgeSelectSpec):
        super().__init__(coordinator)
        self._spec = spec
        device_id = entry.data[CONF_DEVICE_ID]
        self._attr_name = f"{entry.title} {spec.name_suffix}"
        self._attr_unique_id = f"panasonic_{device_id}_{spec.unique_suffix}"
        self._attr_icon = spec.icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Panasonic",
            model="Fridge",
        )

    @property
    def current_option(self):
        data = self.coordinator.data or {}
        raw = data.get(self._spec.key)
        try:
            return EXTRA_MODE_OPTIONS.get(int(raw))
        except (TypeError, ValueError):
            return None

    async def async_select_option(self, option: str) -> None:
        index = _NAME_TO_INDEX.get(option)
        if index is None:
            return
        await self.coordinator.async_set_fields(**{self._spec.key: index})
