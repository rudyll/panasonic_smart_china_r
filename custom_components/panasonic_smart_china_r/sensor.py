from .const import CONF_DEVICE_KIND, DEVICE_KIND_FRESH_AIR


async def async_setup_entry(hass, entry, async_add_entities):
    kind = entry.data.get(CONF_DEVICE_KIND)
    if kind == DEVICE_KIND_FRESH_AIR:
        from .devices.dcerv.sensor import async_setup_entry as setup
        await setup(hass, entry, async_add_entities)
