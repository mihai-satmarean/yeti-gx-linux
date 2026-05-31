#!/usr/bin/env python3
"""
Passive listener — prints every packet the Yeti GX sends unprompted.
Run this, then press the mute button and toggle smartlock, and watch what arrives.
"""
import sys, time, os, glob

VENDOR_ID = "046D"
PRODUCT_ID = "0AFC"

def find_hidraw():
    for uevent_path in glob.glob("/sys/bus/hid/devices/*/uevent"):
        with open(uevent_path) as f:
            content = f.read()
        if f"HID_ID=0003:0000{VENDOR_ID}:0000{PRODUCT_ID}" in content:
            dev_dir = os.path.dirname(uevent_path)
            nodes = glob.glob(os.path.join(dev_dir, "hidraw/hidraw*"))
            if nodes:
                return "/dev/" + os.path.basename(nodes[0])
    return None

HIDRAW = find_hidraw()
if HIDRAW is None:
    print("Yeti GX not found.", file=sys.stderr)
    sys.exit(1)

print(f"Listening on {HIDRAW} — press mute button, toggle smartlock. Ctrl+C to stop.\n")

with open(HIDRAW, "rb", buffering=0) as f:
    os.set_blocking(f.fileno(), False)
    while True:
        try:
            r = f.read(64)
            if r:
                trimmed = r.rstrip(b'\x00')
                print(f"  recv:  {trimmed.hex(' ')}")
                print(f"  bytes: {list(trimmed)}\n")
        except BlockingIOError:
            time.sleep(0.01)
        except KeyboardInterrupt:
            break
