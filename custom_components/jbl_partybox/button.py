"""Sound effect buttons (Effect Lab) for JBL PartyBox."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import PartyBoxConfigEntry, PartyBoxCoordinator
from .entity import PartyBoxEntity

BUTTONS: tuple[tuple[ButtonEntityDescription, bytes], ...] = (
    *(
        (ButtonEntityDescription(key=name, translation_key=name), protocol.dj_tone(i))
        for name, i in protocol.DJ_TONES.items()
    ),
    *(
        (ButtonEntityDescription(key=name, translation_key=name), protocol.dj_voice(i))
        for name, i in protocol.DJ_VOICES.items()
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sound effect buttons."""
    coordinator = entry.runtime_data
    async_add_entities(PartyBoxButton(coordinator, d, f) for d, f in BUTTONS)


class PartyBoxButton(PartyBoxEntity, ButtonEntity):
    """Plays one sound effect."""

    def __init__(
        self,
        coordinator: PartyBoxCoordinator,
        description: ButtonEntityDescription,
        frame: bytes,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._frame = frame

    async def async_press(self) -> None:
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.send(self._frame))
