# JBL PartyBox BLE protocol

Worked out on a PartyBox Stage 320 (product ID `20DD`, firmware 4.0.0) from
Android HCI snoop logs of the JBL PartyBox app 3.14.20, live tests, and the
decompiled app (its `com.harman.sdk.utils.PacketFormat` names most codes).

## Discovery

The speaker advertises with a rotating random address, so it can't be tracked
by address. Its service data for UUID `0xFDDF` identifies it:

```
dd 20 01 <state> <battery> 00 00 08 04 00 00 <classic BT MAC, 6 bytes> 01 01 00 ...
```

- `state`: `D0` on (also `D4` right after waking), `D3` standby.
- `battery`: bit 7 set on mains power, low 7 bits = percent (`E4` = 100 % plugged
  in, `64` = 100 % on battery).
- The classic Bluetooth MAC is stable and serves as the unique ID.

These advertisements also reach Home Assistant through passive proxies.

## GATT

Service `65786365-6c70-6f69-6e74-2e636f6d0000` (ASCII "excelpoint.com"):

| Characteristic | Use |
|---|---|
| `…0002` | Write commands (with response) |
| `…0001` | Notifications: replies and state changes |

No pairing or encryption. The speaker serves one client at a time and ignores a
second one completely, commands included. It also ignores the first commands
for about two seconds after a connection, and everything except power-on while
in standby.

## Frames

```
AA <cmd> <len> <data...>
```

`E1`, `E2` and `E3` use a two-byte big-endian length. Requests are usually
`<page>1` with no data, replies `<page>2`, settings `<page>3`. Settings on TLV
pages take `00` (device index) followed by `tag, length, value`. The speaker
acknowledges a command with `AA 00 02 <cmd> <status>`, status `00` = OK,
`FF` = rejected (e.g. value out of range).

| Cmd | Meaning |
|---|---|
| `03 01 05` / `03 01 04` | Power on (works from standby, no ACK) / off |
| `11` → `12` | Device info TLVs: `31` product ID, `33` battery (same encoding as advertising), `37` MAC, `40` serial, `41` firmware, `55` panel lock, `38` role (`14` normal, `16` Auracast broadcaster), `3C` Auracast on, `5C` USB-A mode (`01` EasySing mics, `00` USB playback), `59` key shifter, `5A`/`5B` vocal removal |
| `13` | Set device info TLVs (`55`, `5C`, …) |
| `31` → `32`, `33` | Light TLVs: `31` pattern, `32` RGB, `36` custom colour on, `4A` available patterns, `99` lights on; zones `38` ring, `39` dots, `33` strobe, `44` white strips. Patterns: `01` Rock, `02` Neon, `03` Club, `04` Flow, `05` Ripple, `06` Cross, `07` Flash, `08` Custom, `09` Loop, `0A` Bounce, `0B` Trim, `0C` Switch, `0D` Freeze |
| `41` → `42`, `43` | Player TLVs: `41` state (`01` paused, `02` playing; set `03` previous, `04` next), `42` volume 0–32, `43` mute, `44`/`45` song/artist, `46`/`47` primary/secondary volume |
| `55 01 <id>` | Sound pad: `01` horn, `02` clap, `03`–`05` scratch, `07` thumbs up, `08` thumbs down, `0D` Pac-Man |
| `56 01 <id>` | Voice pad: `0E` "Party!", `0F` "Hey", `10` "Hands up", `12` "Jump", `13` "Let's go" |
| `57 02 <fx> <0-4>` | Hold-slider effect: `01` repeater, `02` filter, `03` gater, `04` echo, `05` wipeout; `0` = released |
| `61` → `62`, `63` | Bass boost: `00` off, `01` Deep, `02` Punchy |
| `71` → `72`, `73` | Mic effects: `72 <bass> <treble> <echo>`, set `73 <param 1-3> <0-12>`; `74 <param> <value>` when a knob turns |
| `C1` → `C2` | Mic inputs in use, bitmask: `01` input 1, `02` input 2 (mic/guitar); pushed when a mic is plugged in or out |
| `A1` → `A2` | Feature flags (`A5` feedback tone, `AE` panel lock, `AF` key shifter, `B5` AI vocal removal, `B6` EasySing, `B9` USB mode, …) |
| `D1` → `D2`, `D3` | EasySing mic info TLVs; `08` mic volume 0–32 arrives only in notifications, set `D3 04 00 08 01 <v>` |
| `E1` → `E2`, `E3` | EQ: `E2 <active preset> C1 06 05 (<band> <gain>)×5`; presets `06` JBL Signature, `0A` Movie, `03` Vocal, `0B` Chill, `C1` custom. Presets are set with their biquad definition (floats), custom with `C1 06 05` + 5 × (band, gain −6…+6) |
| `EA` | Heartbeat the app sends every 5 s (no reply) |
| `F1` → `F2`, `F3` | Feedback tone |
