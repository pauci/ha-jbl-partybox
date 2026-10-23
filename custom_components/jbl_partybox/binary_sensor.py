"""Binary sensors for JBL PartyBox."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import PartyBoxConfigEntry, PartyBoxCoordinator
from .entity import PartyBoxEntity
from .protocol import MicInputs


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            PartyBoxPluggedIn(coordinator, "plugged_in"),
            PartyBoxAuracast(coordinator, "auracast"),
            PartyBoxMicInput(coordinator, 1, MicInputs.INPUT_1),
            PartyBoxMicInput(coordinator, 2, MicInputs.INPUT_2),
        ]
    )


class PartyBoxPluggedIn(PartyBoxEntity, BinarySensorEntity):
    """Whether the speaker runs on mains power (and so charges)."""

    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_translation_key = "plugged_in"
    needs_power = False

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.plugged_in


class PartyBoxAuracast(PartyBoxEntity, BinarySensorEntity):
    """Whether the speaker broadcasts over Auracast (its Auracast button)."""

    _attr_translation_key = "auracast"

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.auracast


class PartyBoxMicInput(PartyBoxEntity, BinarySensorEntity):
    """A mic plugged into one input (input 2 only counts in mic mode)."""

    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_translation_key = "mic_input"

    def __init__(
        self, coordinator: PartyBoxCoordinator, number: int, bit: MicInputs
    ) -> None:
        super().__init__(coordinator, f"mic_input_{number}")
        self._attr_translation_placeholders = {"number": str(number)}
        self._bit = bit

    @property
    def is_on(self) -> bool | None:
        inputs = self.coordinator.data.mic_inputs
        return None if inputs is None else bool(inputs & self._bit)
