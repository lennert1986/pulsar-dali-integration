from __future__ import annotations

from homeassistant.components.event import (
    ATTR_MULTI_PRESS_COUNT,
    ButtonEventType,
    EventDeviceClass,
    EventEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from . import event_signal
from .entity import PulsarDaliInputEntity

BUTTON_TYPES = [
    ButtonEventType.PRESS_START,
    ButtonEventType.PRESS_END,
    ButtonEventType.LONG_PRESS_START,
    ButtonEventType.LONG_PRESS_END,
    ButtonEventType.MULTI_PRESS_END,
    "long_press_repeat",
    "button_stuck",
    "button_free",
]



def _button_instances(data: dict) -> set[tuple[int, int, int]]:
    return {
        (int(x["bus"]), int(x["address"]), int(x["instance"]))
        for x in data.get("input_instances", [])
        if int(x.get("instance_type", -1)) == 1
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[tuple[int, int, int]] = set()

    @callback
    def add_new() -> None:
        new = _button_instances(coordinator.data) - known
        if new:
            known.update(new)
            async_add_entities(PulsarDaliButtonEvent(coordinator, entry.entry_id, *key) for key in sorted(new))

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliButtonEvent(PulsarDaliInputEntity, EventEntity):
    _attr_device_class = EventDeviceClass.BUTTON
    _attr_event_types = BUTTON_TYPES

    def __init__(self, coordinator, entry_id: str, bus: int, address: int, instance: int) -> None:
        super().__init__(coordinator, bus, address, instance)
        self.entry_id = entry_id
        self._attr_name = f"Button {instance}"
        self._attr_unique_id = f"{coordinator.data['controller_id']}_input_{bus}_{address}_{instance}_event"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, event_signal(self.entry_id), self._handle_event)
        )

    @callback
    def _handle_event(self, event: dict) -> None:
        if (
            int(event.get("bus", -1)) != self.bus
            or int(event.get("address", -1)) != self.address
            or int(event.get("instance", -1)) != self.instance
            or int(event.get("instance_type", -1)) != 1
        ):
            return
        raw_type = str(event.get("event_type", "button_event"))
        attrs = {
            "dali_bus": self.bus,
            "dali_address": self.address,
            "dali_instance": self.instance,
            "dali_info": event.get("info"),
            "dali_raw_event": raw_type,
        }
        mapped = {
            "button_pressed": ButtonEventType.PRESS_START,
            "button_released": ButtonEventType.PRESS_END,
            "short_press": ButtonEventType.PRESS_END,
            "long_press_start": ButtonEventType.LONG_PRESS_START,
            "long_press_stop": ButtonEventType.LONG_PRESS_END,
            "double_press": ButtonEventType.MULTI_PRESS_END,
            "long_press_repeat": "long_press_repeat",
            "button_stuck": "button_stuck",
            "button_free": "button_free",
        }.get(raw_type, ButtonEventType.PRESS_END)
        if raw_type == "double_press":
            attrs[ATTR_MULTI_PRESS_COUNT] = 2
        self._trigger_event(mapped, attrs)
        self.async_write_ha_state()
