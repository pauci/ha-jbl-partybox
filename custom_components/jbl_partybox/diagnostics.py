"""Diagnostics for JBL PartyBox."""

from __future__ import annotations

import dataclasses
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_MAC
from .coordinator import PartyBoxConfigEntry

TO_REDACT = {CONF_MAC, "serial", "12"}
"""Frame 0x12 (device info) carries the serial number and MAC."""


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PartyBoxConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    state = dataclasses.asdict(coordinator.data)
    state["raw"] = async_redact_data(state["raw"], TO_REDACT)
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "seen": coordinator.seen,
        "connected": coordinator.client.connected,
        "state": async_redact_data(state, TO_REDACT),
    }
