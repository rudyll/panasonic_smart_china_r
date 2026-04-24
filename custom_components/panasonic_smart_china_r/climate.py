from .const import CONF_DEVICE_KIND, DEVICE_KIND_AC


async def async_setup_entry(hass, entry, async_add_entities):
    kind = entry.data.get(CONF_DEVICE_KIND)
    if kind == DEVICE_KIND_AC:
        from .devices.ac.climate import async_setup_entry as setup
        await setup(hass, entry, async_add_entities)
