#!/usr/bin/env python3
"""
Probe script to discover get commands for mute and smartlock state.
Sends func 2 variants and prints raw response bytes.
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

DEV_IDX  = 0xFF
FEAT_IDX = 13
SW_ID    = 12

def send_recv(f, data, timeout=0.5):
    f.write(bytes(data))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = f.read(64)
            if r:
                return r
        except BlockingIOError:
            time.sleep(0.01)
    return None

def probe(f, func, params, label):
    pkt = bytes([0x10, DEV_IDX, FEAT_IDX, (func << 4) | SW_ID] + params)
    print(f"\n[{label}]")
    print(f"  sent:  {pkt.hex(' ')}")
    r = send_recv(f, pkt)
    if r:
        print(f"  recv:  {r.hex(' ')}")
        print(f"  bytes: {list(r[:12])}")
    else:
        print("  no response")

with open(HIDRAW, "r+b", buffering=0) as f:
    os.set_blocking(f.fileno(), False)

    probe(f, 2, [0x00, 0x00, 0x00], "get mute    (known: byte 7 = 0x00 muted, 0x01 unmuted)")
    probe(f, 2, [0x00, 0x01, 0x00], "get gain    (known: byte 7 = gain 0-100)")
    probe(f, 2, [0x00, 0x02, 0x00], "get smartlock? (G Hub uses param=0x02, byte 7 = state)")
