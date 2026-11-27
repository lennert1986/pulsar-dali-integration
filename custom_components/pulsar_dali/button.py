from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback

from .entity import PulsarDaliControllerEntity, PulsarDaliGearEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    async_add_entities([PulsarDaliScanButton(coordinator, None)] + [PulsarDaliScanButton(coordinator, bus) for bus in (1, 2, 3)])
    known: set[str] = set()

    @callback
    def add_new() -> None:
        entities = []
        for item in coordinator.data.get("gear", []):
            uid = item.get("ha_uid")
            if uid is None or str(uid) in known:
                continue
            known.add(str(uid))
            entities.append(
                PulsarDaliIdentifyButton(
                    coordinator, str(uid), int(item["bus"]), int(item["address"])
                )
            )
        if entities:
            async_add_entities(entities)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliScanButton(PulsarDaliControllerEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, bus: int | None) -> None:
        super().__init__(coordinator)
        self.bus = bus
        suffix = "all" if bus is None else str(bus)
        self._attr_name = "Scan all DALI buses" if bus is None else f"Scan DALI {bus}"
        self._attr_unique_id = f"{coordinator.data['controller_id']}_scan_{suffix}"

    async def async_press(self) -> None:
        await self.coordinator.async_scan(None if self.bus is None else [self.bus])


class PulsarDaliIdentifyButton(PulsarDaliGearEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, ha_uid: str, bus: int, address: int) -> None:
        super().__init__(coordinator, ha_uid, bus, address)
        self._attr_name = "Identify"
        self._attr_unique_id = f"{coordinator.data['controller_id']}_gear_{ha_uid}_identify"

    async def async_press(self) -> None:
        await self.coordinator.api.identify(self.bus, self.address)
