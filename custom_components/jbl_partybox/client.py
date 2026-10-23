"""BLE transport for the JBL PartyBox."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from . import protocol
from .protocol import Cmd, Frame

_LOGGER = logging.getLogger(__name__)

IDLE_DISCONNECT = 30.0
"""Seconds to stay connected after the last command.

The speaker answers only one client at a time, so holding the link would lock
the JBL app out.
"""
REPLY_TIMEOUT = 3.0
WAKE_ATTEMPTS = 8
WAKE_INTERVAL = 1.0
POWER_ON_SETTLE = 3.0
"""The speaker needs a moment after waking before it answers."""
FOLLOW_UP_DELAY = 0.3
"""Some replies come as several frames; give the rest time to arrive."""
HEARTBEAT_INTERVAL = 5.0
"""How often the app pings the speaker while connected; we do the same."""


class PartyBoxError(Exception):
    """Talking to the speaker failed."""


class PartyBoxNotFound(PartyBoxError):
    """No Bluetooth adapter or proxy that can connect sees the speaker."""


class PartyBoxNoResponse(PartyBoxError):
    """The speaker is in standby or another client (the JBL app) holds it."""


class PartyBoxLinkLost(PartyBoxError):
    """The connection dropped while talking to the speaker."""


class PartyBoxRejected(PartyBoxError):
    """The speaker refused a command (for example a value out of range)."""


class PartyBoxClient:
    """Connects on demand and exchanges frames with one speaker."""

    def __init__(
        self,
        ble_device: Callable[[], BLEDevice | None],
        on_frame: Callable[[Frame], None],
    ) -> None:
        self._ble_device = ble_device
        self._on_frame = on_frame
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self._awake = False
        self._waiters: list[tuple[Callable[[Frame], bool], asyncio.Future[Frame]]] = []
        self._idle_handle: asyncio.TimerHandle | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._persistent = False

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def persistent(self) -> bool:
        return self._persistent

    def set_persistent(self, persistent: bool) -> None:
        """Keep the link open (with heartbeats) instead of idling out.

        Gives instant commands and live updates, but locks the JBL app out.
        """
        if persistent == self._persistent:
            return
        self._persistent = persistent
        if self.connected:
            self._schedule_idle_disconnect()

    async def refresh(self) -> None:
        """Read the full state; it arrives through ``on_frame``."""

        async def read_all() -> None:
            for cmd in protocol.REFRESH_QUERIES:
                expected = cmd + 1
                await self._request(
                    protocol.query(cmd), lambda f, e=expected: f.cmd == e
                )
            await asyncio.sleep(FOLLOW_UP_DELAY)

        await self._run(read_all)

    async def send(self, *frames: bytes, refresh: Cmd | None = None) -> None:
        """Send commands, each waiting for its ACK, then optionally re-read a page.

        Pass ``refresh`` only for settings the speaker doesn't push back by
        itself; every round trip through a proxy can take a second.
        """

        async def exchange() -> None:
            for frame in frames:
                await self._command(frame)
            if refresh is not None:
                expected = refresh + 1
                await self._request(
                    protocol.query(refresh), lambda f: f.cmd == expected
                )

        await self._run(exchange)

    async def power_on(self) -> None:
        """Wake the speaker from standby.

        In standby it ignores everything else and sends no ACK, so just write
        the command and wait until it starts answering.
        """
        async with self._lock:
            await self._ensure_connected()
            await self._write(protocol.power(True))
            await asyncio.sleep(POWER_ON_SETTLE)
            self._awake = False
            await self._ensure_awake()
            self._schedule_idle_disconnect()

    async def power_off(self) -> None:
        async with self._lock:
            await self._ensure_awake()
            await self._command(protocol.power(False))
            self._awake = False
            self._schedule_idle_disconnect()

    async def disconnect(self) -> None:
        self._cancel_idle_disconnect()
        self._stop_heartbeat()
        client, self._client = self._client, None
        self._awake = False
        if client is not None:
            with contextlib.suppress(BleakError, TimeoutError):
                await client.disconnect()

    # --- internals -----------------------------------------------------------

    async def _run(self, work: Callable[[], Awaitable[None]]) -> None:
        """Run an exchange on an awake link, reconnecting once if it drops."""
        async with self._lock:
            for attempt in (1, 2):
                await self._ensure_awake()
                try:
                    await work()
                except PartyBoxLinkLost:
                    if attempt == 2:
                        raise
                    _LOGGER.debug("Link lost, reconnecting")
                    continue
                break
            self._schedule_idle_disconnect()

    async def _ensure_connected(self) -> None:
        self._cancel_idle_disconnect()
        if self.connected:
            return
        device = self._ble_device()
        if device is None:
            raise PartyBoxNotFound("No connectable Bluetooth adapter sees the speaker")
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                device.name or device.address,
                disconnected_callback=self._on_disconnected,
                # A rotated (stale) address only times out; fail fast and let
                # the next advertisement supply the new one.
                max_attempts=2,
            )
            await client.start_notify(protocol.NOTIFY_UUID, self._on_notify)
        except (BleakError, TimeoutError) as err:
            raise PartyBoxError(f"Could not connect: {err}") from err
        self._client = client
        self._awake = False
        _LOGGER.debug("Connected to %s", device.address)

    async def _ensure_awake(self) -> None:
        """Connect, then poll device info until the speaker answers.

        It ignores the first commands after a connection, and everything while
        in standby or while another client is connected.
        """
        await self._ensure_connected()
        if self._awake:
            return
        for _ in range(WAKE_ATTEMPTS):
            try:
                await self._request(
                    protocol.query(Cmd.REQ_DEV_INFO),
                    lambda f: f.cmd == Cmd.RET_DEV_INFO,
                    timeout=WAKE_INTERVAL,
                )
            except PartyBoxNoResponse:
                continue
            await asyncio.sleep(FOLLOW_UP_DELAY)
            self._awake = True
            return
        # Nobody is answering; don't hold a link that could block the app.
        await self.disconnect()
        raise PartyBoxNoResponse(
            "The speaker doesn't answer (in standby, or the JBL app is connected)"
        )

    async def _command(self, frame: bytes) -> None:
        cmd = frame[1]
        reply = await self._request(frame, lambda f: f.ack_for == cmd)
        if not reply.ack_ok:
            raise PartyBoxRejected(f"Command {cmd:02x} rejected: {reply.data.hex()}")

    async def _request(
        self,
        frame: bytes,
        match: Callable[[Frame], bool],
        timeout: float = REPLY_TIMEOUT,
    ) -> Frame:
        future: asyncio.Future[Frame] = asyncio.get_running_loop().create_future()
        waiter = (match, future)
        self._waiters.append(waiter)
        try:
            await self._write(frame)
            async with asyncio.timeout(timeout):
                return await future
        except TimeoutError as err:
            raise PartyBoxNoResponse(f"No reply to {frame.hex()}") from err
        finally:
            with contextlib.suppress(ValueError):
                self._waiters.remove(waiter)

    async def _write(self, frame: bytes) -> None:
        if self._client is None:
            raise PartyBoxLinkLost("Not connected")
        _LOGGER.debug("-> %s", frame.hex())
        try:
            await self._client.write_gatt_char(
                protocol.WRITE_UUID, frame, response=True
            )
        except (BleakError, TimeoutError) as err:
            await self.disconnect()
            raise PartyBoxLinkLost(f"Write failed: {err}") from err

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        _LOGGER.debug("<- %s", data.hex())
        for frame in protocol.decode(bytes(data)):
            for match, future in self._waiters:
                if not future.done() and match(frame):
                    future.set_result(frame)
                    break
            self._on_frame(frame)

    def _on_disconnected(self, _client: BleakClientWithServiceCache) -> None:
        _LOGGER.debug("Disconnected")
        self._client = None
        self._awake = False
        self._cancel_idle_disconnect()
        self._stop_heartbeat()

    def _schedule_idle_disconnect(self) -> None:
        self._cancel_idle_disconnect()
        if self._persistent:
            if self._heartbeat is None or self._heartbeat.done():
                self._heartbeat = asyncio.get_running_loop().create_task(
                    self._heartbeat_loop()
                )
            return
        self._stop_heartbeat()
        loop = asyncio.get_running_loop()
        self._idle_handle = loop.call_later(
            IDLE_DISCONNECT, lambda: loop.create_task(self._idle_disconnect())
        )

    def _cancel_idle_disconnect(self) -> None:
        if self._idle_handle is not None:
            self._idle_handle.cancel()
            self._idle_handle = None

    async def _idle_disconnect(self) -> None:
        if self._lock.locked():
            return
        await self.disconnect()

    async def _heartbeat_loop(self) -> None:
        while self.connected and self._persistent:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            async with self._lock:
                if not self.connected or not self._persistent:
                    return
                try:
                    await self._write(protocol.query(Cmd.HEARTBEAT))
                except PartyBoxError as err:
                    _LOGGER.debug("Heartbeat failed: %s", err)
                    return

    def _stop_heartbeat(self) -> None:
        task, self._heartbeat = self._heartbeat, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
