"""Config flow for JBL PartyBox."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback

from . import protocol
from .const import CONF_MAC, CONF_MODEL, CONF_STAY_CONNECTED, DOMAIN, MANUFACTURER


def _parse(info: BluetoothServiceInfoBleak) -> tuple[str, str, str] | None:
    """Return (mac, title, model) for a PartyBox advertisement."""
    data = info.service_data.get(protocol.ADV_SERVICE_DATA_UUID)
    adv = protocol.parse_advertisement(data) if data else None
    name = info.name or ""
    if adv is None or "PartyBox" not in name:
        return None
    # Advertised as e.g. "Garden PartyBox 320": the owner's name, then the model.
    model = name[name.index("PartyBox") :]
    return adv.mac, name, f"{MANUFACTURER} {model}"


class PartyBoxConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for JBL PartyBox."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, tuple[str, str]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PartyBoxOptionsFlow:
        return PartyBoxOptionsFlow()

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """A PartyBox was seen advertising."""
        parsed = _parse(discovery_info)
        if parsed is None:
            return self.async_abort(reason="not_supported")
        mac, title, model = parsed
        await self.async_set_unique_id(mac)
        self._abort_if_unique_id_configured()
        self._discovered = {mac: (title, model)}
        self.context["title_placeholders"] = {"name": title}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered speaker."""
        mac = self.unique_id
        assert mac is not None
        title, model = self._discovered[mac]
        if user_input is not None:
            return self._create(mac, title, model)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm", description_placeholders={"name": title}
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the speakers the Bluetooth scanners see."""
        if user_input is not None:
            mac = user_input[CONF_MAC]
            await self.async_set_unique_id(mac, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            title, model = self._discovered[mac]
            return self._create(mac, title, model)

        configured = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, False):
            parsed = _parse(info)
            if parsed and parsed[0] not in configured:
                self._discovered[parsed[0]] = (parsed[1], parsed[2])
        if not self._discovered:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MAC): vol.In(
                        {mac: title for mac, (title, _m) in self._discovered.items()}
                    )
                }
            ),
        )

    def _create(self, mac: str, title: str, model: str) -> ConfigFlowResult:
        return self.async_create_entry(
            title=title, data={CONF_MAC: mac, CONF_MODEL: model}
        )


class PartyBoxOptionsFlow(OptionsFlow):
    """Options for a speaker."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Optional(CONF_STAY_CONNECTED, default=False): bool}),
                self.config_entry.options,
            ),
        )
