"""Protocol frame tests.

Command frames are transcribed from the PJD7820HD user guide, "RS232 command
table" (pp. 66-73). Reply frames were captured off the real projector, because
the guide only ever shows single-byte replies and that hides the actual framing
rule. If a builder or the parser stops matching these, it is the code that is
wrong.

Run with:  python -m pytest tests/ -v
"""

from __future__ import annotations

import pytest

from custom_components.viewsonic_projector.protocol import (
    NAK_FRAME,
    build_read,
    build_write,
    payload_int,
    payload_signed,
    take_reply,
)

# Captured from the projector over the bridge, all checksum-valid.
LAMP_HOURS_REPLY = bytes.fromhex("05 14 00 06 00 00 00 B9 0C 00 00 DF".replace(" ", ""))
POWER_OFF_REPLY = bytes.fromhex("051400030000000017")
POWER_ON_REPLY = bytes.fromhex("051400030000000118")
ERROR_STATUS_REPLY = bytes.fromhex(
    "0514001C000000150400000000000000000000000000000000004D000000000005009B".replace(
        " ", ""
    )
)


def _hex(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        # Power on and off differ in the COMMAND byte, not the value byte.
        (build_write(0x11, 0x00, 0x00), "06 14 00 04 00 34 11 00 00 5D"),
        (build_write(0x11, 0x01, 0x00), "06 14 00 04 00 34 11 01 00 5E"),
        (build_read(0x11, 0x00), "07 14 00 05 00 34 00 00 11 00 5E"),
        # Source.
        (build_write(0x13, 0x01, 0x00), "06 14 00 04 00 34 13 01 00 60"),
        (build_write(0x13, 0x01, 0x08), "06 14 00 04 00 34 13 01 08 68"),
        (build_write(0x13, 0x01, 0x03), "06 14 00 04 00 34 13 01 03 63"),
        (build_read(0x13, 0x01), "07 14 00 05 00 34 00 00 13 01 61"),
        # Blank / freeze / mute.
        (build_write(0x12, 0x09, 0x01), "06 14 00 04 00 34 12 09 01 68"),
        (build_write(0x13, 0x00, 0x01), "06 14 00 04 00 34 13 00 01 60"),
        (build_write(0x14, 0x00, 0x01), "06 14 00 04 00 34 14 00 01 61"),
        # Volume: up and down are separate commands, not values.
        (build_write(0x14, 0x01, 0x00), "06 14 00 04 00 34 14 01 00 61"),
        (build_write(0x14, 0x02, 0x00), "06 14 00 04 00 34 14 02 00 62"),
        # Picture.
        (build_write(0x12, 0x04, 0x03), "06 14 00 04 00 34 12 04 03 65"),
        (build_write(0x12, 0x0B, 0x05), "06 14 00 04 00 34 12 0B 05 6E"),
        (build_write(0x11, 0x2C, 0x08), "06 14 00 04 00 34 11 2C 08 91"),
        (build_write(0x12, 0x0F, 0x01), "06 14 00 04 00 34 12 0F 01 6E"),
        # HDMI / CEC / 3D / installation.
        (build_write(0x11, 0x28, 0x02), "06 14 00 04 00 34 11 28 02 87"),
        (build_write(0x11, 0x2B, 0x01), "06 14 00 04 00 34 11 2B 01 89"),
        (build_write(0x12, 0x20, 0x05), "06 14 00 04 00 34 12 20 05 83"),
        (build_write(0x12, 0x00, 0x03), "06 14 00 04 00 34 12 00 03 61"),
        (build_write(0x0C, 0x48, 0x01), "06 14 00 04 00 34 0C 48 01 A1"),
        # Destructive one-shots.
        (build_write(0x11, 0x02, 0x00), "06 14 00 04 00 34 11 02 00 5F"),
        (build_write(0x15, 0x01, 0x00), "06 14 00 04 00 34 15 01 00 62"),
        # Reads.
        (build_read(0x15, 0x01), "07 14 00 05 00 34 00 00 15 01 63"),
        (build_read(0x0C, 0x0D), "07 14 00 05 00 34 00 00 0C 0D 66"),
        (build_read(0x11, 0x10), "07 14 00 05 00 34 00 00 11 10 6E"),
    ],
)
def test_frames_match_command_table(frame: bytes, expected: str) -> None:
    """Built frames are byte-identical to the published command table."""
    assert _hex(frame) == expected


def test_wide_reply_uses_length_byte_not_byte_zero() -> None:
    """A 12-byte lamp reply is read whole.

    Byte 0 is 0x05 here while the length byte is 0x06, so the two disagree.
    Deriving the size from byte 0 truncates the frame to 9 bytes, fails the
    checksum, and silently discards every lamp-hours reply forever.
    """
    assert LAMP_HOURS_REPLY[0] + 4 != len(LAMP_HOURS_REPLY)
    assert LAMP_HOURS_REPLY[3] + 6 == len(LAMP_HOURS_REPLY)

    buffer = bytearray(LAMP_HOURS_REPLY)
    res = take_reply(buffer)
    assert res is not None
    assert not buffer
    assert payload_int(res.payload) == 3257


@pytest.mark.parametrize(
    ("reply", "expected"),
    [(POWER_OFF_REPLY, 0), (POWER_ON_REPLY, 1)],
)
def test_power_replies_decode(reply: bytes, expected: int) -> None:
    """The documented power replies still decode to 0 and 1."""
    res = take_reply(bytearray(reply))
    assert res is not None
    assert payload_int(res.payload) == expected


def test_error_status_block_parses() -> None:
    """The 34-byte error block is accepted whole."""
    buffer = bytearray(ERROR_STATUS_REPLY)
    res = take_reply(buffer)
    assert res is not None
    assert not buffer
    assert len(res.payload) == 29


def test_values_are_little_endian() -> None:
    """0xB9 0x0C decodes as 3257, not 47372."""
    res = take_reply(bytearray(LAMP_HOURS_REPLY))
    assert res is not None
    assert payload_int(res.payload) == 0x0CB9


def test_incomplete_frame_is_kept() -> None:
    """A partial frame is left intact until the rest of it arrives."""
    buffer = bytearray(LAMP_HOURS_REPLY[:7])
    assert take_reply(buffer) is None
    assert len(buffer) == 7

    buffer.extend(LAMP_HOURS_REPLY[7:])
    res = take_reply(buffer)
    assert res is not None
    assert payload_int(res.payload) == 3257


def test_leading_garbage_is_discarded() -> None:
    """Stray bytes ahead of a valid frame are resynchronised past.

    Two clients sharing the bridge interleave, and the ESP8266 bootloader dumps
    noise onto the line at power-up, so this is routine rather than exceptional.
    """
    buffer = bytearray(b"\x00\x03\xff\x14\x00" + POWER_ON_REPLY)
    res = take_reply(buffer)
    assert res is not None
    assert payload_int(res.payload) == 1


def test_bad_checksum_is_rejected() -> None:
    """A frame whose checksum does not add up yields nothing."""
    corrupt = bytearray(POWER_ON_REPLY)
    corrupt[-1] ^= 0xFF
    assert take_reply(corrupt) is None


def test_two_frames_in_one_read() -> None:
    """Back-to-back frames are consumed one at a time."""
    buffer = bytearray(POWER_ON_REPLY + LAMP_HOURS_REPLY)
    first = take_reply(buffer)
    second = take_reply(buffer)
    assert first is not None and payload_int(first.payload) == 1
    assert second is not None and payload_int(second.payload) == 3257
    assert not buffer


def test_nak_is_recognised_as_a_refusal() -> None:
    """The projector's refusal frame is an answer, not garbage.

    In standby it NAKs most queries. Reading this as noise means waiting out a
    full reply timeout for every refused command on every sweep.
    """
    buffer = bytearray(NAK_FRAME)
    reply = take_reply(buffer)
    assert reply is not None
    assert reply.supported is False
    assert not buffer


def test_nak_frame_is_checksum_valid() -> None:
    """The NAK obeys the same length and checksum rules as any other frame."""
    assert NAK_FRAME == bytes.fromhex("001400000014")
    assert NAK_FRAME[3] + 6 == len(NAK_FRAME)
    assert sum(NAK_FRAME[1:-1]) & 0xFF == NAK_FRAME[-1]


def test_nak_between_two_replies() -> None:
    """A refusal in the middle of the stream doesn't eat its neighbours."""
    buffer = bytearray(POWER_ON_REPLY + NAK_FRAME + LAMP_HOURS_REPLY)
    first = take_reply(buffer)
    middle = take_reply(buffer)
    last = take_reply(buffer)
    assert first is not None and payload_int(first.payload) == 1
    assert middle is not None and middle.supported is False
    assert last is not None and payload_int(last.payload) == 3257
    assert not buffer


def test_adjustments_decode_as_signed() -> None:
    """Vertical keystone at -4 arrives as 0xFC, not as 252."""
    keystone = bytes.fromhex("05140003000000FC13")
    assert len(keystone) == 9
    reply = take_reply(bytearray(keystone))
    assert reply is not None
    assert payload_int(reply.payload) == 252
    assert payload_signed(reply.payload) == -4


def test_every_control_builds_a_valid_frame() -> None:
    """Every row of the command table produces a well-formed frame."""
    from custom_components.viewsonic_projector.const import CONTROLS, POWER, Kind

    for control in (POWER, *CONTROLS):
        pairs = [
            p
            for p in (control.on, control.off, control.up, control.down, control.execute)
            if p is not None
        ]
        if control.kind is Kind.SELECT:
            assert control.option_cmd is not None
            pairs += [(control.option_cmd, v) for v in control.options.values()]

        for cmd, value in pairs:
            frame = build_write(control.group, cmd, value)
            assert len(frame) == 10, control.key
            assert frame[0] == 0x06, control.key
            assert sum(frame[1:9]) & 0xFF == frame[9], control.key

        if control.read_cmd is not None:
            frame = build_read(control.group, control.read_cmd)
            assert len(frame) == 11, control.key
            assert sum(frame[1:10]) & 0xFF == frame[10], control.key
