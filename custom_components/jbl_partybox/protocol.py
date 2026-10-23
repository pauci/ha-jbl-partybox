"""JBL PartyBox BLE protocol: frames, state parsing and command builders.

Kept free of Home Assistant imports so it can be tested on its own. See
docs/PROTOCOL.md for how the protocol was worked out.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

SERVICE_UUID = "65786365-6c70-6f69-6e74-2e636f6d0000"
WRITE_UUID = "65786365-6c70-6f69-6e74-2e636f6d0002"
NOTIFY_UUID = "65786365-6c70-6f69-6e74-2e636f6d0001"
ADV_SERVICE_DATA_UUID = "0000fddf-0000-1000-8000-00805f9b34fb"

SYNC = 0xAA
LONG_LENGTH_COMMANDS = frozenset({0xE1, 0xE2, 0xE3})
"""Commands whose length field is two bytes, big endian."""

VOLUME_MAX = 32
MIC_VOLUME_MAX = 32
MIC_LEVEL_MAX = 12
EQ_BAND_COUNT = 5
EQ_BAND_MIN = -6
EQ_BAND_MAX = 6


class Cmd(IntEnum):
    """Command bytes (names follow the vendor SDK where known)."""

    ACK = 0x00
    POWER = 0x03
    REQ_DEV_INFO = 0x11
    RET_DEV_INFO = 0x12
    SET_DEV_INFO = 0x13
    REQ_LIGHT = 0x31
    RET_LIGHT = 0x32
    SET_LIGHT = 0x33
    REQ_PLAYER = 0x41
    RET_PLAYER = 0x42
    SET_PLAYER = 0x43
    DJ_TONE = 0x55
    DJ_VOICE = 0x56
    DJ_FILTER = 0x57
    REQ_BASS_BOOST = 0x61
    RET_BASS_BOOST = 0x62
    SET_BASS_BOOST = 0x63
    REQ_KARAOKE = 0x71
    RET_KARAOKE = 0x72
    SET_KARAOKE = 0x73
    NOTIFY_KARAOKE = 0x74
    REQ_MIC_INPUTS = 0xC1
    RET_MIC_INPUTS = 0xC2
    REQ_MIC_INFO = 0xD1
    RET_MIC_INFO = 0xD2
    SET_MIC_INFO = 0xD3
    REQ_EQ = 0xE1
    RET_EQ = 0xE2
    SET_EQ = 0xE3
    HEARTBEAT = 0xEA
    REQ_FEEDBACK_TONE = 0xF1
    RET_FEEDBACK_TONE = 0xF2
    SET_FEEDBACK_TONE = 0xF3


POWER_ON = 0x05
POWER_OFF = 0x04

# Device info TLVs (pages 0x11 / 0x12 / 0x13).
DEV_BATTERY = 0x33
DEV_MAC = 0x37
DEV_AURACAST = 0x3C
DEV_MIC_INPUTS = 0x43
DEV_SERIAL = 0x40
DEV_FIRMWARE = 0x41
DEV_LOCK_PANEL = 0x55
DEV_USB_MODE = 0x5C

# Light TLVs (pages 0x31 / 0x32 / 0x33).
LIGHT_MODE = 0x31
LIGHT_COLOR = 0x32
LIGHT_CUSTOM_COLOR = 0x36
LIGHT_MODES_AVAILABLE = 0x4A
LIGHT_ON = 0x99


class LightZone(IntEnum):
    """Light groups that can be switched separately."""

    RING = 0x38
    DOTS = 0x39
    STROBE = 0x33
    STRIPS = 0x44


LIGHT_PATTERNS: dict[int, str] = {
    0x01: "rock",
    0x02: "neon",
    0x03: "club",
    0x04: "flow",
    0x05: "ripple",
    0x06: "cross",
    0x07: "flash",
    0x08: "custom",
    0x09: "loop",
    0x0A: "bounce",
    0x0B: "trim",
    0x0C: "switch",
    0x0D: "freeze",
}

# Player TLVs (pages 0x41 / 0x42 / 0x43).
PLAYER_STATE = 0x41
PLAYER_VOLUME = 0x42
PLAYER_MUTE = 0x43


class PlayerState(IntEnum):
    """Values of the PLAYER_STATE TLV; PREVIOUS and NEXT are commands only."""

    OFF = 0
    PAUSED = 1
    PLAYING = 2
    PREVIOUS = 3
    NEXT = 4


# Mic info TLVs (pages 0xD1 / 0xD2 / 0xD3).
MIC_VOLUME = 0x08


class KaraokeParam(IntEnum):
    """Microphone effect parameters."""

    BASS = 1
    TREBLE = 2
    ECHO = 3


class MicInputs(IntEnum):
    """Which microphone inputs have something plugged in (a bitmask)."""

    NONE = 0
    INPUT_1 = 1
    INPUT_2 = 2
    BOTH = 3


class BassBoost(IntEnum):
    OFF = 0
    DEEP = 1
    PUNCHY = 2


class UsbMode(IntEnum):
    USB_PLAYBACK = 0
    EASYSING_MICS = 1


EQ_CUSTOM = 0xC1
EQ_PRESETS: dict[int, str] = {
    0x06: "jbl_signature",
    0x0A: "movie",
    0x03: "vocal",
    0x0B: "chill",
}
# The app sends each preset with its filter definition; replay them verbatim.
_EQ_PRESET_PAYLOADS: dict[int, bytes] = {
    0x06: bytes.fromhex(
        "06050000bb80010000000042c800003f8000000100000000447a00003f800000"
        "010000000044fa00003f800000010000000045dac0003f8000000100000000461c"
        "40003f800000"
    ),
    0x0A: bytes.fromhex(
        "0a050000bb800040800000431600003f3333330100000000437a00003f800000"
        "014040000044fa00003f8000000240000000459c40003f3333330100000000461c"
        "40003f800000"
    ),
    0x03: bytes.fromhex(
        "03050000bb8000c0a0000042a000003f0000000140800000447a00003f800000"
        "0140800000457a00003f80000001c0000000460ca0003f3333330300000000460c"
        "a0003f333333"
    ),
    0x0B: bytes.fromhex(
        "0b050000bb8000c0800000434800003f0000000100000000447a00003f800000"
        "01c040000044bb80003f80000002c040000045bb80003f0000000300000000461c"
        "40003f333333"
    ),
}

DJ_TONES: dict[str, int] = {
    "horn": 0x01,
    "pac_man": 0x0D,
    "thumbs_up": 0x07,
    "thumbs_down": 0x08,
    "scratch_1": 0x03,
    "scratch_2": 0x04,
    "scratch_3": 0x05,
    "clap": 0x02,
}
DJ_VOICES: dict[str, int] = {
    "lets_go": 0x13,
    "hands_up": 0x10,
    "hey": 0x0F,
    "party": 0x0E,
    "jump": 0x12,
}
DJ_FILTERS: dict[str, int] = {
    "repeater": 1,
    "filter": 2,
    "gater": 3,
    "echo": 4,
    "wipeout": 5,
}
DJ_FILTER_LEVEL_MAX = 4


@dataclass(frozen=True)
class Frame:
    """One protocol frame: command byte and payload."""

    cmd: int
    data: bytes

    @property
    def ack_for(self) -> int | None:
        """The command an ACK frame answers."""
        return self.data[0] if self.cmd == Cmd.ACK and self.data else None

    @property
    def ack_ok(self) -> bool:
        return len(self.data) >= 2 and self.data[1] == 0


def encode(cmd: int, data: bytes = b"") -> bytes:
    """Build a frame."""
    if cmd in LONG_LENGTH_COMMANDS:
        return bytes([SYNC, cmd]) + len(data).to_bytes(2, "big") + data
    return bytes([SYNC, cmd, len(data)]) + data


def decode(buf: bytes) -> list[Frame]:
    """Split a notification into frames; ignore anything malformed."""
    frames: list[Frame] = []
    i = 0
    while i + 3 <= len(buf) and buf[i] == SYNC:
        cmd = buf[i + 1]
        if cmd in LONG_LENGTH_COMMANDS:
            if i + 4 > len(buf):
                break
            length = int.from_bytes(buf[i + 2 : i + 4], "big")
            start = i + 4
        else:
            length = buf[i + 2]
            start = i + 3
        # The speaker sometimes truncates long frames; keep what arrived.
        frames.append(Frame(cmd, bytes(buf[start : start + length])))
        i = start + length
    return frames


def parse_tlv(data: bytes) -> dict[int, bytes]:
    """Parse ``tag, length, value`` triplets, stopping at a truncated one."""
    out: dict[int, bytes] = {}
    i = 0
    while i + 2 <= len(data):
        tag, length = data[i], data[i + 1]
        if i + 2 + length > len(data):
            break
        out[tag] = data[i + 2 : i + 2 + length]
        i += 2 + length
    return out


def _tlv_set(cmd: int, tag: int, value: bytes) -> bytes:
    return encode(cmd, bytes([0, tag, len(value)]) + value)


# --- Commands ----------------------------------------------------------------


def query(cmd: int) -> bytes:
    """A request frame without parameters."""
    return encode(cmd)


def power(on: bool) -> bytes:
    return encode(Cmd.POWER, bytes([POWER_ON if on else POWER_OFF]))


def set_light_on(on: bool) -> bytes:
    return _tlv_set(Cmd.SET_LIGHT, LIGHT_ON, bytes([on]))


def set_light_mode(mode: int) -> bytes:
    return _tlv_set(Cmd.SET_LIGHT, LIGHT_MODE, bytes([mode]))


def set_light_color(rgb: tuple[int, int, int]) -> bytes:
    data = bytes([0, LIGHT_CUSTOM_COLOR, 1, 1, LIGHT_COLOR, 3, *rgb])
    return encode(Cmd.SET_LIGHT, data)


def set_light_zone(zone: LightZone, on: bool) -> bytes:
    return _tlv_set(Cmd.SET_LIGHT, zone, bytes([on]))


def set_player_state(player_state: PlayerState) -> bytes:
    return _tlv_set(Cmd.SET_PLAYER, PLAYER_STATE, bytes([player_state]))


def set_mute(muted: bool) -> bytes:
    return _tlv_set(Cmd.SET_PLAYER, PLAYER_MUTE, bytes([muted]))


def set_volume(volume: int) -> bytes:
    return _tlv_set(Cmd.SET_PLAYER, PLAYER_VOLUME, bytes([volume]))


def set_mic_volume(volume: int) -> bytes:
    return _tlv_set(Cmd.SET_MIC_INFO, MIC_VOLUME, bytes([volume]))


def set_bass_boost(level: BassBoost) -> bytes:
    return encode(Cmd.SET_BASS_BOOST, bytes([level]))


def set_karaoke(param: KaraokeParam, level: int) -> bytes:
    return encode(Cmd.SET_KARAOKE, bytes([param, level]))


def set_feedback_tone(on: bool) -> bytes:
    return encode(Cmd.SET_FEEDBACK_TONE, bytes([on]))


def set_lock_panel(on: bool) -> bytes:
    return _tlv_set(Cmd.SET_DEV_INFO, DEV_LOCK_PANEL, bytes([on]))


def set_usb_mode(mode: UsbMode) -> bytes:
    return _tlv_set(Cmd.SET_DEV_INFO, DEV_USB_MODE, bytes([mode]))


def set_eq_preset(preset: int) -> bytes:
    return encode(Cmd.SET_EQ, _EQ_PRESET_PAYLOADS[preset])


def set_eq_custom(bands: list[int]) -> bytes:
    data = bytearray([EQ_CUSTOM, 0x06, EQ_BAND_COUNT])
    for i, gain in enumerate(bands, start=1):
        data += bytes([i, gain & 0xFF])
    return encode(Cmd.SET_EQ, bytes(data))


def dj_tone(tone: int) -> bytes:
    return encode(Cmd.DJ_TONE, bytes([tone]))


def dj_voice(voice: int) -> bytes:
    return encode(Cmd.DJ_VOICE, bytes([voice]))


def dj_filter(effect: int, level: int) -> bytes:
    return encode(Cmd.DJ_FILTER, bytes([effect, level]))


# --- State -------------------------------------------------------------------


@dataclass
class PartyBoxState:
    """Everything known about the speaker."""

    power_on: bool | None = None
    battery: int | None = None
    plugged_in: bool | None = None
    serial: str | None = None
    firmware: str | None = None
    light_on: bool | None = None
    light_mode: int | None = None
    light_color: tuple[int, int, int] | None = None
    light_modes: list[int] = field(default_factory=list)
    light_zones: dict[LightZone, bool] = field(default_factory=dict)
    volume: int | None = None
    muted: bool | None = None
    player_state: int | None = None
    mic_volume: int | None = None
    mic_inputs: int | None = None
    bass_boost: int | None = None
    karaoke: dict[KaraokeParam, int] = field(default_factory=dict)
    eq_preset: int | None = None
    eq_bands: list[int] = field(default_factory=lambda: [0] * EQ_BAND_COUNT)
    feedback_tone: bool | None = None
    lock_panel: bool | None = None
    usb_mode: int | None = None
    auracast: bool | None = None
    raw: dict[str, str] = field(default_factory=dict)
    """Last payload of every frame type, hex, for diagnostics."""

    def apply(self, frame: Frame) -> bool:
        """Update from a frame the speaker sent; return whether it was used."""
        handler = _HANDLERS.get(frame.cmd)
        if handler is None:
            return False
        self.raw[f"{frame.cmd:02x}"] = frame.data.hex()
        handler(self, frame.data)
        return True

    def set_battery_byte(self, value: int) -> None:
        """Battery percentage in the low 7 bits, mains power in bit 7."""
        self.battery = value & 0x7F
        self.plugged_in = bool(value & 0x80)


def _signed(byte: int) -> int:
    return byte - 256 if byte > 127 else byte


def _dev_info(state: PartyBoxState, data: bytes) -> None:
    tlv = parse_tlv(data[1:])
    if (v := tlv.get(DEV_BATTERY)) and len(v) == 1:
        state.set_battery_byte(v[0])
    if v := tlv.get(DEV_SERIAL):
        state.serial = v.decode("ascii", "replace")
    if (v := tlv.get(DEV_FIRMWARE)) and len(v) == 3:
        state.firmware = ".".join(str(b) for b in v)
    if (v := tlv.get(DEV_LOCK_PANEL)) and len(v) == 1:
        state.lock_panel = bool(v[0])
    if (v := tlv.get(DEV_USB_MODE)) and len(v) == 1:
        state.usb_mode = v[0]
    if (v := tlv.get(DEV_AURACAST)) and len(v) == 1:
        state.auracast = bool(v[0])
    if (v := tlv.get(DEV_MIC_INPUTS)) and len(v) == 1:
        state.mic_inputs = v[0] & MicInputs.BOTH


def _light(state: PartyBoxState, data: bytes) -> None:
    tlv = parse_tlv(data[1:])
    if (v := tlv.get(LIGHT_MODE)) and len(v) == 1:
        state.light_mode = v[0]
    if (v := tlv.get(LIGHT_COLOR)) and len(v) == 3:
        state.light_color = (v[0], v[1], v[2])
    if v := tlv.get(LIGHT_MODES_AVAILABLE):
        state.light_modes = list(v)
    if (v := tlv.get(LIGHT_ON)) and len(v) == 1:
        state.light_on = bool(v[0])
    for zone in LightZone:
        if (v := tlv.get(zone)) and len(v) == 1:
            state.light_zones[zone] = bool(v[0])


def _player(state: PartyBoxState, data: bytes) -> None:
    tlv = parse_tlv(data[1:])
    if (v := tlv.get(PLAYER_VOLUME)) and len(v) == 1:
        state.volume = v[0]
    if (v := tlv.get(PLAYER_MUTE)) and len(v) == 1:
        state.muted = bool(v[0])
    if (v := tlv.get(PLAYER_STATE)) and len(v) == 1:
        state.player_state = v[0]


def _mic_info(state: PartyBoxState, data: bytes) -> None:
    tlv = parse_tlv(data[1:])
    if (v := tlv.get(MIC_VOLUME)) and len(v) == 1:
        state.mic_volume = v[0]


def _mic_inputs(state: PartyBoxState, data: bytes) -> None:
    if data:
        state.mic_inputs = data[0] & MicInputs.BOTH


def _bass_boost(state: PartyBoxState, data: bytes) -> None:
    if data:
        state.bass_boost = data[0]


def _karaoke(state: PartyBoxState, data: bytes) -> None:
    for param, level in zip(KaraokeParam, data, strict=False):
        state.karaoke[param] = level


def _karaoke_notify(state: PartyBoxState, data: bytes) -> None:
    if len(data) == 2 and data[0] in iter(KaraokeParam):
        state.karaoke[KaraokeParam(data[0])] = data[1]


def _eq(state: PartyBoxState, data: bytes) -> None:
    if not data:
        return
    state.eq_preset = data[0]
    # data[1:4] = C1 06 05, then (band, gain) pairs.
    pairs = data[4:]
    for i in range(0, len(pairs) - 1, 2):
        band, gain = pairs[i], pairs[i + 1]
        if 1 <= band <= EQ_BAND_COUNT:
            state.eq_bands[band - 1] = _signed(gain)


def _feedback_tone(state: PartyBoxState, data: bytes) -> None:
    if data:
        state.feedback_tone = bool(data[0])


_HANDLERS = {
    Cmd.RET_DEV_INFO: _dev_info,
    Cmd.RET_LIGHT: _light,
    Cmd.RET_PLAYER: _player,
    Cmd.RET_MIC_INFO: _mic_info,
    Cmd.RET_BASS_BOOST: _bass_boost,
    Cmd.RET_MIC_INPUTS: _mic_inputs,
    Cmd.RET_KARAOKE: _karaoke,
    Cmd.NOTIFY_KARAOKE: _karaoke_notify,
    Cmd.RET_EQ: _eq,
    Cmd.RET_FEEDBACK_TONE: _feedback_tone,
}

REFRESH_QUERIES = (
    Cmd.REQ_DEV_INFO,
    Cmd.REQ_LIGHT,
    Cmd.REQ_PLAYER,
    Cmd.REQ_BASS_BOOST,
    Cmd.REQ_KARAOKE,
    Cmd.REQ_MIC_INFO,
    Cmd.REQ_MIC_INPUTS,
    Cmd.REQ_EQ,
    Cmd.REQ_FEEDBACK_TONE,
)
"""Requests that together read the full state."""


# --- Advertisements ----------------------------------------------------------


@dataclass(frozen=True)
class Advertisement:
    """What the speaker broadcasts in its 0xFDDF service data."""

    mac: str
    power_on: bool
    battery_byte: int


def parse_advertisement(data: bytes) -> Advertisement | None:
    """Parse ``dd 20 01 <state> <battery> .. .. .. .. .. .. <mac 6>``."""
    if len(data) < 17 or data[0] != 0xDD:
        return None
    mac = ":".join(f"{b:02X}" for b in data[11:17])
    # Seen: D0 (and D4 right after waking) when on, D3 in standby.
    return Advertisement(mac=mac, power_on=data[3] & 0x03 == 0, battery_byte=data[4])
