from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EntityCategory

from .entity import PulsarDaliInputEntity


def _sensor_instances(data: dict) -> dict[tuple[int, int, int], dict]:
    return {
        (int(x["bus"]), int(x["address"]), int(x["instance"])): x
        for x in data.get("input_instances", [])
        if int(x.get("instance_type", -1)) in (2, 4)
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[tuple[int, int, int]] = set()

    @callback
    def add_new() -> None:
        items = _sensor_instances(coordinator.data)
        new = set(items) - known
        if new:
            known.update(new)
            async_add_entities(PulsarDaliInputSensor(coordinator, *key) for key in sorted(new))

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliInputSensor(PulsarDaliInputEntity, SensorEntity):
    def __init__(self, coordinator, bus: int, address: int, instance: int) -> None:
        super().__init__(coordinator, bus, address, instance)
        data = self.input_data
        itype = int(data.get("instance_type", -1))
        self._attr_name = "Relative illuminance" if itype == 4 else "Absolute input"
        self._attr_unique_id = f"{coordinator.data['controller_id']}_input_{bus}_{address}_{instance}_sensor"
        # Part 304 is relative illuminance by default; deliberately no lx unit.
        if itype == 2:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        data = self.input_data
        if int(data.get("instance_type", -1)) == 4:
            return data.get("relative_illuminance", data.get("input_value"))
        return data.get("absolute_input", data.get("input_value"))

    @property
    def extra_state_attributes(self) -> dict:
        data = self.input_data
        return {
            "dali_bus": self.bus,
            "dali_address": self.address,
            "dali_instance": self.instance,
            "resolution": data.get("resolution"),
            "event_scheme": data.get("event_scheme"),
            "event_filter": data.get("event_filter"),
        }
