"""Media player for JBL PartyBox: power, volume and playback."""

from __future__ import annotations

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import PartyBoxConfigEntry
from .entity import PartyBoxEntity
from .protocol import Cmd, PlayerState


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the media player."""
    async_add_entities([PartyBoxMediaPlayer(entry.runtime_data, "speaker")])


class PartyBoxMediaPlayer(PartyBoxEntity, MediaPlayerEntity):
    """The speaker itself."""

    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.PLAY
        | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK
        | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )
    _attr_volume_step = 1 / protocol.VOLUME_MAX
    needs_power = False

    @property
    def state(self) -> MediaPlayerState | None:
        data = self.coordinator.data
        if data.power_on is None:
            return None
        if not data.power_on:
            return MediaPlayerState.OFF
        if data.player_state == PlayerState.PLAYING:
            return MediaPlayerState.PLAYING
        if data.player_state == PlayerState.PAUSED:
            return MediaPlayerState.PAUSED
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        volume = self.coordinator.data.volume
        return None if volume is None else volume / protocol.VOLUME_MAX

    @property
    def is_volume_muted(self) -> bool | None:
        return self.coordinator.data.muted

    async def async_turn_on(self) -> None:
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self) -> None:
        await self.coordinator.async_set_power(False)

    async def async_set_volume_level(self, volume: float) -> None:
        # Volume and mute changes are only acknowledged, not pushed back.
        volume_frame = protocol.set_volume(round(volume * protocol.VOLUME_MAX))
        await self._send(volume_frame, refresh=Cmd.REQ_PLAYER)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._send(protocol.set_mute(mute), refresh=Cmd.REQ_PLAYER)

    async def async_media_play(self) -> None:
        await self._send(protocol.set_player_state(PlayerState.PLAYING))

    async def async_media_pause(self) -> None:
        await self._send(protocol.set_player_state(PlayerState.PAUSED))

    async def async_media_next_track(self) -> None:
        await self._send(protocol.set_player_state(PlayerState.NEXT))

    async def async_media_previous_track(self) -> None:
        await self._send(protocol.set_player_state(PlayerState.PREVIOUS))

    async def _send(self, frame: bytes, refresh: Cmd | None = None) -> None:
        client = self.coordinator.client
        await self.coordinator.async_command(
            lambda: client.send(frame, refresh=refresh)
        )
