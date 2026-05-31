# Windows USB Capture with G Hub

Use this to discover HID++ commands that G Hub sends to the Yeti GX — specifically
any get commands for Smart Lock state that we haven't been able to find on Linux.

---

## Requirements

- Logitech G Hub installed and working with the Yeti GX
- [Wireshark](https://www.wireshark.org/download.html) — install with the USBPcap
  component checked (it's in the installer, off by default)

---

## Procedure

1. Open Wireshark. In the capture interface list you should see one or more
   **USBPcap** interfaces. Pick the one that lists the Yeti GX, or just try
   USBPcap1 first.

2. Start the capture.

3. **Close G Hub completely** (right-click tray icon → Quit), then reopen it and
   navigate to the Yeti GX mic page. The re-initialization sequence is when G Hub
   reads all current device states — this is the most likely moment to see a
   smartlock get query.

4. While G Hub is open, also try toggling Smart Lock on and off from the G Hub UI
   to capture the set commands for comparison.

5. Stop the capture and save as `yeti-ghub.pcapng`.

---

## Extracting the relevant packets

Copy `yeti-ghub.pcapng` to your Linux machine, then:

```bash
# Show all packets to/from the Yeti GX (vendor 046d, product 0afc)
tshark -r yeti-ghub.pcapng -x | grep -B1 -A4 "0d 2c\|0d 3c\|0d 1c\|0d 0c"
```

Or for a cleaner view of just the HID++ payloads:

```bash
tshark -r yeti-ghub.pcapng -T fields \
  -e frame.number \
  -e usb.endpoint_address \
  -e usb.capdata \
  | grep -v "^$"
```

If `usb.capdata` comes back empty, try `usbhid.data` instead:

```bash
tshark -r yeti-ghub.pcapng -T fields \
  -e frame.number \
  -e usb.endpoint_address \
  -e usbhid.data \
  | grep -v "^$"
```

---

## What to look for

All Yeti GX HID++ packets start with `10 ff 0d` (short) or `11 ff 0d` (long).

The byte at offset 3 encodes function and SW_ID: `(func << 4) | SW_ID`.
G Hub uses SW_ID 12 (0x0C), so:

| Byte 3 | Meaning |
|--------|---------|
| `0x0c` | func 0 — getCapabilities |
| `0x1c` | func 1 — getState |
| `0x2c` | func 2 — get (read a value) |
| `0x3c` | func 3 — set (write a value) |

Focus on packets where byte 3 is `0x1c` or `0x2c` (the get functions) — these are
G Hub querying the device. Byte 5 onwards are the parameters; compare them against
the known commands in the README to identify anything new.

---

## Known commands (for reference when reading the capture)

| Packet | Action |
|--------|--------|
| `10 ff 0d 2c 00 01 00` | Get gain → byte 7 of response |
| `10 ff 0d 2c 00 00 00` | Get mute → byte 7: `0x00`=muted, `0x01`=unmuted |
| `10 ff 0d 3c 00 01 <N>` | Set gain to N |
| `10 ff 0d 3c 00 00 00` | Mute |
| `10 ff 0d 3c 00 00 01` | Unmute |
| `11 ff 0d 3c 00 05 07 ...` | Smart Lock on |
| `11 ff 0d 3c 00 05 06 ...` | Smart Lock off |

Any `0x2c` or `0x1c` packet with parameters not in this table is a new discovery.
If G Hub reads Smart Lock state, it will appear as an outbound packet (host → device)
shortly after G Hub connects or opens the mic page.
