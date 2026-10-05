"""The coordinator against a fake projector on a local socket.

How the real line misbehaved (Home Assistant's log, October 2026): a reply that
came after its query had timed out sat in the socket and was read as the answer
to the next query. The power switch flipped on and off every few minutes, selects
reported codes that belong to other controls ("source returned unmapped code
0x415"), and a stray NAK read as "Projector refused the power query" made every
entity unavailable. These tests stage exactly that.

Run with:  python -m pytest tests/ -v
"""

from __future__ import annotations

import asyncio

import pytest

from custom_components.viewsonic_projector import coordinator as cmod
from custom_components.viewsonic_projector.const import CONTROLS_BY_KEY, POWER
from custom_components.viewsonic_projector.protocol import NAK_FRAME

SOURCE = CONTROLS_BY_KEY["source"]
LAMP_HOURS_REPLY = bytes.fromhex("051400060000" "00B90C0000DF")


def single(value: int) -> bytes:
    """A reply carrying one byte, as power, the switches and the selects send."""
    body = bytes([0x14, 0x00, 0x03, 0x00, 0x00, 0x00, value])
    return bytes([0x05]) + body + bytes([sum(body) & 0xFF])


class FakeProjector:
    """Answers each read from a script: per query, a list of (frames, delay)."""

    def __init__(self) -> None:
        self.script: dict[tuple[int, int], list[tuple[bytes, float]]] = {}

    def on(self, control, *answers: tuple[bytes, float]) -> None:
        self.script.setdefault((control.group, control.read_cmd), []).extend(answers)

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def _serve(self, reader, writer) -> None:
        try:
            while True:
                query = await reader.readexactly(11)        # build_read: 11 bytes
                answers = self.script.get((query[8], query[9]))
                frame, delay = answers.pop(0) if answers else (NAK_FRAME, 0)
                if frame is None:
                    continue                                # silent: no answer at all
                asyncio.get_running_loop().call_later(delay, writer.write, frame)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    """Shorter waits than the real line needs, so the tests run in seconds."""
    monkeypatch.setattr(cmod, "REPLY_TIMEOUT", 0.3)
    monkeypatch.setattr(cmod, "STALE_QUIET_AFTER_MISS", 0.2)


async def connected(fake: FakeProjector) -> cmod.ViewSonicCoordinator:
    port = await fake.start()
    coordinator = cmod.ViewSonicCoordinator(None, "127.0.0.1", port, "Test", 3)
    await coordinator._connect()
    return coordinator


def test_a_late_reply_is_not_the_next_answer():
    async def run():
        fake = FakeProjector()
        # Source answers 0.1 s after its query timed out (0.4 s > 0.3 s), while
        # the power query that followed still waits for its own answer (0.15 s):
        # read as power, source's 0x03 is "on".
        fake.on(SOURCE, (single(0x03), 0.4))
        fake.on(POWER, (single(0x00), 0.15))
        c = await connected(fake)
        with pytest.raises(TimeoutError):
            await c._read_control(SOURCE)
        assert await c._read_control(POWER) is False
        await c.async_disconnect()

    asyncio.run(run())


def test_a_wider_frame_is_never_a_switch_or_select_answer():
    async def run():
        fake = FakeProjector()
        # A lamp-hours frame, then the real answer, on the same query.
        fake.on(SOURCE, (LAMP_HOURS_REPLY + single(0x03), 0))
        c = await connected(fake)
        assert await c._read_control(SOURCE) == SOURCE.options_by_code[0x03]
        await c.async_disconnect()

    asyncio.run(run())


def test_bytes_already_waiting_are_thrown_away():
    async def run():
        fake = FakeProjector()
        fake.on(POWER, (single(0x00), 0))
        c = await connected(fake)
        # A stray NAK already in the socket before the power query goes out.
        c._reader.feed_data(NAK_FRAME)
        assert await c._read_control(POWER) is False
        await c.async_disconnect()

    asyncio.run(run())


def test_a_missed_power_reply_keeps_the_last_state():
    async def run():
        fake = FakeProjector()
        fake.on(POWER, (None, 0), (single(0x01), 0))
        c = await connected(fake)
        c.data = {POWER.key: True}
        c._last_power = True
        assert (await c._async_update_data())[POWER.key] is True     # missed: kept
        assert (await c._async_update_data())[POWER.key] is True     # answered
        await c.async_disconnect()

    asyncio.run(run())


def test_several_misses_in_a_row_mark_it_unavailable():
    async def run():
        fake = FakeProjector()
        fake.on(POWER, *[(None, 0)] * cmod.POWER_MISSES_ALLOWED)
        c = await connected(fake)
        c.data = {POWER.key: True}
        c._last_power = True
        for _ in range(cmod.POWER_MISSES_ALLOWED - 1):
            await c._async_update_data()
        with pytest.raises(cmod.UpdateFailed):
            await c._async_update_data()
        await c.async_disconnect()

    asyncio.run(run())


def test_a_power_change_needs_two_reads_that_agree():
    async def run():
        fake = FakeProjector()
        fake.on(POWER, (single(0x01), 0), (single(0x00), 0), (single(0x01), 0), (single(0x01), 0))
        c = await connected(fake)
        c.data = {POWER.key: False}
        c._last_power = False
        published = [(await c._async_update_data())[POWER.key] for _ in range(4)]
        # One "on" between offs is a glitch; two in a row is the projector.
        assert published == [False, False, False, True]
        await c.async_disconnect()

    asyncio.run(run())
