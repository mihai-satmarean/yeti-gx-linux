# Project: Logitech Yeti GX Linux UI

## What this is

A Python library and UI for controlling the Logitech Yeti GX microphone on Linux
without G Hub. The original `yeti-ctl.py` CLI was reverse-engineered from G Hub USB
captures. This fork adds a proper Python library (`ui/yeti_gx.py`) and is building a
GUI on top of it.

## Current state

- `yeti-ctl.py` — original CLI, works, controls gain/mute/smartlock from command line
- `ui/yeti_gx.py` — library class `YetiGX`, ready to use, not yet wired to a UI
- UI framework not yet chosen — PyQt6, tkinter, and others are all candidates
- `probe.py` and `listen.py` are discovery/research scripts, not part of the final product

## Key protocol findings (discovered this session, not in original reverse engineering)

### Get mute state
`10 ff 0d 2c 00 00 00` → byte 7 of response: `0x00` = muted, `0x01` = unmuted.
Confirmed by toggling mute and comparing responses.

### Get smartlock state
`10 ff 0d 2c 00 02 00` → byte 7 of response: `0x00` = off, `0x01` = on.
Discovered from a G Hub USB capture on Windows — G Hub queries params 0x00, 0x01, 0x02
in sequence at startup to read mute, gain, and smartlock respectively.

### Device-initiated notifications
All three physical controls send unsolicited `11 ff 0d 20 00 <type> <value>` packets:
- `type=0x00`: mute toggle (`0x00`=muted, `0x01`=unmuted)
- `type=0x01`: gain dial turned (value = new gain 0–100)
- `type=0x05`: smartlock toggle (`0x00`=off, `0x01`=on)

These fire for both physical control changes AND software-initiated changes, so they
are the right way to keep a UI in sync without polling.

## Library API (`ui/yeti_gx.py`)

```python
from yeti_gx import YetiGX, YetiGXError

with YetiGX() as mic:
    gain = mic.get_gain()          # int 0–100
    mic.set_gain(75)
    muted = mic.get_mute()         # bool
    mic.set_mute(True)
    mic.set_smartlock(True)
    enabled = mic.get_smartlock()  # bool

    mic.listen(
        on_mute=lambda muted: ...,      # bool
        on_gain=lambda gain: ...,       # int
        on_smartlock=lambda enabled: .. # bool
    )
```

`YetiGX` is a context manager. `listen()` starts a background daemon thread.
`close()` / `__exit__` stops the thread and closes the hidraw fd.

## Device info

- USB IDs: `046d:0afc`
- Protocol: HID++ 2.0, feature `0x8370` at index 13, SW_ID 12
- hidraw discovery: scans `/sys/bus/hid/devices/*/uevent` for matching HID_ID
- Requires udev rule for non-root access (see README)

## What's next

- Choose a UI framework and build the GUI in `ui/`
- The UI needs: gain slider, mute toggle, smartlock toggle
- Physical controls should update the UI in real time via `listen()`
- Smart lock initial state can be read via `get_smartlock()` on startup
