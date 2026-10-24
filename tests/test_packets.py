"""Packet building and parsing tests.

Every expected byte string below was taken from a real capture or a live
exchange with a Yeti GX, so these tests pin down the verified wire format.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("yeti_ctl", ROOT / "yeti-ctl.py")
yeti = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(yeti)


# --- request packets -------------------------------------------------------

def test_build_read_gain():
    assert yeti.build_read(13, yeti.FIELD_GAIN) == bytes.fromhex("10ff0d2c000100")


def test_build_read_mute():
    assert yeti.build_read(13, yeti.FIELD_MUTE) == bytes.fromhex("10ff0d2c000000")


def test_build_write_gain_42():
    assert yeti.build_write(13, yeti.FIELD_GAIN, 42) == bytes.fromhex("10ff0d3c00012a")


def test_build_write_smartlock_on_is_short():
    packet = yeti.build_write(13, yeti.FIELD_LOCK_WRITE, yeti.LOCK_ON)
    assert packet == bytes.fromhex("10ff0d3c000507")
    assert len(packet) == 7


def test_build_write_smartlock_off():
    assert yeti.build_write(13, yeti.FIELD_LOCK_WRITE, yeti.LOCK_OFF) == \
        bytes.fromhex("10ff0d3c000506")


def test_build_write_mute_unmute():
    assert yeti.build_write(13, yeti.FIELD_MUTE, 0x00) == bytes.fromhex("10ff0d3c000000")
    assert yeti.build_write(13, yeti.FIELD_MUTE, 0x01) == bytes.fromhex("10ff0d3c000001")


def test_build_feature_count_and_id():
    assert yeti.build_feature_count() == bytes.fromhex("10ff010c000000")
    assert yeti.build_feature_id(13) == bytes.fromhex("10ff011c0d0000")


# --- error handling --------------------------------------------------------

def test_error_detected():
    report = bytes.fromhex("10ffff0d2c0200")
    assert yeti.is_error(report)
    assert yeti.error_code(report) == 0x02
    assert yeti.describe_error(report) == "invalid argument"


def test_success_is_not_an_error():
    report = bytes.fromhex("11ff0d2c00010147000000000000000000000000")
    assert not yeti.is_error(report)


def test_error_never_matches_a_command():
    report = bytes.fromhex("10ffff0d2c0200")
    assert not yeti.matches(report, 13, yeti.FUNC_READ)


def test_error_codes_are_named():
    for code, name in yeti.ERROR_CODES.items():
        report = bytes([0x10, 0xFF, 0xFF, 0x0D, 0x2C, code, 0x00])
        assert yeti.describe_error(report) == name


# --- responses -------------------------------------------------------------

def test_parse_read_gain_71():
    report = bytes.fromhex("11ff0d2c00010147000000000000000000000000")
    assert yeti.parse_read(report) == (yeti.FIELD_GAIN, 0x47)


def test_parse_read_unmuted():
    report = bytes.fromhex("11ff0d2c00000001000000000000000000000000")
    assert yeti.parse_read(report) == (yeti.FIELD_MUTE, 0x01)


def test_parse_read_smartlock_on():
    report = bytes.fromhex("11ff0d2c00020501000000000000000000000000")
    assert yeti.parse_read(report) == (yeti.FIELD_LOCK_STATE, 0x01)


def test_parse_write_echo():
    report = bytes.fromhex("11ff0d3c00050700ca0000020000000000000000")
    assert yeti.parse_write(report) == (yeti.FIELD_LOCK_WRITE, yeti.LOCK_ON)


@pytest.mark.parametrize("index,feature_id", [
    (1, 0x0001), (2, 0x0003), (3, 0x0005), (4, 0x0011), (5, 0x00C2),
    (6, 0x1602), (7, 0x180A), (8, 0x1E81), (9, 0x4610), (10, 0x8040),
    (11, 0x8071), (12, 0x8081), (13, 0x8370),
])
def test_parse_feature_id(index, feature_id):
    report = bytes([0x11, 0xFF, 0x01, 0x1C,
                    feature_id >> 8, feature_id & 0xFF, 0x00, 0x00])
    assert yeti.parse_feature_id(report) == feature_id


def test_response_matching_requires_same_software_id():
    report = bytes.fromhex("11ff0d2c00010147000000000000000000000000")
    assert yeti.matches(report, 13, yeti.FUNC_READ, yeti.SW_ID)
    assert not yeti.matches(report, 13, yeti.FUNC_READ, 14)
    assert not yeti.matches(report, 12, yeti.FUNC_READ, yeti.SW_ID)
    assert not yeti.matches(report, 13, yeti.FUNC_WRITE, yeti.SW_ID)


# --- notifications ---------------------------------------------------------

def test_notification_muted():
    report = bytes.fromhex("11ff0d2000000000000000000000000000000000")
    assert yeti.parse_notification(report, 13) is True


def test_notification_unmuted():
    report = bytes.fromhex("11ff0d2000000100000000000000000000000000")
    assert yeti.parse_notification(report, 13) is False


def test_notification_ignores_other_reports():
    read_reply = bytes.fromhex("11ff0d2c00010147000000000000000000000000")
    assert yeti.parse_notification(read_reply, 13) is None


def test_mute_read_reply_is_not_a_notification():
    # same function and field as a notification, distinguished by software id
    read_reply = bytes.fromhex("11ff0d2c00000001000000000000000000000000")
    assert yeti.parse_notification(read_reply, 13) is None
    event = bytes.fromhex("11ff0d2000000100000000000000000000000000")
    assert yeti.parse_notification(event, 13) is False
