# ViewSonic Projector for Home Assistant

Full RS-232 control of a ViewSonic projector from Home Assistant, with real
state feedback rather than an optimistic guess.

Developed against a **PJD7820HD (VS14937)**. The protocol is shared across much
of the ViewSonic DLP range (and is close to BenQ's), so other models are likely
to work — check your model's RS232 command table before assuming.

## How it works

The projector speaks RS-232. An ESP8266 running ESPHome bridges that serial
line onto TCP, and this integration speaks the projector's protocol directly
from Python.

```
Projector DB9  <--RS-232-->  MAX3232  <--3.3V TTL-->  ESP8266  <--TCP-->  Home Assistant
```

Keeping the protocol in Python rather than in ESPHome lambdas means adding
commands is a one-row change to a table, with no reflashing.

## Entities

Every command in the projector's RS232 table is exposed. Controls you actually
reach for sit in the main device view; the rest are filed under **config**, and
readbacks under **diagnostic**, so thirty-odd settings don't bury the handful
that matter.

| Control | Type | Notes |
| --- | --- | --- |
| Power | `switch` | Holds its commanded state while the lamp strikes or cools |
| Source | `select` | VGA, VGA2, HDMI, Composite, S-Video |
| Aspect ratio | `select` | Auto, 4:3, 16:9, Wide |
| Color mode | `select` | Brightest, Movie, User 1/2, PC/Gaming, ViewMatch, Dynamic PC/Movie |
| Blank, Freeze, Mute | `switch` | |
| Volume | `button` ×2 | Up/down; current value as a sensor |
| Lamp mode | `select` | Normal / Economic |
| Lamp hours | `sensor` | As counted by the projector |
| Contrast, Brightness, Hue, Saturation, Gain | `button` ×2 each | Step controls, with value sensors |
| Keystone, H/V position | `button` ×2 each | |
| Color temperature, Primary color, Gamma | `select` | |
| BrilliantColor | `switch` | |
| HDMI format, HDMI range | `select` | |
| CEC, 3D sync invert | `switch` | |
| 3D sync | `select` | Off, Auto, Frame Sequential, Frame Packing, Top-Bottom, Side-by-Side |
| Projector position | `select` | Front/Rear × Table/Ceiling |
| Splash screen | `select` | Black, Blue, ViewSonic, Screen Capture, Off |
| High altitude, On-screen messages, Quick auto search, Quick power off | `switch` | |
| Remote control code | `select` | Code A / B |
| Auto adjust, Reset color settings | `button` | |
| Reset all settings, Reset lamp hours | `button` | **Destructive — see below** |
| Error status | `sensor` | Raw 29-byte block, undocumented layout |
| Responding | `binary_sensor` | Stays available when the projector doesn't |

### Two buttons to be careful with

**Reset all settings** factory-resets the projector. **Reset lamp hours** clears
the lamp-life counter and is only correct after physically replacing the lamp.
Both are included because the commands exist, and both are one press with no
confirmation — consider hiding them or putting them behind a
[confirmation dialog](https://www.home-assistant.io/dashboards/actions/) if the
dashboard is reachable by anyone else.

### Write-only controls

**A refused read does not mean a refused write.** Verified on a PJD7820HD over
an idle serial line: it NAKs "is it frozen?" while happily accepting "freeze
on" — the image froze for twelve seconds and resumed on command.

So a control the projector will not report is still offered, as an optimistic
entity with `assumed_state` set. Home Assistant then shows separate on/off
buttons instead of a toggle claiming a state it cannot verify. The value shown
is what was last commanded, not what was observed.

Read-only sensors get the opposite treatment: if the projector will not report
a value, the sensor goes *unavailable* rather than sitting at a permanent
`unknown`, which just looks broken.

On this model these read back normally:

> power, lamp hours, error status, keystone, blank, projector position, splash
> screen, high altitude, lamp mode, on-screen messages, quick auto search, CEC,
> quick power off, mute, volume, remote control code

and these are write-only — they work, but report nothing:

> source, aspect ratio, color mode, color temperature, gamma, HDMI format,
> HDMI range, primary color, 3D sync, 3D sync invert, BrilliantColor, freeze,
> contrast, brightness, hue, saturation, gain, horizontal/vertical position

Other models will differ, which is why none of this is hard-coded — it is
discovered at runtime and re-tested whenever the projector's power state
changes.

### A timing note

This projector needs roughly a second between commands. Polling it every 220ms
produced dropped replies that looked like unsupported commands; at 900ms it was
perfectly reliable across every attempt. The integration's own pacing is well
inside that.

### What isn't exposed

**Language** (`0x15 0x00`). The manual lists 21 opcodes for it without saying
which language each one selects, so the entity would be twenty-one unlabelled
choices. Add it to `CONTROLS` in `const.py` if you map them.

## Responsiveness

- Power is read every cycle (3s by default, tunable under the integration's
  **Configure** button, 2–60s).
- Everything else rotates through a queue, four reads per cycle, so no single
  cycle stalls on thirty serialised round trips. A full refresh takes ~10 cycles.
- Writes publish their expected result immediately and then confirm by reading
  the projector back, so the UI moves at once but self-corrects if the projector
  disagrees.
- Power changes hold their commanded state for a grace period, because the
  projector keeps reporting the old state while the lamp strikes. Without that,
  the switch visibly flaps back before settling.

## Hardware

### Bill of materials

| Part | Notes |
| --- | --- |
| ESP8266 board | Developed on a **NodeMCU v2 (ESP-12E, 4 MB flash)**. Any ESP8266 exposing GPIO1/GPIO3 works. An ESP32 works too — see [Using an ESP32](#using-an-esp32). |
| **MAX3232 TTL ↔ RS-232 level shifter** | Sold as "MAX3232 RS232 to TTL converter". Must be a **3.3 V capable** module — many are 3.0–5.5 V, which is fine. Modules with a DB9 connector on board are the least fiddly. |
| DB9 cable | To reach from the module to the projector, if the module's connector doesn't mate directly. See the pinout warning below before buying a null-modem cable. |
| 5 V USB supply | The ESP needs its own power; it is not powered by the projector. |
| Jumper wires | 4 for the TTL side. |

### The level shifter is not optional

RS-232 signals swing **±3 V to ±15 V** (commonly ±12 V). ESP8266 GPIO is 3.3 V
and not even 5 V tolerant. **Wiring the projector's DB9 directly to the ESP will
destroy the ESP**, possibly the projector's port too. The MAX3232 is the only
part that should ever touch the DB9.

This is a translator, not a protocol device — it does no buffering or logic, so
nothing in the software depends on which module you buy.

### Wiring — ESP8266 to the MAX3232 (TTL side)

| ESP8266 | MAX3232 module |
| --- | --- |
| 3V3 | VCC |
| GND | GND |
| GPIO1 (TX, marked D10 / TX on NodeMCU) | TTL **RXD** (module's input) |
| GPIO3 (RX, marked D9 / RX on NodeMCU) | TTL **TXD** (module's output) |

Note the cross: the ESP's transmit goes to the module's receive. Module silk
screens are inconsistent about whose perspective they label from — if you get no
reply, swap these two before suspecting anything else.

### Wiring — MAX3232 to the projector (RS-232 side)

The PJD7820HD's DB9 pin assignment, from the user guide (p. 65):

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | NC | 2 | RX |
| 3 | TX | 4 | NC |
| 5 | **GND** | 6 | NC |
| 7 | RTSZ | 8 | CTSZ |
| 9 | NC | | |

Only **2, 3 and 5** are needed. Flow control is `None` in the protocol, so RTS
and CTS (7/8) go unused.

The guide heads that table "*Pin assignment for this two end*" without saying
whose perspective pins 2 and 3 are named from, so **whether you need a
straight-through or a null-modem (crossover) cable is not determinable from the
documentation.** Don't agonise over it — wire it one way, and if the projector
never answers a power query, swap pins 2 and 3. Nothing is harmed by getting it
the wrong way round; you simply get silence.

### UART0 caveat

GPIO1/GPIO3 are the ESP8266's hardware UART0, which is shared with the boot ROM
and with ESPHome's serial logger. Two consequences:

- **`logger: baud_rate: 0` is mandatory**, and both configs in `esphome/` set it.
  Without it, ESPHome's log output is injected straight into the projector's
  control line. Logs still reach you over WiFi — you only lose USB serial logs.
- At every boot the ESP8266 ROM bootloader emits a burst of garbage at 74880
  baud on TX. This is unavoidable on UART0 and harmless: the projector ignores
  or NAKs it. The frame parser resynchronises past it by design.

**When flashing over USB**, unplug the TTL RX line (GPIO3) from the module — the
projector shares that line and can contend with the flash traffic.

### Placement and power

The projector's RS-232 port stays powered in standby, which is what makes remote
power-on possible at all. The ESP needs its own permanent 5 V supply; if it is
unpowered, nothing works, including power-on.

### Using an ESP32

Swap the `esp8266:` block in the ESPHome config for `esp32:`, and set `tx_pin` /
`rx_pin` to any free UART pins (e.g. GPIO17/GPIO16). Everything else — the
integration, the card, the protocol — is unchanged. On an ESP32 you also get a
spare UART, so you can keep serial logging while driving the projector.

## Setting up the bridge

Flash the ESP with `esphome/projector-bridge.yaml`. It is a transparent bridge
and nothing more. `logger: baud_rate: 0` is required — UART0 belongs to the
projector, and log output would otherwise be injected into the control line.

The bridge vendors a **patched copy** of `oxan/esphome-stream-server` under
`esphome/components/`. Upstream calls `esphome::network::get_use_address()`,
which no longer exists as of ESPHome 2026.8, so it fails to compile. The patch
drops that from a diagnostic log line. See the comment in `stream_server.cpp`.

## Installing the integration

**HACS:** add this repository as a custom repository of type *Integration*,
install, restart Home Assistant.

**Manual:** copy `custom_components/viewsonic_projector/` into your HA
`config/custom_components/` directory and restart.

Then *Settings → Devices & Services → Add Integration → ViewSonic Projector*,
and enter the bridge's IP and port. Setup fails fast if the projector doesn't
answer a power query, so a successful add means the whole path works.

## Protocol notes

Three things about this protocol are worth knowing before changing anything.

**Byte 0 is a message type, not a length.** `0x05` reply, `0x06` write, `0x07`
read. The length lives in **byte 3**, and the total frame is that plus six. The
user guide only ever shows single-byte replies, where the two rules happen to
agree — so a byte-0 length rule looks correct and then silently discards every
wider reply. This is what a real lamp-hours reply looks like:

```
05 14 00 06 00 00 00 B9 0C 00 00 DF     12 bytes; byte[0]+4 would say 9
```

**Values are little-endian**, after three bytes of padding: `B9 0C 00 00` is
3257, not 47372.

**Power is encoded unlike everything else.** Most settings put their value in
the third byte. Power on and off instead differ in the *command* byte, both
carrying value `0x00`:

```
on   06 14 00 04 00 34 11 00 00 5D
off  06 14 00 04 00 34 11 01 00 5E
```

Writing power as a value toggle produces `11 00 01` — a different command that
happens to share the same checksum, so it validates cleanly and does the wrong
thing. Volume has the same shape: up and down are commands `0x01` and `0x02`,
and the readback lives at `0x03`.

**Replies carry no query ID.** A power reply and a lamp-hours reply differ only
in length. Every exchange is serialised behind a lock with the receive buffer
cleared immediately before each request, so a late reply from a timed-out query
is discarded rather than read as the next answer.

## Tests

```bash
python -m pytest tests/ -v
```

Command frames in `tests/test_protocol.py` come from the published table; reply
frames were captured off a real projector. If either stops matching, the code is
wrong.

## Standby behaviour

Most of the command set is only available while the lamp is on. In standby the
projector answers power, lamp hours and a handful of others, and **refuses** the
rest with a NAK frame:

```
00 14 00 00 00 14
```

That is a well-formed, checksum-valid frame with type `00` and no payload — the
same length and checksum rules as any reply. Recognising it matters twice over:
it arrives instantly, so a refused command costs nothing instead of a full reply
timeout, and it is unambiguous, so refused controls can drop out of the polling
rotation until something changes.

A refusal is **not** treated as "this model lacks the command". Availability
follows power state, so anything inferred permanently from a NAK would be wrong
for any projector that happened to be in standby at the time — including, for
instance, whenever Home Assistant restarts overnight. Refused controls keep
their entities and their last known value, and return to the rotation on any
power-state change (or after five minutes, since the projector can be switched
on at its own panel).

Silence is handled separately and more cautiously: a read that times out keeps
its previous value and stays in the rotation. A dropped TCP connection is still
treated as a real failure.
