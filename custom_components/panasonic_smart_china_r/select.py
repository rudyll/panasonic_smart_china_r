from .const import CONF_DEVICE_KIND, DEVICE_KIND_FRESH_AIR, DEVICE_KIND_FRIDGE


async def async_setup_entry(hass, entry, async_add_entities):
    kind = entry.data.get(CONF_DEVICE_KIND)
    if kind == DEVICE_KIND_FRESH_AIR:
        from .devices.erv.select import async_setup_entry as setup
        await setup(hass, entry, async_add_entities)
    elif kind == DEVICE_KIND_FRIDGE:
        from .devices.fridge.select import async_setup_entry as setup
        await setup(hass, entry, async_add_entities)
