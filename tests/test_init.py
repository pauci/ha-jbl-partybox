"""Setup, entity and action tests against a fake speaker client."""

from collections.abc import Callable
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jbl_partybox import protocol
from custom_components.jbl_partybox.const import CONF_MAC, CONF_MODEL, DOMAIN
from custom_components.jbl_partybox.protocol import Cmd

from .conftest import MAC, NAME, adv_payload, service_info
from .test_protocol import DEV_INFO, DEV_INFO_2, EQ, LIGHT, PLAYER

REPLIES = {
    Cmd.REQ_DEV_INFO: [DEV_INFO, DEV_INFO_2],
    Cmd.REQ_LIGHT: [LIGHT],
    Cmd.REQ_PLAYER: [PLAYER],
    Cmd.REQ_BASS_BOOST: [bytes.fromhex("aa620100")],
    Cmd.REQ_KARAOKE: [bytes.fromhex("aa7203060700")],
    Cmd.REQ_MIC_INFO: [bytes.fromhex("aad20700010100050101")],
    Cmd.REQ_MIC_INPUTS: [bytes.fromhex("aac20101")],
    Cmd.REQ_EQ: [EQ],
    Cmd.REQ_FEEDBACK_TONE: [bytes.fromhex("aaf20100")],
}


class FakeClient:
    """Stands in for PartyBoxClient: replays captured replies, records commands."""

    def __init__(self, ble_device: Callable, on_frame: Callable) -> None:
        self._on_frame = on_frame
        self.sent: list[str] = []
        self.power: list[bool] = []
        self.connected = False
        self.persistent = False

    def set_persistent(self, persistent: bool) -> None:
        self.persistent = persistent

    def _reply(self, cmd: Cmd) -> None:
        for buf in REPLIES[cmd]:
            for frame in protocol.decode(buf):
                self._on_frame(frame)

    async def refresh(self) -> None:
        for cmd in protocol.REFRESH_QUERIES:
            self._reply(cmd)

    async def send(self, *frames: bytes, refresh: Cmd | None = None) -> None:
        self.sent.extend(f.hex() for f in frames)
        if refresh is not None:
            self._reply(refresh)

    async def power_on(self) -> None:
        self.power.append(True)

    async def power_off(self) -> None:
        self.power.append(False)

    async def disconnect(self) -> None:
        pass


@pytest.fixture
async def client(hass: HomeAssistant, inject) -> FakeClient:
    """Set up the integration with the speaker on and advertising."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=MAC,
        title=NAME,
        data={CONF_MAC: MAC, CONF_MODEL: "JBL PartyBox 320"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.jbl_partybox.coordinator.PartyBoxClient", FakeClient):
        assert await hass.config_entries.async_setup(entry.entry_id)
        inject(service_info())
        await hass.async_block_till_done()
    return entry.runtime_data.client


async def test_state_after_setup(hass: HomeAssistant, client: FakeClient) -> None:
    player = hass.states.get("media_player.garden_partybox_320")
    assert player.state == "playing"
    assert player.attributes["volume_level"] == pytest.approx(3 / 32)

    light = hass.states.get("light.garden_partybox_320_light_show")
    assert light.state == STATE_ON
    assert light.attributes["effect"] == "loop"
    assert light.attributes["rgb_color"] == (0, 255, 0)
    assert "neon" in light.attributes["effect_list"]

    assert hass.states.get("sensor.garden_partybox_320_battery").state == "100"
    assert (
        hass.states.get("binary_sensor.garden_partybox_320_mains_power").state
        == STATE_ON
    )
    assert hass.states.get("select.garden_partybox_320_equalizer").state == "custom"
    assert hass.states.get("select.garden_partybox_320_bass_boost").state == "off"
    assert hass.states.get("number.garden_partybox_320_mic_treble").state == "7"
    assert (
        hass.states.get("switch.garden_partybox_320_speaker_ring_light").state
        == STATE_ON
    )


async def test_commands(hass: HomeAssistant, client: FakeClient) -> None:
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.garden_partybox_320_light_show", "effect": "neon"},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.garden_partybox_320_bass_boost", "option": "punchy"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.garden_partybox_320_strobe"},
        blocking=True,
    )
    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": "button.garden_partybox_320_horn"},
        blocking=True,
    )
    await hass.services.async_call(
        "media_player",
        "volume_set",
        {"entity_id": "media_player.garden_partybox_320", "volume_level": 0.25},
        blocking=True,
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.garden_partybox_320_mic_volume", "value": 12},
        blocking=True,
    )
    assert client.sent == [
        "aa33040031010" + "2",
        "aa630102",
        "aa330400330100",
        "aa550101",
        "aa430400420108",
        "aad3040008010c",
    ]
    # Mic volume can't be read back, so it is kept locally.
    assert hass.states.get("number.garden_partybox_320_mic_volume").state == "12"


async def test_dj_effect_action(hass: HomeAssistant, client: FakeClient) -> None:
    entry_id = hass.config_entries.async_entries(DOMAIN)[0].entry_id
    with patch("custom_components.jbl_partybox.asyncio.sleep"):
        await hass.services.async_call(
            DOMAIN,
            "dj_effect",
            {"config_entry_id": entry_id, "effect": "gater", "level": 3},
            blocking=True,
        )
    assert client.sent == ["aa57020303", "aa57020300"]


async def test_standby(hass: HomeAssistant, client: FakeClient, inject) -> None:
    inject(service_info(adv_payload(power_on=False, battery=0x50)))
    await hass.async_block_till_done()
    assert hass.states.get("media_player.garden_partybox_320").state == STATE_OFF
    assert (
        hass.states.get("light.garden_partybox_320_light_show").state
        == STATE_UNAVAILABLE
    )
    # Battery comes from the advertisement and stays available.
    assert hass.states.get("sensor.garden_partybox_320_battery").state == "80"
    assert (
        hass.states.get("binary_sensor.garden_partybox_320_mains_power").state
        == STATE_OFF
    )

    await hass.services.async_call(
        "media_player",
        "turn_on",
        {"entity_id": "media_player.garden_partybox_320"},
        blocking=True,
    )
    assert client.power == [True]
    assert hass.states.get("media_player.garden_partybox_320").state == "playing"


async def test_ignores_other_speakers(
    hass: HomeAssistant, client: FakeClient, inject
) -> None:
    inject(service_info(adv_payload(power_on=False, mac="11:22:33:44:55:66")))
    await hass.async_block_till_done()
    assert hass.states.get("media_player.garden_partybox_320").state == "playing"


async def test_unload(hass: HomeAssistant, client: FakeClient) -> None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_mic_controls_follow_the_dongle(
    hass: HomeAssistant, client: FakeClient
) -> None:
    assert hass.states.get("binary_sensor.garden_partybox_320_mic_input_1").state == (
        STATE_ON
    )
    assert hass.states.get("binary_sensor.garden_partybox_320_mic_input_2").state == (
        STATE_OFF
    )
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    coordinator._on_frame(protocol.decode(bytes.fromhex("aac20100"))[0])
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.garden_partybox_320_mic_input_1").state == (
        STATE_OFF
    )
    assert (
        hass.states.get("number.garden_partybox_320_mic_echo").state
        == STATE_UNAVAILABLE
    )


async def test_failed_refresh_retries_soon(
    hass: HomeAssistant, client: FakeClient
) -> None:
    from custom_components.jbl_partybox.client import PartyBoxNotFound
    from custom_components.jbl_partybox.const import REFRESH_INTERVAL, RETRY_INTERVAL

    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data

    async def fail() -> None:
        raise PartyBoxNotFound("proxy not connected yet")

    with patch.object(client, "refresh", fail):
        await coordinator.async_refresh()
    assert coordinator.update_interval == RETRY_INTERVAL
    await coordinator.async_refresh()
    assert coordinator.update_interval == REFRESH_INTERVAL


async def test_stay_connected_option(
    hass: HomeAssistant, client: FakeClient, inject
) -> None:
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert not client.persistent

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"stay_connected": True}
    )
    await hass.async_block_till_done()
    assert entry.options == {"stay_connected": True}
    assert client.persistent

    # In standby there's nothing to stay connected to.
    inject(service_info(adv_payload(power_on=False)))
    await hass.async_block_till_done()
    assert not client.persistent


async def test_mic_inputs_from_device_info(hass: HomeAssistant, client: FakeClient):
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    coordinator._on_frame(protocol.decode(bytes.fromhex("aa120400430103"))[0])
    await hass.async_block_till_done()
    for number in (1, 2):
        state = hass.states.get(f"binary_sensor.garden_partybox_320_mic_input_{number}")
        assert state.state == STATE_ON


async def test_connects_to_latest_address(
    hass: HomeAssistant, client: FakeClient, inject
) -> None:
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    assert coordinator._ble_device().address == "61:75:43:A1:51:C7"
    # Seen only by a passive scanner: can't connect to it there.
    inject(service_info(address="70:11:22:33:44:55", connectable=False))
    await hass.async_block_till_done()
    assert coordinator._ble_device().address == "61:75:43:A1:51:C7"
    inject(service_info(address="70:11:22:33:44:55", connectable=True))
    await hass.async_block_till_done()
    assert coordinator._ble_device().address == "70:11:22:33:44:55"
