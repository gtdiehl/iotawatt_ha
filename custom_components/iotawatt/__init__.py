"""The iotawatt integration."""
import asyncio
import logging

from datetime import timedelta
from httpx import AsyncClient
from iotawattpy.iotawatt import Iotawatt
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import CONF_SCAN_INTERVAL, DEVICE_CLASS_ENERGY
from homeassistant.exceptions import ConfigEntryNotReady, PlatformNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DEFAULT_ICON,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    COORDINATOR,
    IOTAWATT_API,
    SIGNAL_ADD_DEVICE,
    SIGNAL_DELETE_DEVICE,
)

CONFIG_SCHEMA = vol.Schema({DOMAIN: vol.Schema({})}, extra=vol.ALLOW_EXTRA)
_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the iotawatt component."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up iotawatt from a config entry."""
    polling_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    session = AsyncClient()
    api = Iotawatt(
        entry.data["name"],
        entry.data["ip_address"],
        session,
        entry.data["username"],
        entry.data["password"],
    )

    coordinator = IotawattUpdater(
        hass,
        api=api,
        name="IoTaWatt",
        update_interval=polling_interval,
    )

    await coordinator.async_refresh()

    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data[DOMAIN][entry.entry_id] = {
        COORDINATOR: coordinator,
        IOTAWATT_API: api,
    }

    for component in PLATFORMS:
        _LOGGER.info(f"Setting up platform: {component}")
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, component)
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, component)
                for component in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def cleanup_device_registry(hass: HomeAssistant, device_id):
    """Remove device registry entry if there are no remaining entities."""

    device_registry = await hass.helpers.device_registry.async_get_registry()
    entity_registry = await hass.helpers.entity_registry.async_get_registry()
    if device_id and not hass.helpers.entity_registry.async_entries_for_device(
        entity_registry, device_id, include_disabled_entities=True
    ):
        device_registry.async_remove_device(device_id)


class IotawattUpdater(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device"""

    def __init__(self, hass: HomeAssistant, api: str, name: str, update_interval: int):
        self.api = api
        self.sensorlist = {}

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=name,
            update_interval=timedelta(seconds=update_interval)
        )

    async def _async_update_data(self):
        """Fetch sensors from IoTaWatt device"""

        await self.api.update()
        sensors = self.api.getSensors()

        for sensor in sensors["sensors"]:
            if sensor not in self.sensorlist:
                to_add = {
                    "entity": sensor,
                    "mac_address": sensors["sensors"][sensor].hub_mac_address,
                    "name": sensors["sensors"][sensor].getName(),
                }
                async_dispatcher_send(self.hass, SIGNAL_ADD_DEVICE, to_add)
                self.sensorlist[sensor] = sensors["sensors"][sensor]

        keys_to_be_removed = []
        for known_sensor in self.sensorlist:
            if known_sensor not in sensors["sensors"]:
                async_dispatcher_send(
                    self.hass, SIGNAL_DELETE_DEVICE, known_sensor
                )
                keys_to_be_removed.append(known_sensor)

        for k in keys_to_be_removed:
            del self.sensorlist[k]

        return sensors

class IotaWattEntity(CoordinatorEntity):
    """Defines the base IoTaWatt Energy Device entity."""

    device_class = DEVICE_CLASS_ENERGY

    def __init__(self, coordinator: IotawattUpdater, entity, mac_address, name):
        """Initialize the IoTaWatt Entity."""
        super().__init__(coordinator)

        self._entity = entity
        self._name = name
        self._icon = DEFAULT_ICON
        self._mac_address = mac_address

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._mac_addr

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def icon(self):
        """Return the icon for the entity."""
        return self._icon

    async def async_added_to_hass(self):
        """When entity is added to HASS."""
        self.async_on_remove(self.coordinator.async_add_listener(self._update_callback))

    async def async_will_remove_from_hass(self) -> None:
        """Call when entity will be removed from hass."""
        self._remove_signal_update()

    @callback
    def _update_callback(self):
        """Handle device update."""
        self.async_write_ha_state()

    async def _delete_callback(self, device_id):
        """Remove the device when it disappears."""

        if device_id == self._unique_id:
            entity_registry = (
                await self.hass.helpers.entity_registry.async_get_registry()
            )

            if entity_registry.async_is_registered(self.entity_id):
                entity_entry = entity_registry.async_get(self.entity_id)
                entity_registry.async_remove(self.entity_id)
                await cleanup_device_registry(self.hass, entity_entry.device_id)
            else:
                await self.async_remove()