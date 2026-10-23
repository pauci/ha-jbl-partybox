"""Shared test fixtures."""

import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_get_advertisement_callback,
)
from homeassistant.core import HomeAssistant

# Make the HA-independent protocol module importable as ``protocol``.
sys.path.insert(
    0, str(Path(__file__).parents[1] / "custom_components" / "jbl_partybox")
)

MAC = "AA:BB:CC:00:11:22"
NAME = "Garden PartyBox 320"
FDDF = "0000fddf-0000-1000-8000-00805f9b34fb"


def adv_payload(power_on: bool = True, battery: int = 0xE4, mac: str = MAC) -> bytes:
    """The 0xFDDF service data the speaker broadcasts."""
    state = 0xD0 if power_on else 0xD3
    return (
        bytes([0xDD, 0x20, 0x01, state, battery, 0, 0, 0x08, 0x04, 0, 0])
        + bytes.fromhex(mac.replace(":", ""))
        + bytes([1, 1, 0, 0, 0, 0, 0])
    )


def service_info(
    payload: bytes | None = None,
    name: str = NAME,
    address: str = "61:75:43:A1:51:C7",
    connectable: bool = True,
) -> BluetoothServiceInfoBleak:
    """An advertisement as Home Assistant's Bluetooth stack reports it."""
    data = {FDDF: payload if payload is not None else adv_payload()}
    adv = AdvertisementData(
        local_name=name,
        manufacturer_data={},
        service_data=data,
        service_uuids=[FDDF],
        tx_power=-4,
        rssi=-60,
        platform_data=(),
    )
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-60,
        manufacturer_data={},
        service_data=data,
        service_uuids=[FDDF],
        source="local",
        device=BLEDevice(address, name, None),
        advertisement=adv,
        connectable=connectable,
        time=time.monotonic(),
        tx_power=-4,
    )


@pytest.fixture(autouse=True)
def auto_enable(enable_custom_integrations, mock_bluetooth):
    """Load custom_components and keep Bluetooth off the real adapters."""
    return


@pytest.fixture
def inject(hass: HomeAssistant) -> Callable[[BluetoothServiceInfoBleak], None]:
    """Feed an advertisement into Home Assistant's Bluetooth stack."""

    def _inject(info: BluetoothServiceInfoBleak) -> None:
        async_get_advertisement_callback(hass)(info)

    return _inject
