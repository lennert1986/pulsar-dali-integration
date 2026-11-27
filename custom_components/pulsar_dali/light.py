from __future__ import annotations

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .entity import PulsarDaliGearEntity, PulsarDaliGroupEntity


def _gear_items(data: dict) -> dict[str, dict]:
    return {
        str(item["ha_uid"]): item
        for item in data.get("gear", [])
        if item.get("entity_kind") == "light" and item.get("ha_uid") is not None
    }


def _group_keys(data: dict) -> set[tuple[int, int]]:
    return {
        (int(item["bus"]), int(item["group"]))
        for item in data.get("groups", [])
        if int(item.get("member_count", 0)) > 0
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    known_gear: set[str] = set()
    known_groups: set[tuple[int, int]] = set()

    @callback
    def add_new() -> None:
        entities = []
        items = _gear_items(coordinator.data)
        for ha_uid in sorted(set(items) - known_gear):
            item = items[ha_uid]
            known_gear.add(ha_uid)
            entities.append(PulsarDaliLight(coordinator, ha_uid, int(item["bus"]), int(item["address"])))
        new_groups = _group_keys(coordinator.data) - known_groups
        if new_groups:
            known_groups.update(new_groups)
            entities.extend(PulsarDaliGroupLight(coordinator, bus, group) for bus, group in sorted(new_groups))
        if entities:
            async_add_entities(entities)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliLight(PulsarDaliGearEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator, ha_uid: str, bus: int, address: int) -> None:
        super().__init__(coordinator, ha_uid, bus, address)
        self._attr_unique_id = f"{coordinator.data['controller_id']}_gear_{ha_uid}_light"
        self._attr_name = "Light"

    @property
    def is_on(self) -> bool:
        return bool(self.gear.get("is_on", False))

    @property
    def brightness(self) -> int | None:
        value = self.gear.get("actual_level")
        if value is None:
            return None
        return round(min(254, int(value)) * 255 / 254)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "dali_bus": self.bus,
            "dali_address": self.address,
            "dali_groups": self.gear.get("groups", []),
            "address_conflict": self.gear.get("address_conflict", False),
        }

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        level = 254 if brightness is None else min(254, max(1, round(int(brightness) * 254 / 255)))
        await self.coordinator.api.set_level(self.bus, self.address, level)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.set_level(self.bus, self.address, 0)
        await self.coordinator.async_request_refresh()


class PulsarDaliGroupLight(PulsarDaliGroupEntity, LightEntity):
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator, bus: int, group: int) -> None:
        super().__init__(coordinator, bus, group)
        self._attr_unique_id = f"{coordinator.data['controller_id']}_group_{bus}_{group}_light"
        self._attr_name = "Light"

    @property
    def is_on(self) -> bool:
        return bool(self.group_data.get("is_on", False))

    @property
    def brightness(self) -> int | None:
        value = self.group_data.get("actual_level")
        if value is None:
            return None
        return round(min(254, int(value)) * 255 / 254)

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "dali_bus": self.bus,
            "dali_group": self.group,
            "members": self.group_data.get("members", []),
        }

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        level = 254 if brightness is None else min(254, max(1, round(int(brightness) * 254 / 255)))
        await self.coordinator.api.set_group_level(self.bus, self.group, level)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.api.set_group_level(self.bus, self.group, 0)
        await self.coordinator.async_request_refresh()
