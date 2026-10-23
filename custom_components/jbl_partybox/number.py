"""Numbers for JBL PartyBox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import PartyBoxConfigEntry, PartyBoxCoordinator
from .entity import PartyBoxEntity
from .protocol import Cmd, KaraokeParam, PartyBoxState


@dataclass(frozen=True, kw_only=True)
class PartyBoxNumberDescription(NumberEntityDescription):
    """Describes a PartyBox number."""

    value_fn: Callable[[PartyBoxState], int | None]
    frame_fn: Callable[[PartyBoxState, int], bytes]
    refresh: Cmd | None
    optimistic_fn: Callable[[PartyBoxState, int], None] | None = None
    """Store the value locally when the speaker can't be asked for it."""
    needs_mic: bool = False
    """Unavailable while no microphone is plugged in, as in the app."""


def _karaoke(key: str, param: KaraokeParam) -> PartyBoxNumberDescription:
    return PartyBoxNumberDescription(
        key=key,
        translation_key=key,
        native_min_value=0,
        native_max_value=protocol.MIC_LEVEL_MAX,
        native_step=1,
        value_fn=lambda s: s.karaoke.get(param),
        frame_fn=lambda _s, v: protocol.set_karaoke(param, v),
        refresh=Cmd.REQ_KARAOKE,
        needs_mic=True,
    )


def _eq_band(band: int) -> PartyBoxNumberDescription:
    def frame(state: PartyBoxState, value: int) -> bytes:
        bands = list(state.eq_bands)
        bands[band] = value
        return protocol.set_eq_custom(bands)

    return PartyBoxNumberDescription(
        key=f"eq_band_{band + 1}",
        translation_key="eq_band",
        translation_placeholders={"band": str(band + 1)},
        native_min_value=protocol.EQ_BAND_MIN,
        native_max_value=protocol.EQ_BAND_MAX,
        native_step=1,
        mode=NumberMode.SLIDER,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.eq_bands[band],
        frame_fn=frame,
        refresh=Cmd.REQ_EQ,
    )


def _set_mic_volume(state: PartyBoxState, value: int) -> None:
    state.mic_volume = value


NUMBERS: tuple[PartyBoxNumberDescription, ...] = (
    PartyBoxNumberDescription(
        key="mic_volume",
        translation_key="mic_volume",
        native_min_value=0,
        native_max_value=protocol.MIC_VOLUME_MAX,
        native_step=1,
        mode=NumberMode.SLIDER,
        value_fn=lambda s: s.mic_volume,
        frame_fn=lambda _s, v: protocol.set_mic_volume(v),
        refresh=None,
        optimistic_fn=_set_mic_volume,
        needs_mic=True,
    ),
    _karaoke("mic_bass", KaraokeParam.BASS),
    _karaoke("mic_treble", KaraokeParam.TREBLE),
    _karaoke("mic_echo", KaraokeParam.ECHO),
    *(_eq_band(i) for i in range(protocol.EQ_BAND_COUNT)),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers."""
    coordinator = entry.runtime_data
    async_add_entities(PartyBoxNumber(coordinator, d) for d in NUMBERS)


class PartyBoxNumber(PartyBoxEntity, NumberEntity):
    """A PartyBox number."""

    entity_description: PartyBoxNumberDescription

    def __init__(
        self, coordinator: PartyBoxCoordinator, description: PartyBoxNumberDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not self.entity_description.needs_mic or bool(
            self.coordinator.data.mic_inputs
        )

    @property
    def native_value(self) -> int | None:
        return self.entity_description.value_fn(self.coordinator.data)

    async def async_set_native_value(self, value: float) -> None:
        description = self.entity_description
        data = self.coordinator.data
        level = round(value)
        frame = description.frame_fn(data, level)
        client = self.coordinator.client
        await self.coordinator.async_command(
            lambda: client.send(frame, refresh=description.refresh)
        )
        if description.optimistic_fn is not None:
            description.optimistic_fn(data, level)
            self.coordinator.async_update_listeners()
