"""Support for IoTaWatt Energy monitor."""
from decimal import Decimal, DecimalException
import logging

from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    DEVICE_CLASS_ENERGY,
    STATE_CLASS_TOTAL_INCREASING,
    SensorEntity,
)
from homeassistant.const import (
    DEVICE_CLASS_ENERGY,
    DEVICE_CLASS_POWER,
    DEVICE_CLASS_VOLTAGE,
    ELECTRIC_POTENTIAL_VOLT,
    ENERGY_WATT_HOUR,
    ENERGY_KILO_WATT_HOUR,
    POWER_WATT,
    TIME_HOURS,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt

from . import IotaWattEntity
from .const import COORDINATOR, DOMAIN, SIGNAL_ADD_DEVICE

_LOGGER = logging.getLogger(__name__)

ATTR_SOURCE_ID = "source"

ICON_INTEGRATION = "mdi:chart-histogram"


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Add sensors for passed config_entry in HA."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATOR]
    sensors = coordinator.data["sensors"]
    entities = []

    for idx, ent in enumerate(sensors):
        sensor = sensors[ent]
        entity = IotaWattSensor(
            coordinator=coordinator,
            entity=ent,
            mac_address=sensor.hub_mac_address,
            name=sensor.getName(),
        )
        entities.append(entity)

    async_add_entities(entities)

    async def async_new_entities(sensor_info):
        """Add an entity."""
        ent = sensor_info["entity"]
        hub_mac_address = sensor_info["mac_address"]
        name = sensor_info["name"]

        entity = IotaWattSensor(
            coordinator=coordinator,
            entity=ent,
            mac_address=hub_mac_address,
            name=name,
        )
        entities = [entity]
        async_add_entities(entities)

    async_dispatcher_connect(hass, SIGNAL_ADD_DEVICE, async_new_entities)


class IotaWattSensor(IotaWattEntity, RestoreEntity):
    """Defines a IoTaWatt Energy Sensor."""

    def __init__(self, coordinator, entity, mac_address, name):
        """Initialize the sensor."""
        super().__init__(
            coordinator=coordinator, entity=entity, mac_address=mac_address, name=name
        )

        sensor = self.coordinator.data["sensors"][entity]
        self._ent = entity
        self._name = name
        self._io_type = sensor.getType()
        self._state = None
        self._attr_state_class = STATE_CLASS_MEASUREMENT
        self._attr_force_update = True

        self._accumulating = False
        self._accumulatingValue = None
        self._handle_coordinator_update_called = False

        unit = sensor.getUnit()
        if unit == "Watts":
            self._attr_unit_of_measurement = POWER_WATT
            self._attr_device_class = DEVICE_CLASS_POWER
        elif unit == "WattHours":
            self._attr_unit_of_measurement = ENERGY_WATT_HOUR
            self._attr_device_class = DEVICE_CLASS_ENERGY
            self._attr_state_class = STATE_CLASS_TOTAL_INCREASING
            self._accumulating = not sensor.getFromStart()
        elif unit == "Volts":
            self._attr_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT
            self._attr_device_class = DEVICE_CLASS_VOLTAGE
        else:
            self._attr_unit_of_measurement = unit

    @property
    def _iotawattEntry(self):
        return self.coordinator.data["sensors"][self._ent]

    @property
    def device_state_attributes(self):
        """Return the state attributes of the device."""
        if self._io_type == "Input":
            channel = self._iotawattEntry.getChannel()
        else:
            channel = "N/A"

        attrs = {"type": self._io_type, "channel": channel}
        if self._accumulating:
            attrs["last_update"] = self.coordinator.api.getLastUpdateTime().isoformat()

        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._ent not in self.coordinator.data["sensors"]:
            entity_registry.async_get(self.hass).async_remove(self.entity_id)
            return

        if self._accumulating:
            assert (
                self._accumulatedValue is not None
            ), "async_added_to_hass must have been called first"
            _LOGGER.debug(
                f"Accumulating sensor:{self._ent} value:{round(self._accumulatedValue, 3)} with:{self._iotawattEntry.getValue()}"
            )
            self._accumulatedValue += Decimal(self._iotawattEntry.getValue())

        self._handle_coordinator_update_called = True
        super()._handle_coordinator_update()

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        assert (
            not self._handle_coordinator_update_called
        ), "_handle_coordinator_update_called must not have been called yet"

        await super().async_added_to_hass()
        if self._accumulating:
            state = await self.async_get_last_state()
            newValue = Decimal(self._iotawattEntry.getValue())
            if state:
                try:
                    self._accumulatedValue = Decimal(state.state) + newValue
                    _LOGGER.debug(
                        f"Entity:{self._ent} Restored:{Decimal(state.state)} newValue:{newValue}"
                    )
                except (DecimalException, ValueError) as err:
                    _LOGGER.warning("Could not restore last state: %s", err)
                    self._accumulatedValue = newValue
            else:
                # No previous history (first setup), set the first one to the last read.
                self._accumulatedValue = newValue
            self.async_write_ha_state()

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self._accumulating:
            return self._iotawattEntry.getValue()
        # Will return None if state hasn't yet been restored.
        return round(self._accumulatedValue, 1) if self._accumulatedValue else None

    @property
    def last_reset(self):
        """Return the time when the sensor was last reset, if any."""
        last_reset = self._iotawattEntry.getBegin()
        if last_reset is None or self._accumulating:
            return None
        return dt.parse_datetime(last_reset)

    @property
    def name(self):
        """Return the name of the sensor."""
        name = (
            "IoTaWatt "
            + str(self._io_type)
            + " "
            + str(self._iotawattEntry.getName())
            + (".accumulated" if self._accumulating else "")
        )
        return name

    @property
    def unique_id(self) -> str:
        """Return the Unique ID for the sensor."""
        return self._iotawattEntry.getSensorID() + (
            ".accumulated" if self._accumulating else ""
        )

    @property
    def icon(self):
        """Return the icon for the entity."""
        if self._accumulating:
            return ICON_INTEGRATION
        return super().icon
