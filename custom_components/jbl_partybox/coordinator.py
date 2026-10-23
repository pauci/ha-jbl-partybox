"""Coordinator for one JBL PartyBox."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from datetime import datetime

from bleak.backends.device import BLEDevice
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import protocol
from .client import PartyBoxClient, PartyBoxError, PartyBoxNoResponse
from .const import (
    CONF_MAC,
    CONF_STAY_CONNECTED,
    DOMAIN,
    POWER_GRACE,
    REFRESH_INTERVAL,
    RETRY_INTERVAL,
    UNAVAILABLE_AFTER,
)
from .protocol import Frame, PartyBoxState

_LOGGER = logging.getLogger(__name__)

type PartyBoxConfigEntry = ConfigEntry[PartyBoxCoordinator]


class PartyBoxCoordinator(DataUpdateCoordinator[PartyBoxState]):
    """Tracks advertisements and talks to the speaker when needed."""

    config_entry: PartyBoxConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PartyBoxConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=REFRESH_INTERVAL,
        )
        self.mac: str = entry.data[CONF_MAC]
        self.data = PartyBoxState()
        self.client = PartyBoxClient(self._ble_device, self._on_frame)
        self._last_seen: float | None = None
        self._seen = False
        self._power_set_at = 0.0
        self.stay_connected: bool = entry.options.get(CONF_STAY_CONNECTED, False)

    @property
    def seen(self) -> bool:
        """Whether the speaker advertised recently."""
        return self._seen

    @property
    def powered_on(self) -> bool:
        return self._seen and bool(self.data.power_on)

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Listen for advertisements; return a function that stops it."""
        unsub_adv = bluetooth.async_register_callback(
            self.hass,
            self._on_advertisement,
            bluetooth.BluetoothCallbackMatcher(
                service_data_uuid=protocol.ADV_SERVICE_DATA_UUID, connectable=False
            ),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
        unsub_timer = async_track_time_interval(
            self.hass, self._check_seen, UNAVAILABLE_AFTER / 5
        )
        unsub_keep = async_track_time_interval(
            self.hass, self._keep_connected, RETRY_INTERVAL
        )
        # Pick up what the scanners already know.
        for info in bluetooth.async_discovered_service_info(self.hass, False):
            if protocol.ADV_SERVICE_DATA_UUID in info.service_data:
                self._on_advertisement(info, bluetooth.BluetoothChange.ADVERTISEMENT)

        def stop() -> None:
            unsub_adv()
            unsub_timer()
            unsub_keep()

        return stop

    @callback
    def async_set_stay_connected(self, stay_connected: bool) -> None:
        """Apply the option without reloading the entry."""
        self.stay_connected = stay_connected
        self._update_persistence()
        if stay_connected and self.powered_on and not self.client.connected:
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "jbl_partybox connect"
            )

    @callback
    def _update_persistence(self) -> None:
        # Only while the speaker is on: in standby it doesn't answer anyway.
        self.client.set_persistent(self.stay_connected and self.powered_on)

    @callback
    def _keep_connected(self, _now: datetime) -> None:
        """Reconnect after the link dropped (speaker restarted, app took over)."""
        if self.stay_connected and self.powered_on and not self.client.connected:
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "jbl_partybox reconnect"
            )

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self.client.disconnect()

    async def _async_update_data(self) -> PartyBoxState:
        if not self.powered_on:
            self.update_interval = REFRESH_INTERVAL
            return self.data
        try:
            await self.client.refresh()
        except PartyBoxError as err:
            # Often a proxy that isn't connected yet after a restart, or the
            # JBL app holding the speaker; try again soon.
            _LOGGER.debug("Refresh failed, retrying soon: %s", err)
            self.update_interval = RETRY_INTERVAL
        else:
            self.update_interval = REFRESH_INTERVAL
        return self.data

    async def async_command(self, command: Callable[[], Awaitable[None]]) -> None:
        """Run a client call and publish the resulting state."""
        try:
            await command()
        except PartyBoxNoResponse as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="no_response"
            ) from err
        except PartyBoxError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="command_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        finally:
            self.async_update_listeners()

    async def async_set_power(self, on: bool) -> None:
        if on:
            await self.async_command(self.client.power_on)
        else:
            await self.async_command(self.client.power_off)
        self.data.power_on = on
        self._power_set_at = time.monotonic()
        self._update_persistence()
        self.async_update_listeners()
        if on:
            await self.async_command(self.client.refresh)

    def _ble_device(self) -> BLEDevice | None:
        """The speaker as most recently seen by something that can connect.

        Its address rotates, so look it up at connect time instead of
        remembering one: a stale address only runs into connect timeouts.
        """
        latest: bluetooth.BluetoothServiceInfoBleak | None = None
        for info in bluetooth.async_discovered_service_info(self.hass, True):
            data = info.service_data.get(protocol.ADV_SERVICE_DATA_UUID)
            adv = protocol.parse_advertisement(data) if data else None
            if (
                adv
                and adv.mac == self.mac
                and (latest is None or info.time > latest.time)
            ):
                latest = info
        return latest.device if latest else None

    @callback
    def _on_frame(self, frame: Frame) -> None:
        state = self.data
        identity = (state.serial, state.firmware)
        if not state.apply(frame):
            return
        if (state.serial, state.firmware) != identity:
            self._update_device_registry()
        self.async_update_listeners()

    @callback
    def _update_device_registry(self) -> None:
        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, self.mac), self.config_entry.entry_id
        )
        if device is not None:
            registry.async_update_device(
                device.id,
                serial_number=self.data.serial,
                sw_version=self.data.firmware,
            )

    @callback
    def _on_advertisement(
        self,
        info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        adv = protocol.parse_advertisement(
            info.service_data.get(protocol.ADV_SERVICE_DATA_UUID, b"")
        )
        if adv is None or adv.mac != self.mac:
            return
        self._last_seen = time.monotonic()
        was_on = self.powered_on
        changed = not self._seen
        self._seen = True
        state = self.data
        if time.monotonic() - self._power_set_at > POWER_GRACE:
            changed |= state.power_on != adv.power_on
            state.power_on = adv.power_on
        before = (state.battery, state.plugged_in)
        state.set_battery_byte(adv.battery_byte)
        changed |= before != (state.battery, state.plugged_in)
        if changed:
            self._update_persistence()
            self.async_update_listeners()
        if self.powered_on and not was_on:
            # Switched on at the speaker or by the app: read what it's set to.
            self.config_entry.async_create_background_task(
                self.hass, self.async_request_refresh(), "jbl_partybox refresh"
            )

    @callback
    def _check_seen(self, _now: datetime) -> None:
        if self._last_seen is None:
            return
        seen = time.monotonic() - self._last_seen < UNAVAILABLE_AFTER.total_seconds()
        if seen != self._seen:
            self._seen = seen
            self._update_persistence()
            self.async_update_listeners()
