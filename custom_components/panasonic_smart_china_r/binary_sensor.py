from .const import CONF_DEVICE_KIND, DEVICE_KIND_FRIDGE


async def async_setup_entry(hass, entry, async_add_entities):
    kind = entry.data.get(CONF_DEVICE_KIND)
    if kind == DEVICE_KIND_FRIDGE:
        from .devices.fridge.binary_sensor import async_setup_entry as setup
        await setup(hass, entry, async_add_entities)
