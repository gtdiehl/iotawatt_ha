"""The iotawatt integration."""
from datetime import timedelta
from decimal import Decimal, DecimalException
import logging
from typing import Dict, List
from . import context

from httpx import AsyncClient
from iotawattpy.iotawatt import Iotawatt
import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    COORDINATOR,
    DEFAULT_ICON,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    IOTAWATT_API,
    SIGNAL_ADD_DEVICE,
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
    if "username" in entry.data.keys():
        api = Iotawatt(
            entry.data["name"],
            entry.data["host"],
            session,
            entry.data["username"],
            entry.data["password"],
        )
    else:
        api = Iotawatt(
            entry.data["name"],
            entry.data["host"],
            session,
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


class IotawattUpdater(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    def __init__(self, hass: HomeAssistant, api: str, name: str, update_interval: int):
        """Initialize IotaWattUpdater object."""
        self.api = api
        self.sensorlist: Dict[str, List[str]] = {}
        self.accumulatedValues = {}

        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=name,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self):
        """Fetch sensors from IoTaWatt device."""

        await self.api.update()
        sensors = self.api.getSensors()

        for sensor in sensors["sensors"]:
            entry = sensors["sensors"][sensor]
            if sensor not in self.sensorlist:
                _LOGGER.debug(f"First read sensor:{sensor} value:{entry.getValue()}")
                unit = entry.getUnit()
                suffix = ""
                if unit == "WattHours" and entry.getFromStart():
                    suffix = " Total Wh"
                elif unit == "WattHours":
                    suffix = ".Wh"

                to_add = {
                    "entity": sensor,
                    "mac_address": entry.hub_mac_address,
                    "name": entry.getBaseName() + suffix,
                }
                async_dispatcher_send(self.hass, SIGNAL_ADD_DEVICE, to_add)
                self.sensorlist[sensor] = entry
            if sensor in self.accumulatedValues:
                _LOGGER.debug(
                    f"Accumulating sensor:{sensor} value:{round(self.accumulatedValues[sensor], 3)} with:{entry.getValue()}"
                )
                self.accumulatedValues[sensor] += Decimal(entry.getValue())
        return sensors


class IotaWattEntity(CoordinatorEntity, SensorEntity):
    """Defines the base IoTaWatt Energy Device entity."""

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
        return self._mac_address

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def icon(self):
        """Return the icon for the entity."""
        return self._icon
