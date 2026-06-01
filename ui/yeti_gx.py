#!/usr/bin/env python3
"""
Logitech Yeti GX library — HID++ 2.0, feature 0x8370 (index 13)
"""
import os
import glob
import time
import threading

VENDOR_ID  = "046D"
PRODUCT_ID = "0AFC"

DEV_IDX  = 0xFF
FEAT_IDX = 13
SW_ID    = 12
FUNC_GET = 2
FUNC_SET = 3
FUNC_GET_SW = (FUNC_GET << 4) | SW_ID   # 0x2C
FUNC_SET_SW = (FUNC_SET << 4) | SW_ID   # 0x3C


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


class YetiGXError(Exception):
    pass


class YetiGX:
    def __init__(self):
        path = find_hidraw()
        if path is None:
            raise YetiGXError("Yeti GX not found. Is it plugged in?")
        self._f = open(path, "r+b", buffering=0)
        os.set_blocking(self._f.fileno(), False)
        self._lock = threading.Lock()
        self._listener_thread = None
        self._listener_stop = threading.Event()
        self._cb_mute = None
        self._cb_gain = None
        self._cb_smartlock = None

    def close(self):
        self.stop_listening()
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    # --- internal ---

    def _send_recv(self, data, timeout=0.5):
        with self._lock:
            self._f.write(bytes(data))
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    r = self._f.read(64)
                    if r:
                        return r
                except BlockingIOError:
                    time.sleep(0.01)
        return None

    # --- gain ---

    def get_gain(self) -> int:
        r = self._send_recv([0x10, DEV_IDX, FEAT_IDX, FUNC_GET_SW, 0x00, 0x01, 0x00])
        if r and len(r) >= 8:
            return r[7]
        raise YetiGXError("No response to get_gain")

    def set_gain(self, gain: int):
        if not 0 <= gain <= 100:
            raise ValueError("Gain must be 0–100")
        self._send_recv([0x10, DEV_IDX, FEAT_IDX, FUNC_SET_SW, 0x00, 0x01, gain])

    # --- mute ---

    def get_mute(self) -> bool:
        """Returns True if muted."""
        r = self._send_recv([0x10, DEV_IDX, FEAT_IDX, FUNC_GET_SW, 0x00, 0x00, 0x00])
        if r and len(r) >= 8:
            return r[7] == 0x00
        raise YetiGXError("No response to get_mute")

    def set_mute(self, muted: bool):
        self._send_recv([0x10, DEV_IDX, FEAT_IDX, FUNC_SET_SW, 0x00, 0x00, 0x00 if muted else 0x01])

    # --- smartlock ---

    def get_smartlock(self) -> bool:
        """Returns True if Smart Lock is enabled."""
        r = self._send_recv([0x10, DEV_IDX, FEAT_IDX, FUNC_GET_SW, 0x00, 0x02, 0x00])
        if r and len(r) >= 8:
            return r[7] == 0x01
        raise YetiGXError("No response to get_smartlock")

    def set_smartlock(self, enabled: bool):
        pkt = [0x11, DEV_IDX, FEAT_IDX, FUNC_SET_SW,
               0x00, 0x05, 0x07 if enabled else 0x06,
               0x00, 0xca, 0x00, 0x00, 0x02,
               0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        self._send_recv(pkt)

    # --- event listener ---
    # All device-initiated notifications share the format:
    #   11 ff 0d 20 00 <type> <value>
    # type 0x00 = mute:      value 0x00=muted,  0x01=unmuted
    # type 0x01 = gain:      value = gain 0-100 (physical dial)
    # type 0x05 = smartlock: value 0x00=off,    0x01=on

    def listen(self, on_mute=None, on_gain=None, on_smartlock=None):
        """
        Start a background thread that fires callbacks when physical controls change.
          on_mute(muted: bool)
          on_gain(gain: int)
          on_smartlock(enabled: bool)
        """
        self._cb_mute = on_mute
        self._cb_gain = on_gain
        self._cb_smartlock = on_smartlock
        self._listener_stop.clear()
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

    def stop_listening(self):
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_stop.set()
            self._listener_thread.join(timeout=1)
        self._listener_thread = None

    def _listen_loop(self):
        while not self._listener_stop.is_set():
            try:
                r = self._f.read(64)
                if r and len(r) >= 7 and r[1] == 0xFF and r[2] == FEAT_IDX and r[3] == 0x20:
                    evt_type  = r[5]
                    evt_value = r[6]
                    if evt_type == 0x00 and self._cb_mute:
                        self._cb_mute(evt_value == 0x00)
                    elif evt_type == 0x01 and self._cb_gain:
                        self._cb_gain(evt_value)
                    elif evt_type == 0x05 and self._cb_smartlock:
                        self._cb_smartlock(evt_value == 0x01)
            except BlockingIOError:
                time.sleep(0.02)
            except OSError:
                break
