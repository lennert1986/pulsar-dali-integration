from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback

from .entity import PulsarDaliGearEntity

PARAMETERS = {
    "min_level": "Minimum level",
    "max_level": "Maximum level",
    "power_on_level": "Power-on level",
    "system_failure_level": "System failure level",
}


def _items(data: dict) -> dict[str, dict]:
    return {str(x["ha_uid"]): x for x in data.get("gear", []) if x.get("ha_uid") is not None}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[tuple[str, str]] = set()

    @callback
    def add_new() -> None:
        entities = []
        items = _items(coordinator.data)
        for uid, item in sorted(items.items()):
            for parameter, name in PARAMETERS.items():
                key = (uid, parameter)
                if key not in known:
                    known.add(key)
                    entities.append(
                        PulsarDaliConfigNumber(
                            coordinator, uid, int(item["bus"]), int(item["address"]), parameter, name
                        )
                    )
        if entities:
            async_add_entities(entities)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliConfigNumber(PulsarDaliGearEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, ha_uid: str, bus: int, address: int, parameter: str, name: str) -> None:
        super().__init__(coordinator, ha_uid, bus, address)
        self.parameter = parameter
        self._attr_name = name
        self._attr_unique_id = f"{coordinator.data['controller_id']}_gear_{ha_uid}_{parameter}"

    @property
    def native_value(self) -> float | None:
        value = self.gear.get(self.parameter)
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.api.set_config(self.bus, self.address, self.parameter, int(value))
        await self.coordinator.async_request_refresh()
