from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback

from .entity import PulsarDaliControllerEntity, PulsarDaliGearEntity, PulsarDaliInputEntity

DIAGNOSTICS = {
    "control_gear_failure": ("Control gear failure", BinarySensorDeviceClass.PROBLEM),
    "lamp_failure": ("Lamp failure", BinarySensorDeviceClass.PROBLEM),
    "limit_error": ("Limit error", BinarySensorDeviceClass.PROBLEM),
    "address_conflict": ("DALI address conflict", BinarySensorDeviceClass.PROBLEM),
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    coordinator = entry.runtime_data.coordinator
    entities = [PulsarDaliBusSensor(coordinator, bus) for bus in (1, 2, 3)]
    async_add_entities(entities)
    known: set[tuple[str, str]] = set()

    @callback
    def add_new() -> None:
        new_entities = []
        for item in coordinator.data.get("gear", []):
            uid = item.get("ha_uid")
            if uid is None:
                continue
            for field, (name, device_class) in DIAGNOSTICS.items():
                key = (str(uid), field)
                if key not in known:
                    known.add(key)
                    new_entities.append(
                        PulsarDaliGearDiagnostic(
                            coordinator,
                            str(uid),
                            int(item["bus"]),
                            int(item["address"]),
                            field,
                            name,
                            device_class,
                        )
                    )
        if new_entities:
            async_add_entities(new_entities)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))

    known_occupancy: set[tuple[int, int, int]] = set()

    @callback
    def add_occupancy() -> None:
        entities = []
        for item in coordinator.data.get("input_instances", []):
            if int(item.get("instance_type", -1)) != 3:
                continue
            key = (int(item["bus"]), int(item["address"]), int(item["instance"]))
            if key in known_occupancy:
                continue
            known_occupancy.add(key)
            entities.append(PulsarDaliOccupancy(coordinator, *key))
        if entities:
            async_add_entities(entities)

    add_occupancy()
    entry.async_on_unload(coordinator.async_add_listener(add_occupancy))


class PulsarDaliBusSensor(PulsarDaliControllerEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, bus: int) -> None:
        super().__init__(coordinator)
        self.bus = bus
        self._attr_name = f"DALI {bus} connection"
        self._attr_unique_id = f"{coordinator.data['controller_id']}_bus_{bus}_connection"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("buses", {}).get(str(self.bus), {}).get("online", False))


class PulsarDaliGearDiagnostic(PulsarDaliGearEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, ha_uid: str, bus: int, address: int, field: str, name: str, device_class) -> None:
        super().__init__(coordinator, ha_uid, bus, address)
        self.field = field
        self._attr_name = name
        self._attr_device_class = device_class
        self._attr_unique_id = f"{coordinator.data['controller_id']}_gear_{ha_uid}_{field}"

    @property
    def is_on(self) -> bool | None:
        value = self.gear.get(self.field)
        return bool(value) if value is not None else None


class PulsarDaliOccupancy(PulsarDaliInputEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator, bus: int, address: int, instance: int) -> None:
        super().__init__(coordinator, bus, address, instance)
        self._attr_name = f"Occupancy {instance}"
        self._attr_unique_id = f"{coordinator.data['controller_id']}_input_{bus}_{address}_{instance}_occupancy"

    @property
    def is_on(self) -> bool | None:
        value = self.input_data.get("occupied")
        return bool(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.input_data
        return {
            "movement": data.get("movement"),
            "dali_bus": self.bus,
            "dali_address": self.address,
            "dali_instance": self.instance,
            "event_scheme": data.get("event_scheme"),
        }
