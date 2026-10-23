"""Base entity for JBL PartyBox."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MODEL, DOMAIN, MANUFACTURER
from .coordinator import PartyBoxCoordinator


class PartyBoxEntity(CoordinatorEntity[PartyBoxCoordinator]):
    """Entity bound to one speaker.

    Controls are only available while the speaker is on: in standby it ignores
    everything except power-on.
    """

    _attr_has_entity_name = True
    needs_power = True

    def __init__(self, coordinator: PartyBoxCoordinator, key: str) -> None:
        super().__init__(coordinator)
        mac = coordinator.mac
        entry = coordinator.config_entry
        self._attr_unique_id = f"{mac}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, mac)},
            connections={(CONNECTION_BLUETOOTH, mac)},
            manufacturer=MANUFACTURER,
            model=entry.data.get(CONF_MODEL),
            name=entry.title,
        )

    @property
    def available(self) -> bool:
        if self.needs_power:
            return self.coordinator.powered_on
        return self.coordinator.seen
