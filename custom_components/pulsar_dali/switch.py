from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .entity import PulsarDaliGearEntity


def _items(data: dict) -> dict[str, dict]:
    return {
        str(item["ha_uid"]): item
        for item in data.get("gear", [])
        if item.get("entity_kind") == "switch" and item.get("ha_uid") is not None
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[str] = set()

    @callback
    def add_new() -> None:
        items = _items(coordinator.data)
        new = set(items) - known
        if new:
            known.update(new)
            async_add_entities(
                PulsarDaliSwitch(coordinator, uid, int(items[uid]["bus"]), int(items[uid]["address"]))
                for uid in sorted(new)
            )

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliSwitch(PulsarDaliGearEntity, SwitchEntity):
    def __init__(self, coordinator, ha_uid: str, bus: int, address: int) -> None:
        super().__init__(coordinator, ha_uid, bus, address)
        self._attr_unique_id = f"{coordinator.data['controller_id']}_gear_{ha_uid}_switch"
        self._attr_name = "Switch"

    @property
    def is_on(self) -> bool:
        return bool(self.gear.get("is_on", False))

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "dali_bus": self.bus,
            "dali_address": self.address,
            "dali_groups": self.gear.get("groups", []),
            "address_conflict": self.gear.get("address_conflict", False),
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.api.set_level(self.bus, self.address, 254)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.set_level(self.bus, self.address, 0)
        await self.coordinator.async_request_refresh()
