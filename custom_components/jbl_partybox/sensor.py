"""Battery sensor for JBL PartyBox."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PartyBoxConfigEntry
from .entity import PartyBoxEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the battery sensor."""
    async_add_entities([PartyBoxBattery(entry.runtime_data, "battery")])


class PartyBoxBattery(PartyBoxEntity, SensorEntity):
    """Battery level, from the advertisement (works in standby too)."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    needs_power = False

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.battery
