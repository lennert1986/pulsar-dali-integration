from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .api import PulsarDaliApi, PulsarDaliApiError
from .const import CONF_FINGERPRINT, CONF_SCAN_ON_SETUP, CONF_TOKEN, CONF_URL, DOMAIN, PLATFORMS
from .coordinator import PulsarDaliCoordinator

_LOGGER = logging.getLogger(__name__)


def event_signal(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_input_event"


@dataclass
class PulsarDaliRuntimeData:
    api: PulsarDaliApi
    coordinator: PulsarDaliCoordinator
    event_task: asyncio.Task | None = None


async def _event_listener(hass: HomeAssistant, entry: ConfigEntry, runtime: PulsarDaliRuntimeData) -> None:
    since = int(runtime.coordinator.data.get("event_latest_id", 0))
    while True:
        try:
            payload = await runtime.api.events(since=since, wait=25.0)
            since = max(since, int(payload.get("latest_id", since)))
            events = payload.get("events", [])
            for event in events:
                async_dispatcher_send(hass, event_signal(entry.entry_id), event)
            if events:
                await runtime.coordinator.async_request_refresh()
        except asyncio.CancelledError:
            raise
        except PulsarDaliApiError as exc:
            _LOGGER.debug("Pulsar DALI event stream unavailable: %s", exc)
            await asyncio.sleep(2)
        except Exception as exc:  # Keep the listener alive on malformed vendor events.
            _LOGGER.warning("Pulsar DALI event listener error: %s", exc)
            await asyncio.sleep(2)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.info("Setting up %s using %s", entry.title, entry.data[CONF_URL])
    api = PulsarDaliApi(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data.get(CONF_TOKEN),
        entry.data.get(CONF_FINGERPRINT),
    )
    coordinator = PulsarDaliCoordinator(hass, api)

    if entry.data.get(CONF_SCAN_ON_SETUP, True):
        try:
            cached = await api.devices()
            # A full v0.10 scan now includes 16 scene queries per gear and a
            # DALI-2 control-device scan. Reuse the add-on cache on normal HA
            # restarts; the Configure page remains the explicit rescan point.
            if not cached.get("gear") and not cached.get("control_devices"):
                await api.scan([1, 2, 3])
        except Exception:
            pass

    await coordinator.async_config_entry_first_refresh()
    runtime = PulsarDaliRuntimeData(api, coordinator)
    entry.runtime_data = runtime
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    runtime.event_task = entry.async_create_background_task(
        hass,
        _event_listener(hass, entry, runtime),
        "Pulsar DALI input events",
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    runtime = getattr(entry, "runtime_data", None)
    if runtime is not None and runtime.event_task is not None:
        runtime.event_task.cancel()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
