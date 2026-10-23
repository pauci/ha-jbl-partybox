"""Protocol tests, using frames captured from a PartyBox Stage 320."""

import protocol
from protocol import BassBoost, KaraokeParam, LightZone, PartyBoxState, PlayerState

DEV_INFO = bytes.fromhex(
    "aa123a00310220dd3201013301e43401013501003601003706aabbcc0011223801143901"
    "004103040000420100430101440201163c01003b0400000000"
)
DEV_INFO_2 = bytes.fromhex(
    "aa122d004010544c303030302d494f303030303030303a0653746572656f3d0101550100"
    "5a01015b01005c0101590100"
)
LIGHT = bytes.fromhex(
    "aa323300310109320300ff003301013601003801013901014001014101014201014301"
    "014401014801004a0702090a0b0c0d08990101"
)
PLAYER = bytes.fromhex("aa42140042010343010046010347010a41010244004500")
EQ = bytes.fromhex("aae2000ec1c1060501fa0200030004000500")
ADV = bytes.fromhex("dd2001d064000008040000aabbcc00112201010000000000")


def _state(*buffers: bytes) -> PartyBoxState:
    state = PartyBoxState()
    for buf in buffers:
        for frame in protocol.decode(buf):
            state.apply(frame)
    return state


def test_decode_splits_concatenated_frames() -> None:
    frames = protocol.decode(bytes.fromhex("aa00023300aa620101"))
    assert [(f.cmd, f.data.hex()) for f in frames] == [(0x00, "3300"), (0x62, "01")]
    assert frames[0].ack_for == 0x33
    assert frames[0].ack_ok


def test_rejected_ack() -> None:
    (frame,) = protocol.decode(bytes.fromhex("aa000243ff"))
    assert frame.ack_for == 0x43
    assert not frame.ack_ok


def test_device_info() -> None:
    state = _state(DEV_INFO, DEV_INFO_2)
    assert state.battery == 100
    assert state.plugged_in is True
    assert state.serial == "TL0000-IO0000000"
    assert state.firmware == "4.0.0"
    assert state.lock_panel is False
    assert state.usb_mode == protocol.UsbMode.EASYSING_MICS
    assert state.auracast is False
    # Auracast button pressed on the speaker.
    state.apply(protocol.decode(bytes.fromhex("aa1207003801163c0101"))[0])
    assert state.auracast is True


def test_light() -> None:
    state = _state(LIGHT)
    assert state.light_on is True
    assert state.light_mode == 0x09
    assert state.light_color == (0x00, 0xFF, 0x00)
    assert state.light_modes == [0x02, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x08]
    assert state.light_zones == {
        LightZone.RING: True,
        LightZone.DOTS: True,
        LightZone.STROBE: True,
        LightZone.STRIPS: True,
    }


def test_player_and_notifications() -> None:
    state = _state(PLAYER)
    assert (state.volume, state.muted, state.player_state) == (3, False, 2)
    # Volume knob and pause pushed by the speaker.
    state = _state(PLAYER, bytes.fromhex("aa420400420107aa42080041010144004500"))
    assert state.volume == 7
    assert state.player_state == PlayerState.PAUSED


def test_eq_custom_with_negative_band() -> None:
    state = _state(EQ)
    assert state.eq_preset == protocol.EQ_CUSTOM
    assert state.eq_bands == [-6, 0, 0, 0, 0]


def test_karaoke_and_mic_volume() -> None:
    state = _state(
        bytes.fromhex("aa7203060700"),
        bytes.fromhex("aa74020204"),
        bytes.fromhex("aad20a0005010108011f090101"),
        bytes.fromhex("aa620102"),
        bytes.fromhex("aaf20101"),
        bytes.fromhex("aac20102"),
    )
    assert state.karaoke == {
        KaraokeParam.BASS: 6,
        KaraokeParam.TREBLE: 4,
        KaraokeParam.ECHO: 0,
    }
    assert state.mic_volume == 31
    assert state.bass_boost == BassBoost.PUNCHY
    assert state.feedback_tone is True
    assert state.mic_inputs == protocol.MicInputs.INPUT_2


def test_truncated_tlv_is_ignored() -> None:
    state = _state(bytes.fromhex("aa320800310109320300ff"))
    assert state.light_mode == 0x09
    assert state.light_color is None


def test_unknown_frames_are_ignored() -> None:
    assert not PartyBoxState().apply(protocol.Frame(0xB2, b"\x00"))


def test_commands_match_the_app() -> None:
    assert protocol.power(True).hex() == "aa030105"
    assert protocol.power(False).hex() == "aa030104"
    assert protocol.query(protocol.Cmd.REQ_DEV_INFO).hex() == "aa1100"
    assert protocol.query(protocol.Cmd.REQ_EQ).hex() == "aae10000"
    assert protocol.set_light_mode(0x0A).hex() == "aa33040031010a"
    assert protocol.set_light_on(False).hex() == "aa330400990100"
    assert protocol.set_light_color((0x11, 0x3B, 0xFF)).hex() == (
        "aa3309003601013203113bff"
    )
    assert protocol.set_light_zone(LightZone.RING, False).hex() == "aa330400380100"
    assert protocol.set_volume(8).hex() == "aa430400420108"
    assert protocol.set_player_state(PlayerState.PAUSED).hex() == "aa430400410101"
    assert protocol.set_mic_volume(12).hex() == "aad3040008010c"
    assert protocol.set_bass_boost(BassBoost.DEEP).hex() == "aa630101"
    assert protocol.set_karaoke(KaraokeParam.TREBLE, 4).hex() == "aa73020204"
    assert protocol.set_feedback_tone(True).hex() == "aaf30101"
    assert protocol.set_lock_panel(True).hex() == "aa130400550101"
    assert protocol.set_usb_mode(protocol.UsbMode.USB_PLAYBACK).hex() == (
        "aa1304005c0100"
    )
    assert protocol.set_eq_custom([0, 3, -2, -3, 1]).hex() == (
        "aae3000dc106050100020303fe04fd0501"
    )
    assert protocol.set_eq_preset(0x06).hex().startswith("aae3004706050000bb80")
    assert protocol.dj_tone(protocol.DJ_TONES["horn"]).hex() == "aa550101"
    assert protocol.dj_voice(protocol.DJ_VOICES["lets_go"]).hex() == "aa560113"
    assert protocol.dj_filter(2, 3).hex() == "aa57020203"


def test_eq_preset_frames_have_the_captured_length() -> None:
    for preset in protocol.EQ_PRESETS:
        frame = protocol.set_eq_preset(preset)
        assert len(frame) == 4 + 0x47
        assert frame[4] == preset


def test_advertisement() -> None:
    adv = protocol.parse_advertisement(ADV)
    assert adv is not None
    assert adv.mac == "AA:BB:CC:00:11:22"
    assert adv.power_on is True
    state = PartyBoxState()
    state.set_battery_byte(adv.battery_byte)
    assert (state.battery, state.plugged_in) == (100, False)

    standby = protocol.parse_advertisement(ADV[:3] + b"\xd3" + ADV[4:])
    assert standby is not None
    assert standby.power_on is False
    assert protocol.parse_advertisement(b"\x01\x02") is None
