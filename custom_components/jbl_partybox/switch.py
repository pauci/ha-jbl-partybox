"""Switches for JBL PartyBox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import PartyBoxConfigEntry, PartyBoxCoordinator
from .entity import PartyBoxEntity
from .protocol import Cmd, LightZone, PartyBoxState


@dataclass(frozen=True, kw_only=True)
class PartyBoxSwitchDescription(SwitchEntityDescription):
    """Describes a PartyBox switch."""

    value_fn: Callable[[PartyBoxState], bool | None]
    frame_fn: Callable[[bool], bytes]
    refresh: Cmd | None
    """Page to re-read; None when the speaker pushes the change itself."""


def _zone(key: str, zone: LightZone) -> PartyBoxSwitchDescription:
    return PartyBoxSwitchDescription(
        key=key,
        translation_key=key,
        value_fn=lambda s: s.light_zones.get(zone),
        frame_fn=lambda on: protocol.set_light_zone(zone, on),
        refresh=None,
    )


SWITCHES: tuple[PartyBoxSwitchDescription, ...] = (
    _zone("light_ring", LightZone.RING),
    _zone("light_dots", LightZone.DOTS),
    _zone("light_strobe", LightZone.STROBE),
    _zone("light_strips", LightZone.STRIPS),
    PartyBoxSwitchDescription(
        key="feedback_tone",
        translation_key="feedback_tone",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.feedback_tone,
        frame_fn=protocol.set_feedback_tone,
        refresh=Cmd.REQ_FEEDBACK_TONE,
    ),
    PartyBoxSwitchDescription(
        key="child_lock",
        translation_key="child_lock",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda s: s.lock_panel,
        frame_fn=protocol.set_lock_panel,
        refresh=Cmd.REQ_DEV_INFO,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data
    async_add_entities(PartyBoxSwitch(coordinator, d) for d in SWITCHES)


class PartyBoxSwitch(PartyBoxEntity, SwitchEntity):
    """A PartyBox switch."""

    entity_description: PartyBoxSwitchDescription

    def __init__(
        self, coordinator: PartyBoxCoordinator, description: PartyBoxSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        description = self.entity_description
        client = self.coordinator.client
        await self.coordinator.async_command(
            lambda: client.send(description.frame_fn(on), refresh=description.refresh)
        )
