# Discovery Agents

These scripts were used to reverse-engineer the Yeti GX HID++ protocol beyond what
was captured from G Hub. They are research tools, not part of the final product.

---

## probe.py

Sends candidate HID++ queries to the device and prints the raw response bytes.
Used to discover get commands by sending func 2 variants and observing responses.

```
python3 probe.py
```

No arguments. Edit the `with` block at the bottom to add new probe packets.

**How to use it:** send a packet, look at the response bytes, compare across device
states (e.g. run once muted, run again unmuted — differing bytes reveal state fields).

**What it found:**
- `10 ff 0d 2c 00 00 00` returns mute state in byte 7 (`0x00`=muted, `0x01`=unmuted)
- Smartlock has no get command — func 2 with smartlock params returns a HID++ error
  packet (`10 ff ff 0d 2c 02 00`), where `0xff 0xff` at bytes 2–3 signals an error
  and `0x02` is the error code (unsupported)

---

## listen.py

Passively reads and prints every unsolicited packet the device sends.
Used to discover what the device broadcasts when physical controls are changed.

```
python3 listen.py
```

No arguments. Runs until Ctrl+C. While it's running, interact with the physical
controls (mute button, gain dial) and toggle smartlock via `yeti-ctl.py` in another
terminal to see what notifications the device emits.

**What it found:** all three physical controls send `11 ff 0d 20 00 <type> <value>`
notifications (see README Protocol section for the full table). Crucially, smartlock
notifications fire for software-initiated changes too, meaning a listener can track
smartlock state after the first toggle without any get command.

---

## Extending the probe

If you want to probe for new commands (e.g. after a G Hub USB capture on Windows
reveals packets we haven't tried), add entries to the `with` block in `probe.py`:

```python
probe(f, <func>, [0x00, <param1>, <param2>], "description")
```

`func` is the function number (0–15). The packet becomes `10 ff 0d (<func><<4)|0x0c ...`.
A response with `ff ff` at bytes 2–3 is a HID++ error — that function/param combo is
unsupported. A well-formed response will echo back bytes 0–4 and carry data in bytes 5+.
