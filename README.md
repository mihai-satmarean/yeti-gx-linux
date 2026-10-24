# Logitech Yeti GX — Linux Control

Full hardware control for the Logitech Yeti GX microphone on Linux, without G Hub.

The protocol below was reverse-engineered from G Hub USB captures and then
verified against the device itself over HID++ 2.0. Everything documented here
was observed on a real Yeti GX (USB `046d:0afc`, firmware 2.00).

---

## Requirements

- Python 3
- udev rule to allow access without sudo (see below)

---

## Setup

Copy the udev rule so any user can access the device. The rule grants access to
the HID++ hidraw node:

```
SUBSYSTEM=="hidraw", KERNEL=="hidraw*", ATTRS{idVendor}=="046d", ATTRS{idProduct}=="0afc", TAG+="uaccess"
```

Install it:

```
sudo cp udev/99-yeti-gx.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Replug the microphone. After that, no `sudo` is needed.

---

## Usage

```
yeti-ctl.py get
yeti-ctl.py set <0-100>
yeti-ctl.py mute | unmute
yeti-ctl.py smartlock on|off
yeti-ctl.py status
yeti-ctl.py listen
```

### Examples

```
yeti-ctl.py set 75        # set hardware gain to 75%
yeti-ctl.py get           # read current gain
yeti-ctl.py mute          # mute mic, LED turns red
yeti-ctl.py unmute        # unmute mic, LED turns white
yeti-ctl.py smartlock on  # enable Smart Audio Lock
yeti-ctl.py status        # gain, mute and Smart Audio Lock in one call
yeti-ctl.py listen        # follow the physical mute button
```

`status` reads all three values back from the device, so it doubles as a way to
confirm that a previous command actually took effect.

---

## Features

### Hardware Gain (`set` / `get`)

Controls the actual hardware preamp gain (0–100). This is the same slider as in
G Hub. ALSA only exposes a software gain (0–12) which is separate and less
useful.

### Mute / Unmute

Mutes or unmutes the microphone in hardware. The LED reflects the state:

- White = active
- Red = muted

This is equivalent to pressing the physical mute button on the device.

### Smart Audio Lock

A Logitech feature that automatically limits the gain when loud sounds are
detected, preventing clipping. Toggle it on or off from the command line.

### Listen

The physical mute button sends a state notification rather than press/release
events: one packet per press, carrying the state that resulted from it. It is
read-only — the device fires the same notification when the button or G Hub
changes the state.

Software writes are silent. Muting via `yeti-ctl.py mute` (or any other HID++
write) produces **no** notification, so an application that changes state
itself must re-read it — `yeti-ctl.py status` does exactly that.

`listen` checks every event against a fresh state read and prints both, which
makes it easy to confirm the device and the host agree:

```
10:54:03.209  event=muted    readback=muted    consistent
10:54:08.009  event=unmuted  readback=unmuted  consistent
```

Because each event triggers a read, an extremely fast double press can be
coalesced; human-speed presses are always reported individually.

---

## Protocol

The Yeti GX uses **Logitech HID++ 2.0** over USB HID.

- USB IDs: `046d:0afc`, USB 2.0 Full Speed (12 Mbps)
- Three interfaces: audio control (0), audio streaming (1), HID++ (2)
- HID++ is a vendor-defined HID interface, report descriptor usage page `0xFF43`
- Two report IDs:
  - `0x10` — short, 7 bytes (1 ID + 6 payload)
  - `0x11` — long, 20 bytes (1 ID + 19 payload)
- The hidraw node number varies; the script finds it by USB ID. Example:
  `/dev/hidraw11`.

### Report layout

```
Byte 0    Report ID     0x10 short, 0x11 long
Byte 1    Device index  0xFF
Byte 2    Feature index runtime index, discovered at startup (13 here)
Byte 3    Func + SW_ID  (func << 4) | software id
Byte 4+   Parameters
```

The software id is chosen by the client. G Hub uses 14; this tool uses 12. The
device echoes whatever value it receives and never validates it.

### Feature discovery

Feature indices are assigned at runtime, so they must not be hardcoded. The
feature set lives at index 1 and enumerates every available feature:

```
getCount    10 ff 01 0c 00 00 00        -> 0d (13 features)
getFeature  10 ff 01 1c <index> 00 00   -> <id hi> <id lo> ...
```

On a Yeti GX the enumeration is:

| Index | Feature ID | Meaning |
|-------|-----------|---------|
| 1 | `0x0001` | Feature set |
| 2 | `0x0003` | Device firmware version |
| 3 | `0x0005` | Device name |
| 4 | `0x0011` | — |
| 5 | `0x00C2` | — |
| 6 | `0x1602` | — |
| 7 | `0x180A` | — |
| 8 | `0x1E81` | — |
| 9 | `0x4610` | — |
| 10 | `0x8040` | — |
| 11 | `0x8071` | — |
| 12 | `0x8081` | — |
| 13 | `0x8370` | Microphone settings |

All microphone controls live on **feature `0x8370`**, functions 2 (read) and
3 (write).

### Fields

| Field | Direction | Values |
|-------|-----------|--------|
| `0x00` | read/write | `0` muted, `1` unmuted |
| `0x01` | read/write | gain, `0`–`100` |
| `0x02` | read only | Smart Audio Lock, `0` off, `1` on |
| `0x05` | write only | Smart Audio Lock, `0x06` off, `0x07` on |
| `0x03`, `0x04` | — | unsupported, returns an error |

### Raw commands

Read a field (`<feat>` is the discovered index, 13 on current firmware):

| Action | Packet |
|--------|--------|
| Get gain | `10 ff 0d 2c 00 01 00` |
| Get mute | `10 ff 0d 2c 00 00 00` |
| Get Smart Lock | `10 ff 0d 2c 00 02 00` |

Write a field:

| Action | Packet |
|--------|--------|
| Set gain to N | `10 ff 0d 3c 00 01 <N>` |
| Mute | `10 ff 0d 3c 00 00 00` |
| Unmute | `10 ff 0d 3c 00 00 01` |
| Smart Lock on | `10 ff 0d 3c 00 05 07` |
| Smart Lock off | `10 ff 0d 3c 00 05 06` |

The device answers a read with the field, its type and its value:

```
11 ff 0d 2c 00 01 01 47 00 ...     field 0x01, type 0x01 (range), value 0x47 = 71
11 ff 0d 2c 00 00 00 01 00 ...     field 0x00, type 0x00 (bool),  value 0x01 = unmuted
11 ff 0d 2c 00 02 05 01 00 ...     field 0x02, type 0x05 (enum),  value 0x01 = on
```

A write is echoed back as a long report carrying the new state:

```
11 ff 0d 3c 00 05 07 00 <token> 00 00 02 00 ...
```

That trailing `<token>` is a per-session value G Hub generates and stores. It is
**not validated**: the same state change works with a stale token, with a
different token, or with no long report at all. A plain 7-byte short write is
enough, which is what this tool sends.

### Error responses

Unsupported operations return an error report. Note that byte 2 becomes `0xff`
and the error code moves to byte 5:

```
10 ff ff <feat> <func> <code> 00
```

| Code | Meaning |
|------|---------|
| `0x02` | invalid argument |
| `0x03` | out of range |
| `0x04` | invalid feature index |
| `0x05` | invalid function id |
| `0x07` | unsupported |

### Physical button events (device → host)

The mute button sends a state notification, not press/release events:

```
11 ff 0d 20 00 00 00 00 ...   muted
11 ff 0d 20 00 00 01 00 ...   unmuted
```

Byte 3 is `0x20`, i.e. function 2 with software id 0, and the state sits in
byte 6 — one byte earlier than in a read response.

---

## What is *not* available

### Blue VO!CE

Blue VO!CE has no feature of its own on this device. Toggling "Enable Blue
VO!CE" in G Hub was captured in full, and it sends only two existing field
writes:

- enable → gain `70`, then Smart Audio Lock on
- disable → Smart Audio Lock off, then gain `100`

The DSP itself (EQ, de-esser, presets, limiter) runs inside G Hub's host-side
audio driver and never crosses USB. It therefore cannot be controlled over
HID++ from Linux — no amount of protocol work will change that. The device-side
part can be reproduced:

```
yeti-ctl.py set 70 && yeti-ctl.py smartlock on     # what "enable" does
yeti-ctl.py smartlock off && yeti-ctl.py set 100   # what "disable" does
```

Note that G Hub re-applies the gain after every Smart Audio Lock write, so gain
and lock are not independent in its UI.

---

## How this was verified

The captures were taken on the host with `usbmon` while the microphone was
attached to a Windows VM, which is a reliable way to observe what G Hub
actually sends:

```
sudo modprobe usbmon
sudo tshark -i usbmon5 -w capture.pcapng
# exercise G Hub, then trim to the HID++ endpoints (0x81 IN, 0x01 OUT)
tshark -r capture.pcapng -Y "usb.endpoint_address.number==1" -w hidpp.pcapng
tshark -r hidpp.pcapng -T fields -e frame.time_relative -e usb.src -e usb.dst -e usb.capdata
```

The audio streaming endpoint (`0x83`, isochronous) carries raw microphone
audio, so always trim captures before sharing them.

---

## Development

```
python3 -m py_compile yeti-ctl.py
python3 -m pytest tests/ -q
```

The packet builders and parsers are pure functions so they can be tested
without the microphone attached. Every expected byte string in the tests comes
from a real capture or a live exchange.

---

## Troubleshooting

- **Device not found** — the script matches USB ID `046d:0afc`; check
  `lsusb -d 046d:0afc`. If the microphone is passed through to a virtual
  machine, it is detached from the host and no hidraw node exists.
- **Permission denied** — install the udev rule above and replug.
- **`get` works but `set` appears to do nothing** — check `yeti-ctl.py status`;
  a rejected write now reports an error instead of silently succeeding.
