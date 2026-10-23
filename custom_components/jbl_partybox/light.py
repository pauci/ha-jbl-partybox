"""Light show for JBL PartyBox."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol
from .coordinator import PartyBoxConfigEntry
from .entity import PartyBoxEntity

_EFFECT_TO_MODE = {name: mode for mode, name in protocol.LIGHT_PATTERNS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PartyBoxConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the light show."""
    async_add_entities([PartyBoxLight(entry.runtime_data, "light_show")])


class PartyBoxLight(PartyBoxEntity, LightEntity):
    """The light show: on/off, pattern and custom colour.

    The speaker has no brightness setting; brightness scales the colour.
    """

    _attr_translation_key = "light_show"
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature.EFFECT

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.light_on

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self.coordinator.data.light_color

    @property
    def brightness(self) -> int | None:
        color = self.coordinator.data.light_color
        return max(color) if color else None

    @property
    def effect_list(self) -> list[str]:
        modes = self.coordinator.data.light_modes or list(protocol.LIGHT_PATTERNS)
        return [
            protocol.LIGHT_PATTERNS[m] for m in modes if m in protocol.LIGHT_PATTERNS
        ]

    @property
    def effect(self) -> str | None:
        mode = self.coordinator.data.light_mode
        return None if mode is None else protocol.LIGHT_PATTERNS.get(mode)

    async def async_turn_on(self, **kwargs: Any) -> None:
        frames: list[bytes] = []
        if not self.is_on:
            frames.append(protocol.set_light_on(True))
        if (effect := kwargs.get(ATTR_EFFECT)) in _EFFECT_TO_MODE:
            frames.append(protocol.set_light_mode(_EFFECT_TO_MODE[effect]))
        rgb = kwargs.get(ATTR_RGB_COLOR)
        if ATTR_BRIGHTNESS in kwargs:
            base = rgb or self.rgb_color or (255, 255, 255)
            peak = max(base) or 255
            scale = kwargs[ATTR_BRIGHTNESS] / peak
            rgb = tuple(min(255, round(c * scale)) for c in base)
        if rgb is not None:
            frames.append(protocol.set_light_color(rgb))
        if frames:
            await self._send(*frames)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send(protocol.set_light_on(False))

    async def _send(self, *frames: bytes) -> None:
        # The speaker pushes the light page after every change.
        client = self.coordinator.client
        await self.coordinator.async_command(lambda: client.send(*frames))
