from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PulsarDaliApi, PulsarDaliApiError

_LOGGER = logging.getLogger(__name__)


class PulsarDaliCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, api: PulsarDaliApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="Pulsar DALI",
            update_interval=timedelta(seconds=5),
            always_update=False,
        )
        self.api = api

    async def _async_update_data(self) -> dict:
        try:
            return await self.api.devices()
        except PulsarDaliApiError as exc:
            raise UpdateFailed(str(exc)) from exc

    async def async_scan(self, buses: list[int] | None = None) -> None:
        await self.api.scan(buses)
        await self.async_request_refresh()
