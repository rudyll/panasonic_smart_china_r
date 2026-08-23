"""Select platform for Panasonic fridge devices (category 0100) — 变温室食材保鲜档位。

变温室（字段名 SCB1，此前误标成"切换室1"，见 sensor.py/number.py 顶部注释）的
SCB1ExtraMode 不是普通开关，而是「直接设温 / 食材保鲜档位」的互斥选择：
0 = 直接设温（此时 SCB1TempSet 的数值写入才生效，见 number.py），1+ = 命中对应
食材后 App 会提示切换的专用档位，每档背后有一套固定的（模式, 温度）组合，不建议
再叠加手动温度写入。

档位名称和 MODE 序号最初来自 App 4.26.0（devSubTypeId=Fridge-42）的
chunk-365722ae.6a9add35.js 里 setSCB() 函数的 `n` 数组（2026-08-22 反编译确认），
该数组列出了全部 10 个档位名称，但那是食材推荐流程用的通用表，不代表这台设备的
变温室设置界面真的全部提供。经真实设备 App 界面核对（2026-08-23），变温室的
档位选择界面实际只提供其中 3 个（-3°c微冻/养生五谷/高级干货），其余 7 个档位
（低温发酵/高级臻品/腌制料理/婴幼辅食/母乳珍藏/暖存养胃/牛肉熟成）在这台设备上
没有对应界面，没有把握认定这些值可以安全写入，故不收录为可选项。

SCB2（切换室2）在这台设备的 App 上完全没有对应的档位选择界面，故不提供
SCB2ExtraMode 的 select 实体。
"""

import logging
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ...const import CONF_DEVICE_ID, DOMAIN

_LOGGER = logging.getLogger(__name__)

# index -> 档位名称（index 0 = 直接设温，对应 number.py 里的 SCB1TempSet 可写状态）。
# 只收录真实设备 App 界面上变温室档位选择实际提供的选项（见上方模块 docstring）。
EXTRA_MODE_OPTIONS: dict[int, str] = {
    0: "直接设温",
    1: "-3°c微冻",
    2: "养生五谷",
    3: "高级干货",
}
_NAME_TO_INDEX = {name: idx for idx, name in EXTRA_MODE_OPTIONS.items()}


@dataclass(frozen=True)
class FridgeSelectSpec:
    key: str
    name_suffix: str
    unique_suffix: str
    icon: str = "mdi:fridge-variant"


SELECT_SPECS: tuple[FridgeSelectSpec, ...] = (
    FridgeSelectSpec("SCB1ExtraMode", "变温室档位", "scb1_extra_mode"),
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
