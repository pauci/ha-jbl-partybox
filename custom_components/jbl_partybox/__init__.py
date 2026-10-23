"""The JBL PartyBox integration."""

from __future__ import annotations

import asyncio

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from . import protocol
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DURATION,
    ATTR_EFFECT,
    ATTR_LEVEL,
    CONF_STAY_CONNECTED,
    DOMAIN,
    SERVICE_DJ_EFFECT,
)
from .coordinator import PartyBoxConfigEntry, PartyBoxCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

DJ_EFFECT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_EFFECT): vol.In(list(protocol.DJ_FILTERS)),
        vol.Optional(ATTR_LEVEL, default=protocol.DJ_FILTER_LEVEL_MAX): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=protocol.DJ_FILTER_LEVEL_MAX)
        ),
        vol.Optional(ATTR_DURATION, default=2.0): vol.All(
            vol.Coerce(float), vol.Range(min=0.2, max=30)
        ),
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""

    async def dj_effect(call: ServiceCall) -> None:
        entry: PartyBoxConfigEntry | None = hass.config_entries.async_get_entry(
            call.data[ATTR_CONFIG_ENTRY_ID]
        )
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_not_loaded"
            )
        coordinator = entry.runtime_data
        effect = protocol.DJ_FILTERS[call.data[ATTR_EFFECT]]
        level = call.data[ATTR_LEVEL]

        async def hold() -> None:
            client = coordinator.client
            await client.send(protocol.dj_filter(effect, level))
            try:
                await asyncio.sleep(call.data[ATTR_DURATION])
            finally:
                await client.send(protocol.dj_filter(effect, 0))

        await coordinator.async_command(hold)

    hass.services.async_register(
        DOMAIN, SERVICE_DJ_EFFECT, dj_effect, schema=DJ_EFFECT_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PartyBoxConfigEntry) -> bool:
    """Set up a JBL PartyBox from a config entry."""
    coordinator = PartyBoxCoordinator(hass, entry)
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_start())
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: PartyBoxConfigEntry
) -> None:
    entry.runtime_data.async_set_stay_connected(
        entry.options.get(CONF_STAY_CONNECTED, False)
    )


async def async_unload_entry(hass: HomeAssistant, entry: PartyBoxConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded
