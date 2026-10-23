"""Client tests with a fake BLE link."""

import asyncio
from unittest.mock import patch

import pytest
from bleak.backends.device import BLEDevice

from custom_components.jbl_partybox import client as client_module
from custom_components.jbl_partybox import protocol
from custom_components.jbl_partybox.client import (
    PartyBoxClient,
    PartyBoxNoResponse,
    PartyBoxRejected,
)
from custom_components.jbl_partybox.protocol import Cmd, Frame


class FakeLink:
    """A BleakClient that answers like the speaker."""

    def __init__(self, fail_writes: int = 0, silent: bool = False) -> None:
        self.is_connected = True
        self.written: list[str] = []
        self.fail_writes = fail_writes
        self.silent = silent
        self._notify = None

    async def start_notify(self, _uuid, callback) -> None:
        self._notify = callback

    async def write_gatt_char(self, _uuid, data: bytes, response: bool) -> None:
        if self.fail_writes:
            self.fail_writes -= 1
            raise TimeoutError("link dropped")
        self.written.append(data.hex())
        if self.silent:
            return
        cmd = data[1]
        if cmd == Cmd.REQ_DEV_INFO:
            reply = "aa120400330164"
        elif cmd == Cmd.SET_PLAYER and data[-1] > protocol.VOLUME_MAX:
            reply = f"aa0002{cmd:02x}ff"
        elif cmd & 0x0F == 1:
            reply = f"aa{cmd + 1:02x}0100"
        else:
            reply = f"aa0002{cmd:02x}00"
        asyncio.get_running_loop().call_soon(
            self._notify, None, bytearray.fromhex(reply)
        )

    async def disconnect(self) -> None:
        self.is_connected = False


@pytest.fixture
def links():
    created: list[FakeLink] = []
    pending: list[FakeLink] = []

    async def establish(*_args, **_kwargs):
        link = pending.pop(0) if pending else FakeLink()
        created.append(link)
        return link

    with (
        patch.object(client_module, "establish_connection", establish),
        patch.object(client_module, "FOLLOW_UP_DELAY", 0),
        patch.object(client_module, "WAKE_INTERVAL", 0.05),
        patch.object(client_module, "IDLE_DISCONNECT", 60),
    ):
        yield created, pending


def _client(frames: list[Frame] | None = None) -> PartyBoxClient:
    return PartyBoxClient(
        lambda: BLEDevice("AA:BB:CC:DD:EE:FF", "PartyBox", None),
        (frames if frames is not None else []).append,
    )


async def test_send_waits_for_ack(links) -> None:
    created, _ = links
    client = _client()
    await client.send(protocol.set_volume(8))
    assert created[0].written == ["aa1100", "aa430400420108"]
    await client.disconnect()


async def test_rejected_command(links) -> None:
    client = _client()
    with pytest.raises(PartyBoxRejected):
        await client.send(protocol.set_volume(40))
    await client.disconnect()


async def test_reconnects_once_when_the_link_drops(links) -> None:
    created, pending = links
    pending.append(FakeLink())
    client = _client()
    await client.send(protocol.set_bass_boost(protocol.BassBoost.DEEP))
    # Drop the link under the client, as a proxy disconnect would.
    created[0].fail_writes = 1
    await client.send(protocol.set_bass_boost(protocol.BassBoost.OFF))
    assert len(created) == 2
    assert created[1].written[-1] == "aa630100"
    await client.disconnect()


async def test_silent_speaker_is_released(links) -> None:
    created, pending = links
    pending.append(FakeLink(silent=True))
    client = _client()
    with pytest.raises(PartyBoxNoResponse):
        await client.send(protocol.set_bass_boost(protocol.BassBoost.DEEP))
    assert not client.connected
    assert not created[0].is_connected


async def test_refresh_reads_every_page(links) -> None:
    created, _ = links
    frames: list[Frame] = []
    client = _client(frames)
    await client.refresh()
    sent = created[0].written
    for cmd in protocol.REFRESH_QUERIES:
        assert protocol.query(cmd).hex() in sent
    assert any(f.cmd == Cmd.RET_DEV_INFO for f in frames)
    await client.disconnect()
