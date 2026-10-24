#!/usr/bin/env python3
"""Logitech Yeti GX control over HID++ 2.0, without G Hub.

Verified against USB captures of G Hub plus live hardware probing.

All microphone controls live on feature 0x8370 ("audio settings").

Read (function 2):
    report      10 ff <feat> 2c 00 <field> 00
    response    11 ff <feat> 2c 00 <field> <type> <value> ...

Write (function 3):
    report      10 ff <feat> 3c 00 <field> <value>
    response    11 ff <feat> 3c 00 <field> <value> 00 <token> 00 00 02 ...

Fields:
    0x00  mute              0 = muted, 1 = unmuted
    0x01  gain              0-100
    0x02  Smart Audio Lock  0 = off, 1 = on  (read only)
    0x05  Smart Audio Lock  0x06 = off, 0x07 = on  (write)

The 20-byte long report G Hub uses for Smart Audio Lock is not required; a
plain 7-byte short write works. The trailing token in G Hub's long report is
a per-session value that the device stores and echoes but never validates.

Errors come back as 10 ff ff <feat> <func> <code> 00 - note the feature byte
is 0xff and the error code sits in byte 5.

Usage:
  yeti-ctl.py get
  yeti-ctl.py set <0-100>
  yeti-ctl.py mute | unmute
  yeti-ctl.py smartlock on|off
  yeti-ctl.py status
  yeti-ctl.py listen
"""
import glob
import os
import sys
import time

VENDOR_ID = "046D"
PRODUCT_ID = "0AFC"
HID_ID = f"0003:0000{VENDOR_ID}:0000{PRODUCT_ID}"

REPORT_SHORT = 0x10
REPORT_LONG = 0x11
DEV_IDX = 0xFF
SW_ID = 12

FEATURE_SET_IDX = 1
FEATURE_SET_ID = 0x0001
AUDIO_FEATURE_ID = 0x8370
AUDIO_FEATURE_FALLBACK = 13

FUNC_COUNT = 0
FUNC_FEATURE_ID = 1
FUNC_READ = 2
FUNC_WRITE = 3
FUNC_NOTIFY = 2

FIELD_MUTE = 0x00
FIELD_GAIN = 0x01
FIELD_LOCK_STATE = 0x02
FIELD_LOCK_WRITE = 0x05

LOCK_OFF = 0x06
LOCK_ON = 0x07

VENDOR_USAGE_PAGE = b"\x06\x43\xff"

ERROR_CODES = {
    0x01: "unknown",
    0x02: "invalid argument",
    0x03: "out of range",
    0x04: "invalid feature index",
    0x05: "invalid function id",
    0x06: "busy",
    0x07: "unsupported",
}


# --- packet building (pure, unit tested) -----------------------------------

def func_sw(func, sw_id=SW_ID):
    return (func << 4) | sw_id


def build_read(feature_idx, field, sw_id=SW_ID):
    return bytes([REPORT_SHORT, DEV_IDX, feature_idx, func_sw(FUNC_READ, sw_id),
                  0x00, field, 0x00])


def build_write(feature_idx, field, value, sw_id=SW_ID):
    return bytes([REPORT_SHORT, DEV_IDX, feature_idx, func_sw(FUNC_WRITE, sw_id),
                  0x00, field, value])


def build_feature_count(sw_id=SW_ID):
    return bytes([REPORT_SHORT, DEV_IDX, FEATURE_SET_IDX,
                  func_sw(FUNC_COUNT, sw_id), 0x00, 0x00, 0x00])


def build_feature_id(index, sw_id=SW_ID):
    return bytes([REPORT_SHORT, DEV_IDX, FEATURE_SET_IDX,
                  func_sw(FUNC_FEATURE_ID, sw_id), index, 0x00, 0x00])


# --- response parsing (pure, unit tested) ----------------------------------

def is_error(report):
    return len(report) >= 6 and report[2] == 0xFF


def error_code(report):
    return report[5] if is_error(report) else None


def describe_error(report):
    code = error_code(report)
    return ERROR_CODES.get(code, f"error 0x{code:02x}")


def matches(report, feature_idx, func, sw_id=SW_ID):
    if len(report) < 5 or is_error(report):
        return False
    if report[0] not in (REPORT_SHORT, REPORT_LONG):
        return False
    return (report[2] == feature_idx
            and (report[3] >> 4) == func
            and (report[3] & 0x0F) == sw_id)


def parse_read(report):
    """Return (field, value) from a function 2 response."""
    if len(report) < 8:
        return None
    return report[5], report[7]


def parse_write(report):
    """Return (field, value) from a function 3 echo."""
    if len(report) < 7:
        return None
    return report[5], report[6]


def parse_feature_id(report):
    if len(report) < 6:
        return None
    return (report[4] << 8) | report[5]


def parse_notification(report, feature_idx):
    """Return True when the device reports the microphone muted.

    Notifications use function 2 with software id 0 and carry the state in
    byte 6, unlike read responses which put the value in byte 7.
    """
    if len(report) < 7 or report[2] != feature_idx:
        return None
    if (report[3] >> 4) != FUNC_NOTIFY or (report[3] & 0x0F) != 0:
        return None
    if report[5] != FIELD_MUTE:
        return None
    return report[6] == 0x00


# --- device access ---------------------------------------------------------

def find_hidraw():
    """Locate the HID++ hidraw node, preferring the vendor usage page 0xFF43."""
    candidates = []
    for uevent_path in glob.glob("/sys/bus/hid/devices/*/uevent"):
        try:
            with open(uevent_path) as f:
                content = f.read()
        except OSError:
            continue
        if HID_ID not in content:
            continue
        dev_dir = os.path.dirname(uevent_path)
        for node in sorted(glob.glob(os.path.join(dev_dir, "hidraw/hidraw*"))):
            score = 0
            try:
                with open(os.path.join(dev_dir, "report_descriptor"), "rb") as f:
                    if VENDOR_USAGE_PAGE in f.read(64):
                        score = 1
            except OSError:
                pass
            candidates.append((score, "/dev/" + os.path.basename(node)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


class HidppDevice:
    def __init__(self, path):
        self.path = path
        try:
            self.handle = open(path, "r+b", buffering=0)
        except PermissionError:
            sys.exit(f"Permission denied on {path}.\n"
                     "Install udev/99-yeti-gx.rules (see README) and replug.")
        os.set_blocking(self.handle.fileno(), False)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.handle.close()

    def read_report(self, deadline):
        while time.time() < deadline:
            try:
                report = self.handle.read(64)
            except BlockingIOError:
                time.sleep(0.005)
                continue
            if report:
                return bytes(report)
        return None

    def drain(self):
        """Discard replies left over from earlier requests or button events."""
        while True:
            try:
                if not self.handle.read(64):
                    return
            except BlockingIOError:
                return

    def command(self, report, feature_idx, func, timeout=0.5, drain=True):
        """Send a report and return the matching reply, or None."""
        if drain:
            self.drain()
        self.handle.write(report)
        deadline = time.time() + timeout
        while True:
            reply = self.read_report(deadline)
            if reply is None:
                return None
            if is_error(reply):
                if reply[3] == feature_idx:
                    return reply
                continue
            if matches(reply, feature_idx, func):
                return reply

    def _gain_readable_at(self, feature_idx):
        """True when feature_idx answers a gain read with a plausible value."""
        reply = self.command(build_read(feature_idx, FIELD_GAIN),
                             feature_idx, FUNC_READ)
        if reply is None or is_error(reply):
            return False
        parsed = parse_read(reply)
        return parsed is not None and parsed[0] == FIELD_GAIN and 0 <= parsed[1] <= 100

    def resolve_feature(self):
        """Find the runtime index of feature 0x8370 via the feature set.

        Falls back to the index observed on current firmware (13), but only
        after confirming that index actually answers a gain read.
        """
        reply = self.command(build_feature_count(), FEATURE_SET_IDX, FUNC_COUNT)
        if reply and not is_error(reply) and len(reply) >= 5:
            for index in range(1, reply[4] + 1):
                for _ in range(2):
                    reply = self.command(build_feature_id(index),
                                         FEATURE_SET_IDX, FUNC_FEATURE_ID, 0.4)
                    if reply is None:
                        continue
                    if is_error(reply):
                        break
                    if parse_feature_id(reply) == AUDIO_FEATURE_ID:
                        return index
                    break
        if self._gain_readable_at(AUDIO_FEATURE_FALLBACK):
            return AUDIO_FEATURE_FALLBACK
        print("warning: feature discovery failed, assuming index "
              f"{AUDIO_FEATURE_FALLBACK}", file=sys.stderr)
        return AUDIO_FEATURE_FALLBACK

    def read_field(self, feature_idx, field, drain=True):
        reply = self.command(build_read(feature_idx, field), feature_idx, FUNC_READ,
                             drain=drain)
        if reply is None:
            sys.exit("No response from the Yeti GX.")
        if is_error(reply):
            sys.exit(f"Cannot read field {field}: {describe_error(reply)}")
        parsed = parse_read(reply)
        if parsed is None:
            sys.exit(f"Unexpected reply to read: {reply.hex(' ')}")
        return parsed[1]

    def write_field(self, feature_idx, field, value):
        reply = self.command(build_write(feature_idx, field, value),
                             feature_idx, FUNC_WRITE)
        if reply is None:
            sys.exit("No response from the Yeti GX.")
        if is_error(reply):
            sys.exit(f"Cannot write field {field}: {describe_error(reply)}")
        return parse_write(reply)


def open_device():
    path = find_hidraw()
    if path is None:
        sys.exit("Yeti GX not found. Is it plugged in?")
    return HidppDevice(path)


# --- commands --------------------------------------------------------------

def trim(lines):
    return "\n".join(lines)


def print_status(device, feature_idx):
    gain = device.read_field(feature_idx, FIELD_GAIN)
    muted = device.read_field(feature_idx, FIELD_MUTE) == 0
    locked = device.read_field(feature_idx, FIELD_LOCK_STATE) == 1
    print(f"Gain:        {gain} / 100")
    print(f"Mute:        {'muted' if muted else 'unmuted'}")
    print(f"Smart Lock:  {'on' if locked else 'off'}")


def listen(device, feature_idx):
    print("Listening for button events. Press Ctrl-C to stop.", flush=True)
    muted = device.read_field(feature_idx, FIELD_MUTE) == 0
    print(f"Current state: {'muted' if muted else 'unmuted'}", flush=True)
    print("Each event is checked against a fresh state read.", flush=True)
    try:
        while True:
            report = device.read_report(time.time() + 3600)
            if not report:
                continue
            state = parse_notification(report, feature_idx)
            if state is None:
                continue
            actual_muted = device.read_field(feature_idx, FIELD_MUTE,
                                             drain=False) == 0
            agree = actual_muted == state
            now = time.time()
            stamp = (time.strftime("%H:%M:%S", time.localtime(now))
                     + f".{int(now % 1 * 1000):03d}")
            print(f"{stamp}  raw={report.hex(' ')}"
                  f"  event={'muted' if state else 'unmuted'}"
                  f"  readback={'muted' if actual_muted else 'unmuted'}"
                  f"  {'consistent' if agree else 'MISMATCH'}", flush=True)
    except KeyboardInterrupt:
        print()


def usage():
    return trim([
        "Usage:",
        "  yeti-ctl.py get",
        "  yeti-ctl.py set <0-100>",
        "  yeti-ctl.py mute | unmute",
        "  yeti-ctl.py smartlock on|off",
        "  yeti-ctl.py status",
        "  yeti-ctl.py listen",
    ])


def main(argv):
    command = argv[1] if len(argv) > 1 else "get"
    if command in ("-h", "--help", "help"):
        print(usage())
        return 0

    with open_device() as device:
        feature_idx = device.resolve_feature()

        if command == "get":
            print(f"Gain: {device.read_field(feature_idx, FIELD_GAIN)} / 100")

        elif command == "set":
            if len(argv) < 3:
                sys.exit(usage())
            gain = int(argv[2])
            if not 0 <= gain <= 100:
                sys.exit("Gain must be 0-100")
            device.write_field(feature_idx, FIELD_GAIN, gain)
            print(f"Gain: {gain} / 100")

        elif command in ("mute", "unmute"):
            muted = command == "mute"
            device.write_field(feature_idx, FIELD_MUTE, 0x00 if muted else 0x01)
            print("Muted" if muted else "Unmuted")

        elif command == "smartlock":
            if len(argv) < 3 or argv[2] not in ("on", "off"):
                sys.exit("Usage: yeti-ctl.py smartlock on|off")
            enabled = argv[2] == "on"
            device.write_field(feature_idx, FIELD_LOCK_WRITE,
                               LOCK_ON if enabled else LOCK_OFF)
            print(f"Smart Lock: {argv[2]}")

        elif command == "status":
            print_status(device, feature_idx)

        elif command == "listen":
            listen(device, feature_idx)

        else:
            sys.exit(usage())

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
