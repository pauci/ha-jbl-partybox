"""Config flow tests."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jbl_partybox.const import CONF_MAC, CONF_MODEL, DOMAIN

from .conftest import MAC, NAME, adv_payload, service_info

SETUP = "custom_components.jbl_partybox.async_setup_entry"


async def test_bluetooth_discovery(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"

    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {CONF_MAC: MAC, CONF_MODEL: "JBL PartyBox 320"}
    assert result["result"].unique_id == MAC


async def test_bluetooth_discovery_ignores_other_jbl(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_BLUETOOTH},
        data=service_info(name="JBL Flip 6"),
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_bluetooth_discovery_already_configured(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=MAC, data={CONF_MAC: MAC}).add_to_hass(
        hass
    )
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=service_info()
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_picks_a_discovered_speaker(hass: HomeAssistant) -> None:
    other = service_info(
        adv_payload(mac="11:22:33:44:55:66"), name="Party PartyBox 120"
    )
    with patch(
        "custom_components.jbl_partybox.config_flow.async_discovered_service_info",
        return_value=[service_info(), other, service_info(name="JBL Charge 5")],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema[CONF_MAC]
    assert schema.container == {MAC: NAME, "11:22:33:44:55:66": "Party PartyBox 120"}

    with patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MAC: "11:22:33:44:55:66"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MODEL] == "JBL PartyBox 120"


async def test_user_no_speakers(hass: HomeAssistant) -> None:
    with patch(
        "custom_components.jbl_partybox.config_flow.async_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"
