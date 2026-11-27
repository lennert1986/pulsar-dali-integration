from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PulsarDaliCoordinator


class PulsarDaliGearEntity(CoordinatorEntity[PulsarDaliCoordinator]):
    """Base entity keyed by the controller's persistent logical gear token.

    The token keeps the v0.8 unique-id shape (for example ``1_12``) but is
    carried with the gear when the integration changes its DALI short address.
    DALI randomAddress is deliberately not used as an HA identity because
    RANDOMISE changes it during commissioning.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: PulsarDaliCoordinator, ha_uid: str, bus: int, address: int) -> None:
        super().__init__(coordinator)
        self.ha_uid = str(ha_uid)
        self._last_bus = int(bus)
        self._last_address = int(address)
        controller_id = coordinator.data["controller_id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}:gear:{self.ha_uid.replace('_', ':', 1)}")},
            name=f"DALI {bus} gear {address}",
            model=self._model_name,
            via_device=(DOMAIN, controller_id),
        )

    @property
    def gear(self) -> dict:
        for item in self.coordinator.data.get("gear", []):
            if str(item.get("ha_uid")) == self.ha_uid:
                self._last_bus = int(item.get("bus", self._last_bus))
                self._last_address = int(item.get("address", self._last_address))
                return item
        return {}

    @property
    def bus(self) -> int:
        item = self.gear
        return int(item.get("bus", self._last_bus)) if item else self._last_bus

    @property
    def address(self) -> int:
        item = self.gear
        return int(item.get("address", self._last_address)) if item else self._last_address

    @property
    def _model_name(self) -> str:
        item = self.gear
        dt = item.get("device_type")
        source = item.get("light_source_name")
        parts = []
        if dt is not None:
            parts.append(f"DALI DT{dt}")
        if source:
            parts.append(str(source).replace("_", " "))
        return " · ".join(parts) or "DALI control gear"

    @property
    def available(self) -> bool:
        return bool(self.gear.get("online", False)) and not bool(self.gear.get("address_conflict", False)) and self.coordinator.last_update_success


class PulsarDaliGroupEntity(CoordinatorEntity[PulsarDaliCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PulsarDaliCoordinator, bus: int, group: int) -> None:
        super().__init__(coordinator)
        self.bus = bus
        self.group = group
        controller_id = coordinator.data["controller_id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}:group:{bus}:{group}")},
            name=f"DALI {bus} group {group}",
            model="DALI group",
            via_device=(DOMAIN, controller_id),
        )

    @property
    def group_data(self) -> dict:
        for item in self.coordinator.data.get("groups", []):
            if item.get("bus") == self.bus and item.get("group") == self.group:
                return item
        return {}

    @property
    def available(self) -> bool:
        return bool(self.group_data.get("online", False)) and self.coordinator.last_update_success


class PulsarDaliControllerEntity(CoordinatorEntity[PulsarDaliCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PulsarDaliCoordinator) -> None:
        super().__init__(coordinator)
        controller_id = coordinator.data["controller_id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, controller_id)},
            name="Pulsar DALI Controller",
            manufacturer="Glamox / ES-SYSTEM",
            model="Pulsar CM4 DALI gateway",
        )


class PulsarDaliInputEntity(CoordinatorEntity[PulsarDaliCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: PulsarDaliCoordinator, bus: int, address: int, instance: int) -> None:
        super().__init__(coordinator)
        self.bus = int(bus)
        self.address = int(address)
        self.instance = int(instance)
        controller_id = coordinator.data["controller_id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{controller_id}:input:{self.bus}:{self.address}")},
            name=f"DALI {self.bus} input device {self.address}",
            manufacturer="DALI-2",
            model="DALI-2 control device",
            via_device=(DOMAIN, controller_id),
        )

    @property
    def input_data(self) -> dict:
        for item in self.coordinator.data.get("input_instances", []):
            if (
                int(item.get("bus", -1)) == self.bus
                and int(item.get("address", -1)) == self.address
                and int(item.get("instance", -1)) == self.instance
            ):
                return item
        return {}

    @property
    def available(self) -> bool:
        return bool(self.input_data) and self.coordinator.last_update_success
