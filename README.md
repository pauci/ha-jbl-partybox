# JBL PartyBox for Home Assistant

A Home Assistant custom integration for **JBL PartyBox** speakers. It talks to
the speaker over **Bluetooth Low Energy**, like the JBL PartyBox app does, so it
can switch the speaker on from standby, run the light show, change the
equalizer and play the Effect Lab sounds, all without a phone.

> Not affiliated with or endorsed by JBL or Harman. The protocol was
> reverse-engineered, see [docs/PROTOCOL.md](docs/PROTOCOL.md). A firmware update
> could break it.

Tested with the **PartyBox Stage 320** (sold as PartyBox 320). Other models from
the same generation (Club 120, 520, 720, Encore 2, Encore Essential 2,
On-The-Go 2) very likely use the same protocol, but their EQ presets differ and
are not included yet. Reports are welcome.

## Requirements

- Home Assistant's Bluetooth integration with an adapter or an **active**
  [ESPHome Bluetooth proxy](https://esphome.io/components/bluetooth_proxy/) in
  range of the speaker. Passive proxies (Shelly) are enough for power state and
  battery, but not for control.
- The speaker answers **one client at a time**. While the JBL PartyBox app is
  connected (it reconnects in the background while open), Home Assistant's
  commands are ignored. By default the integration disconnects 30 seconds after
  the last command so the app can connect again.

## Options

- **Stay connected**: keep the link open while the speaker is on. Commands react
  instantly, and changes made on the speaker (knobs, light button, plugging in a
  mic) show up live. The JBL PartyBox app can't connect meanwhile. Without it,
  the first command after a pause takes a few seconds to connect, and speaker-side
  changes show up at the next refresh (every 5 minutes).

## Features

| Entity | Description |
|---|---|
| Media player | On/standby, volume (0–32), mute, play/pause, next/previous track |
| Battery | Battery level. From the speaker's broadcast, so it works in standby |
| Mains power | On while the speaker runs on mains power (and charges) |
| Auracast | On while the speaker broadcasts over Auracast (its Auracast button). Read-only |
| Light show | On/off, pattern (Neon, Loop, Bounce, Trim, Switch, Freeze, Custom) and colour. The speaker has no brightness setting; brightness scales the colour |
| Speaker ring light, Dot lights, Strobe, White light strips | Switch the individual light groups |
| Equalizer | JBL Signature, Movie, Vocal, Chill or Custom |
| Custom EQ band 1–5 | −6…+6, switches the equalizer to Custom. Disabled by default |
| Bass boost | Off, Deep or Punchy |
| Mic input 1, Mic input 2 | On while a mic is plugged in. Input 2 (mic/guitar) only counts with its switch in mic mode |
| Mic volume | 0–32, follows the knob on the speaker. Works with JBL wireless mics; the app has no such control. Unavailable while no mic is plugged in |
| Mic bass, Mic treble, Mic echo | 0–12, follow the knobs on the speaker. Unavailable while no mic is plugged in |
| Horn, Pac-Man, Thumbs up/down, Scratch 1–3, Clap, "Let's go", "Hands up", "Hey", "Party!", "Jump" | Effect Lab sound buttons |
| Feedback tone, Panel lock | Configuration switches |
| USB-A port | *JBL EasySing mics* or *USB playback and charging* |

Controls are unavailable while the speaker is in standby, because it ignores
everything except power-on then. Changes made on the speaker or in the app
(knobs, light button, power) show up when the speaker reports them or at the
next refresh (every 5 minutes while on).

### Action: `jbl_partybox.dj_effect`

Applies one of the Effect Lab sliders for a while, as if you held it in the app.

```yaml
action: jbl_partybox.dj_effect
data:
  config_entry_id: <your entry>
  effect: gater # repeater, filter, gater, echo, wipeout
  level: 3 # 1–4
  duration: 2 # seconds
```

## Installation

1. HACS → *Integrations* → menu → *Custom repositories*, add
   `https://github.com/pauci/ha-jbl-partybox` as an *Integration*.
2. Install *JBL PartyBox* and restart Home Assistant.
3. The speaker is discovered automatically. Otherwise use *Settings → Devices &
   services → Add integration → JBL PartyBox*.

## Not supported

- Song titles: the speaker reports none for Bluetooth playback.
- Key shifter and AI vocal removal: the code exists in the app, but the Stage 320
  doesn't support them (the speaker's own feature list says so).
- Stereo pairing, switching Auracast and the custom light pattern editor.
- The effect pad buttons on the speaker: the speaker doesn't report presses, so they
  can't trigger automations.
