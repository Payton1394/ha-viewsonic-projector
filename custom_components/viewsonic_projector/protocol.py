"""Frame encoding and decoding for the ViewSonic RS-232 control protocol.

Documented in the PJD7820HD user guide, "RS232 command table" (p.66), but the
guide only ever shows single-byte replies, which hides two things. Both were
established by capturing real traffic off the projector:

    lamp hours    05 14 00 06 00 00 00 B9 0C 00 00 DF     (12 bytes)
    power         05 14 00 03 00 00 00 00 17              (9 bytes)
    error status  05 14 00 1C 00 00 00 15 04 ... 05 00 9B (34 bytes)

**Byte 0 is a message type, not a length.** 0x05 reply, 0x06 write, 0x07 read.
The length lives in byte 3, and the total frame is that plus six. Deriving the
length from byte 0 appears to work, because for one-byte replies the two happen
to agree -- and then silently fails on every wider reply.

**Values are little-endian**, sitting after three bytes of padding:

    power       00 00 00 | 00           -> 0
    lamp hours  00 00 00 | B9 0C 00 00  -> 0x00000CB9 = 3257

The lamp-hours decode was confirmed against the projector's own OSD, so the
little-endian reading is field-verified and not just checksum-consistent --
big-endian would give 47372 and also pass the checksum.

The checksum is the sum of every byte after byte 0, modulo 256.

Read replies carry no indication of which query they answer -- a power reply and
a lamp-hours reply differ only in length. Callers must issue one request at a
time; see ``coordinator.ViewSonicCoordinator``.
"""

from __future__ import annotations

HEADER = 0x14
WRITE_MARK = 0x34

TYPE_NAK = 0x00
TYPE_REPLY = 0x05
TYPE_WRITE = 0x06
TYPE_READ = 0x07

# A NAK is a well-formed, checksum-valid frame with type 0x00 and no payload:
#
#     00 14 00 00 00 14
#
# The projector sends it for any command it does not implement. The published
# command table is generic across the ViewSonic DLP range, so a given model
# NAKs a good share of it. Treating this as garbage rather than as an answer
# costs a full reply timeout per unsupported command on every poll.
NAK_FRAME = bytes([TYPE_NAK, HEADER, 0x00, 0x00, 0x00, HEADER])

# type + header + 0x00 + len + at least one payload byte + checksum
_MIN_FRAME = 6

# Header is 4 bytes; the value starts after 3 bytes of padding.
_PAYLOAD_START = 4
_VALUE_OFFSET = 3
_MAX_VALUE_BYTES = 4


def _checksum(body: bytes) -> int:
    """Sum of every byte after byte 0, modulo 256."""
    return sum(body) & 0xFF


def build_write(group: int, cmd: int, value: int) -> bytes:
    """Build a write command, e.g. build_write(0x12, 0x09, 0x01) -> blank on."""
    body = bytes([HEADER, 0x00, 0x04, 0x00, WRITE_MARK, group, cmd, value])
    return bytes([TYPE_WRITE]) + body + bytes([_checksum(body)])


def build_read(group: int, cmd: int) -> bytes:
    """Build a read query, e.g. build_read(0x15, 0x01) -> read lamp hours."""
    body = bytes([HEADER, 0x00, 0x05, 0x00, WRITE_MARK, 0x00, 0x00, group, cmd])
    return bytes([TYPE_READ]) + body + bytes([_checksum(body)])


class Reply:
    """One decoded frame from the projector."""

    __slots__ = ("payload", "supported")

    def __init__(self, payload: bytes, supported: bool = True) -> None:
        """Hold a reply's payload, or record that the command was refused."""
        self.payload = payload
        self.supported = supported

    def __repr__(self) -> str:
        """Describe the reply for logs."""
        if not self.supported:
            return "Reply(unsupported)"
        return f"Reply({self.payload.hex(' ')})"


def take_reply(buffer: bytearray) -> Reply | None:
    """Consume the first complete, checksum-valid frame from ``buffer``.

    Returns None when the buffer does not yet hold a full valid frame, a Reply
    carrying the payload for a normal answer, or a Reply with supported=False
    when the projector NAKed the command.

    Mutates ``buffer`` in place, discarding leading garbage -- the projector
    emits bare ACK bytes, the ESP8266 bootloader dumps noise onto the line at
    power-up, and two clients sharing the bridge can interleave -- so
    resynchronising rather than trusting the stream is deliberate.
    """
    while len(buffer) >= _MIN_FRAME:
        # Frames open with a type byte, then 14 00.
        if buffer[0] not in (TYPE_REPLY, TYPE_NAK) or buffer[1] != HEADER or buffer[2] != 0x00:
            del buffer[0]
            continue

        size = buffer[3] + 6
        if len(buffer) < size:
            return None  # Incomplete; wait for more bytes.

        frame = bytes(buffer[:size])
        if _checksum(frame[1 : size - 1]) != frame[size - 1]:
            del buffer[0]
            continue

        del buffer[:size]

        if frame[0] == TYPE_NAK:
            return Reply(b"", supported=False)
        return Reply(frame[_PAYLOAD_START : size - 1])

    return None


def payload_int(payload: bytes) -> int:
    """Decode a payload's little-endian value, skipping its padding."""
    return int.from_bytes(
        payload[_VALUE_OFFSET : _VALUE_OFFSET + _MAX_VALUE_BYTES], "little"
    )


def payload_signed(payload: bytes) -> int:
    """Decode a single-byte payload value as signed.

    Adjustments that swing either side of zero are two's complement: vertical
    keystone reports 0xFC for -4, which read unsigned looks like 252.
    """
    return int.from_bytes(
        payload[_VALUE_OFFSET : _VALUE_OFFSET + 1], "little", signed=True
    )
