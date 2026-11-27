from __future__ import annotations

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


def _scene_keys(data: dict) -> set[tuple[int, int]]:
    return {
        (int(x["bus"]), int(x["scene"]))
        for x in data.get("scenes", [])
        if int(x.get("member_count", 0)) > 0
    }


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    known: set[tuple[int, int]] = set()

    @callback
    def add_new() -> None:
        new = _scene_keys(coordinator.data) - known
        if new:
            known.update(new)
            async_add_entities(PulsarDaliScene(coordinator, bus, scene) for bus, scene in sorted(new))

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class PulsarDaliScene(CoordinatorEntity, Scene):
    _attr_has_entity_name = True

    def __init__(self, coordinator, bus: int, scene: int) -> None:
        super().__init__(coordinator)
        self.bus = bus
        self.scene = scene
        controller_id = coordinator.data["controller_id"]
        self._attr_unique_id = f"{controller_id}_scene_{bus}_{scene}"
        self._attr_name = f"Scene {scene}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}:scene:{bus}:{scene}")},
            name=f"DALI {bus} scene {scene}",
            model="DALI scene",
            via_device=(DOMAIN, controller_id),
        )

    @property
    def scene_data(self) -> dict:
        for item in self.coordinator.data.get("scenes", []):
            if int(item.get("bus", -1)) == self.bus and int(item.get("scene", -1)) == self.scene:
                return item
        return {}

    @property
    def available(self) -> bool:
        return bool(self.scene_data.get("online", False)) and self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "dali_bus": self.bus,
            "dali_scene": self.scene,
            "members": self.scene_data.get("members", []),
            "levels": self.scene_data.get("levels", {}),
        }

    async def async_activate(self, **kwargs) -> None:
        await self.coordinator.api.activate_scene(self.bus, self.scene)
        await self.coordinator.async_request_refresh()
