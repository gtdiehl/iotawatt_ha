"""IoTaWatt DataUpdateCoordinator."""
from __future__ import annotations

from datetime import timedelta
import logging

from iotawattpy.iotawatt import Iotawatt

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import httpx_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONNECTION_ERRORS

_LOGGER = logging.getLogger(__name__)


class IotawattUpdater(DataUpdateCoordinator):
    """Class to manage fetching update data from the IoTaWatt Energy Device."""

    api: Iotawatt | None = None

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize IotaWattUpdater object."""
        self.entry = entry
        super().__init__(
            hass=hass,
            logger=_LOGGER,
            name=entry.title,
            update_interval=timedelta(seconds=30),
        )

        self._last_run = None
        self._refresh_requested = False

    def updateLastRun(self, last_run):
        # We want to fetch the data from the iotawatt since HA was last shutdown.
        # We retrieve from the sensor last updated.
        # This method is called from each sensor upon their state being restored.
        if self._last_run is None or last_run > self._last_run:
            self._last_run = last_run

    async def request_refresh(self):
        """Request a refresh of the iotawatt sensors"""
        if self._refresh_requested:
            return
        self._refresh_requested = True
        await self.async_request_refresh()

    async def _async_update_data(self):
        """Fetch sensors from IoTaWatt device."""
        if self.api is None:
            api = Iotawatt(
                self.entry.title,
                self.entry.data[CONF_HOST],
                httpx_client.get_async_client(self.hass),
                self.entry.data.get(CONF_USERNAME),
                self.entry.data.get(CONF_PASSWORD),
            )
            try:
                is_authenticated = await api.connect()
            except CONNECTION_ERRORS as err:
                raise UpdateFailed("Connection failed") from err

            if not is_authenticated:
                raise UpdateFailed("Authentication error")

            self.api = api

        await self.api.update(lastUpdate=self._last_run)
        self._last_run = None
        self._refresh_requested = False
        return self.api.getSensors()
