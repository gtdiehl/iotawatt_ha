"""Support for IoTaWatt Energy monitor."""
from datetime import timedelta
from functools import partial
import logging

from homeassistant.const import (
    POWER_WATT,
    ELECTRIC_POTENTIAL_VOLT,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_VOLTAGE
)

from homeassistant.core import callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from . import IotaWattEntity, IotawattUpdater
from .const import (
    COORDINATOR,
    DOMAIN,
    SIGNAL_ADD_DEVICE,
    SIGNAL_DELETE_DEVICE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    entities = []

    for idx, ent in enumerate(coordinator.data["sensors"]):
        entity = IotaWattSensor(
            coordinator=coordinator,
            entity=ent,
            mac_address=coordinator.data["sensors"][ent].hub_mac_address,
            name=coordinator.data["sensors"][ent].getName(),
        )
        entities.append(entity)

    async_add_entities(entities)

    async def async_new_entities(sensor_info):
        """Remove an entity."""
        ent = sensor_info["entity"]
        hub_mac_address = sensor_info["mac_address"]
        name = sensor_info["name"]

        entity = IotaWattSensor(
            coordinator=coordinator, entity=ent, mac_address=hub_mac_address, name=name,
        )
        entities = [entity]
        async_add_entities(entities)

    async_dispatcher_connect(hass, SIGNAL_ADD_DEVICE, async_new_entities)


class IotaWattSensor(IotaWattEntity):
    """Defines a IoTaWatt Energy Sensor."""

    def __init__(self, coordinator, entity, mac_address, name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, entity=entity, mac_address=mac_address, name=name
        )

        self._ent = entity
        self._name = name
        self._io_type = self.coordinator.data["sensors"][self._ent].getType()
        self._state = None

        unit = self.coordinator.data["sensors"][self._ent].getUnit()
        if unit == "Watts":
            self._attr_unit_of_measurement = POWER_WATT
            self._attr_device_class = DEVICE_CLASS_POWER
        elif unit == "Volts":
            self._attr_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT
            self._attr_device_class = DEVICE_CLASS_VOLTAGE
        else:
            self._attr_unit_of_measurement = unit

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        if self._io_type == "Input":
            channel = self.coordinator.data["sensors"][self._ent].getChannel()
        else:
            channel = "N/A"

        return {"Type": self._io_type, "Channel": channel}

    @property
    def state(self):
        """Return the state of the sensor."""
        return self.coordinator.data["sensors"][self._ent].getValue()

    @property
    def name(self):
        """Return the name of the sensor."""
        name = (
            "IoTaWatt "
            + str(self._io_type)
            + " "
            + str(self.coordinator.data["sensors"][self._ent].getName())
        )
        return name

    @property
    def unique_id(self) -> str:
        """Return the Uniqie ID for the sensor."""
        return self.coordinator.data["sensors"][self._ent].getSensorID()
