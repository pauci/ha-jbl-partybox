"""Selects for JBL PartyBox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import PartyBoxConfigEntry, PartyBoxCoordinator
from .entity import PartyBoxEntity
from .protocol import BassBoost, Cmd, PartyBoxState, UsbMode

EQ_CUSTOM = "custom"


def _eq_option(state: PartyBoxState) -> str | None:
    if state.eq_preset == protocol.EQ_CUSTOM:
        return EQ_CUSTOM
    return protocol.EQ_PRESETS.get(state.eq_preset)


def _eq_frame(state: PartyBoxState, option: str) -> bytes:
    if option == EQ_CUSTOM:
        return protocol.set_eq_custom(state.eq_bands)
    preset = next(k for k, v in protocol.EQ_PRESETS.items() if v == option)
    return protocol.set_eq_preset(preset)


@dataclass(frozen=True, kw_only=True)
class PartyBoxSelectDescription(SelectEntityDescription):
    """Describes a PartyBox select."""

    value_fn: Callable[[PartyBoxState], str | None]
    frame_fn: Callable[[PartyBoxState, str], bytes]
    refresh: Cmd | None
    """Page to re-read; None when the speaker pushes the change itself."""


def _enum_select(
    key: str,
    enum: type[BassBoost | UsbMode],
    attr: str,
    frame,
    refresh: Cmd | None,
    **kw,
) -> PartyBoxSelectDescription:
    names = {member.value: member.name.lower() for member in enum}
    return PartyBoxSelectDescription(
        key=key,
        translation_key=key,
        options=list(names.values()),
        value_fn=lambda s: names.get(getattr(s, attr)),
        frame_fn=lambda _s, option: frame(enum[option.upper()]),
        refresh=refresh,
        **kw,
    )


SELECTS: tuple[PartyBoxSelectDescription, ...] = (
    PartyBoxSelectDescription(
        key="equalizer",
        translation_key="equalizer",
        options=[*protocol.EQ_PRESETS.values(), EQ_CUSTOM],
        value_fn=_eq_option,
        frame_fn=_eq_frame,
        refresh=Cmd.REQ_EQ,
    ),
    _enum_select(
        "bass_boost",
        BassBoost,
        "bass_boost",
        protocol.set_bass_boost,
        None,
    ),
    _enum_select(
        "usb_mode",
        UsbMode,
        "usb_mode",
        protocol.set_usb_mode,
        Cmd.REQ_DEV_INFO,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the selects."""
    coordinator = entry.runtime_data
    async_add_entities(PartyBoxSelect(coordinator, d) for d in SELECTS)


class PartyBoxSelect(PartyBoxEntity, SelectEntity):
    """A PartyBox select."""

    entity_description: PartyBoxSelectDescription

    def __init__(
        self, coordinator: PartyBoxCoordinator, description: PartyBoxSelectDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def current_option(self) -> str | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_select_option(self, option: str) -> None:
        description = self.entity_description
        frame = description.frame_fn(self.coordinator.data, option)
        client = self.coordinator.client
        # Changing the USB mode also resets bass boost, so re-read everything.
        refresh = description.refresh
        await self.coordinator.async_command(
            lambda: client.send(frame, refresh=refresh)
        )
        if description.key == "usb_mode":
            await self.coordinator.async_request_refresh()
