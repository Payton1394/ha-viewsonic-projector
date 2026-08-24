"""Serialised TCP client and polling coordinator for the ViewSonic projector.

The projector speaks RS-232; an ESPHome node running ``stream_server`` bridges
that line onto TCP. Because a read reply carries no indication of which query it
answers, every exchange is serialised behind a lock and the receive buffer is
cleared immediately before each request, so a late reply from a timed-out query
is discarded rather than mistaken for the next answer.

Responsiveness comes from four things:

* Refusals are recognised. In standby the projector NAKs most queries -- only
  power, lamp hours and a handful of others answer -- and a NAK arrives at once.
  Reading it as an answer rather than as garbage saves a full reply timeout per
  refused command on every sweep, which is most of them while the lamp is off.
* Refused controls drop out of the rotation until the projector's state changes,
  so a standby sweep costs a couple of round trips rather than thirty.
* A write publishes its expected result immediately, then confirms by reading
  the projector back. The UI moves at once and self-corrects if the projector
  disagrees.
* A power change holds its assumed state for a grace period, because the
  projector keeps reporting the old state while the lamp strikes or cools, and
  without this the switch visibly flaps back before settling.

A refusal is emphatically *not* treated as "this model lacks the command".
Availability follows power state, so anything permanent inferred from a NAK
would be wrong for every projector that happened to be in standby at the time.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONTROLS,
    CONTROLS_BY_KEY,
    KEY_ERROR_STATUS,
    POWER,
    POWER_CONFIRM_SETTLE,
    REARM_AFTER,
    REPLY_TIMEOUT,
    SLOW_READS_PER_CYCLE,
    WRITE_CONFIRM,
    Control,
    Kind,
)
from .protocol import (
    Reply,
    build_read,
    build_write,
    payload_int,
    payload_signed,
    take_reply,
)

_LOGGER = logging.getLogger(__name__)


class CommandRefused(Exception):
    """Raised when the projector NAKs a command.

    Means "not available in the projector's current state", typically standby.
    """


class ViewSonicCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Own the TCP link to the projector and poll it on a schedule."""

    def __init__(
        self, hass: HomeAssistant, host: str, port: int, name: str, scan_interval: int
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._buffer = bytearray()
        self._lock = asyncio.Lock()
        self._queue: deque[str] = deque()
        self._refused: set[str] = set()
        self._rearm_at: float = 0.0
        self._last_power: bool | None = None
        self._power_assumed: bool | None = None
        self._power_grace_until: float = 0.0

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        """Open the TCP link if it is not already up."""
        if self._writer is not None and not self._writer.is_closing():
            return

        await self.async_disconnect()
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=REPLY_TIMEOUT * 4
        )
        self._buffer.clear()

    async def async_disconnect(self) -> None:
        """Tear the TCP link down, tolerating an already-dead socket."""
        writer, self._writer, self._reader = self._writer, None, None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, TimeoutError):  # Socket was already gone.
            pass

    # ------------------------------------------------------------------
    # Low-level exchange -- callers must hold the lock
    # ------------------------------------------------------------------

    async def _exchange(self, group: int, cmd: int) -> Reply:
        """Send a read query and return the projector's frame."""
        assert self._writer is not None and self._reader is not None

        # Untagged replies: anything still buffered would be misread as the
        # answer to this query, so start clean.
        self._buffer.clear()
        self._writer.write(build_read(group, cmd))
        await self._writer.drain()

        loop = asyncio.get_running_loop()
        deadline = loop.time() + REPLY_TIMEOUT
        while True:
            reply = take_reply(self._buffer)
            if reply is not None:
                return reply

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"no reply to {group:#04x}/{cmd:#04x}")

            chunk = await asyncio.wait_for(self._reader.read(128), timeout=remaining)
            if not chunk:
                raise ConnectionError("bridge closed the connection")
            self._buffer.extend(chunk)

    # ------------------------------------------------------------------
    # Decoding
    # ------------------------------------------------------------------

    def _decode(self, control: Control, payload: bytes) -> Any:
        """Turn a reply payload into the value an entity wants."""
        if control.key == KEY_ERROR_STATUS:
            # A 29-byte status block, not a scalar. Surface it verbatim.
            return payload.hex(" ").upper()

        if control.kind is Kind.SWITCH:
            # Every switch, power included, reports 1 for on and 0 for off.
            return bool(payload_int(payload))

        if control.kind is Kind.SELECT:
            code = payload_int(payload)
            option = control.options_by_code.get(code)
            if option is None:
                _LOGGER.warning(
                    "%s returned unmapped code %#04x; known codes are %s",
                    control.key,
                    code,
                    sorted(control.options_by_code),
                )
            return option

        if control.kind is Kind.STEP:
            # Adjustments swing either side of zero: keystone reports 0xFC
            # for -4, which read unsigned would look like 252.
            return payload_signed(payload)

        return payload_int(payload)

    async def _read_control(self, control: Control) -> Any:
        """Read one control. Caller must hold the lock."""
        assert control.read_cmd is not None
        reply = await self._exchange(control.group, control.read_cmd)
        if not reply.supported:
            raise CommandRefused(control.key)
        return self._decode(control, reply.payload)

    def is_read_refused(self, control: Control) -> bool:
        """Whether the projector currently refuses to report this control.

        Writes still work: the PJD7820HD accepts "freeze on" while refusing
        "is it frozen?", confirmed on a quiet line. Such a control stays fully
        usable, but its state is what we last commanded rather than observed,
        so entities built on it declare an assumed state.
        """
        return control.key in self._refused

    # ------------------------------------------------------------------
    # Rotation bookkeeping
    # ------------------------------------------------------------------

    def _rearm(self) -> None:
        """Put every refused control back into the rotation."""
        self._refused.clear()
        self._queue = deque(
            c.key for c in CONTROLS if c.read_cmd is not None
        )
        self._rearm_at = asyncio.get_running_loop().time() + REARM_AFTER

    # ------------------------------------------------------------------
    # Startup priming
    # ------------------------------------------------------------------

    async def async_prime(self) -> None:
        """Read everything once so entities start with values where possible.

        Refusals come back immediately, so this is quick even in standby.
        Nothing is inferred permanently from them.
        """
        data: dict[str, Any] = dict(self.data or {})
        self._rearm()

        async with self._lock:
            try:
                await self._connect()
                for control in CONTROLS:
                    if control.read_cmd is None:
                        continue
                    try:
                        value = await self._read_control(control)
                    except CommandRefused:
                        self._refused.add(control.key)
                    except TimeoutError:
                        _LOGGER.debug("No reply for %s while priming", control.key)
                    else:
                        if value is not None:
                            data[control.key] = value
            except (OSError, ConnectionError) as err:
                _LOGGER.debug("Priming stopped early: %s", err)

        for key in self._refused:
            if key in self._queue:
                self._queue.remove(key)

        if self._refused:
            _LOGGER.debug(
                "Projector refused %d controls (normal in standby): %s",
                len(self._refused),
                ", ".join(sorted(self._refused)),
            )

        self.async_set_updated_data(data)

    # ------------------------------------------------------------------
    # Public API used by entities
    # ------------------------------------------------------------------

    async def _send_write(self, control: Control, cmd: int, value: int) -> None:
        """Push a write command onto the wire."""
        try:
            async with self._lock:
                await self._connect()
                assert self._writer is not None
                self._buffer.clear()
                self._writer.write(build_write(control.group, cmd, value))
                await self._writer.drain()
        except (OSError, TimeoutError) as err:
            await self.async_disconnect()
            raise UpdateFailed(f"Failed sending command to {self.host}: {err}") from err

    async def async_write(
        self, control: Control, cmd: int, value: int, optimistic: Any = None
    ) -> None:
        """Write a setting, publish the expected result, then confirm it."""
        await self._send_write(control, cmd, value)

        if optimistic is not None:
            self.data[control.key] = optimistic
            self.async_set_updated_data(self.data)

        # No point confirming a control the projector will not report; the
        # optimistic value published above is the best we can do.
        if control.read_cmd is None or self.is_read_refused(control):
            return

        await asyncio.sleep(WRITE_CONFIRM)
        await self.async_refresh_control(control)

    async def async_set_power(self, turn_on: bool) -> None:
        """Change power, holding the assumed state while the lamp settles."""
        cmd, value = POWER.on if turn_on else POWER.off

        self._power_assumed = turn_on
        self._power_grace_until = (
            asyncio.get_running_loop().time() + POWER_CONFIRM_SETTLE
        )

        try:
            await self._send_write(POWER, cmd, value)
        except UpdateFailed:
            self._power_assumed = None
            raise

        # Coming out of standby unlocks most of the command set, so stop
        # skipping everything that was refused while the lamp was off.
        self._rearm()

        self.data[POWER.key] = turn_on
        self.async_set_updated_data(self.data)

    async def async_refresh_control(self, control: Control) -> None:
        """Re-read a single control and publish it, without a full poll."""
        if control.read_cmd is None:
            return
        try:
            async with self._lock:
                await self._connect()
                value = await self._read_control(control)
        except CommandRefused:
            self._refused.add(control.key)
            if control.key in self._queue:
                self._queue.remove(control.key)
            return
        except TimeoutError:
            return  # The rotation will pick it up later.
        except (OSError, ConnectionError) as err:
            await self.async_disconnect()
            _LOGGER.debug("Refresh of %s failed: %s", control.key, err)
            return

        if value is not None:
            self.data[control.key] = value
            self.async_set_updated_data(self.data)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll power every cycle, plus a slice of everything still answering."""
        data: dict[str, Any] = dict(self.data or {})
        loop = asyncio.get_running_loop()

        # Periodically retry refused controls even without a power change --
        # the projector can be switched on at its own panel.
        if self._refused and loop.time() >= self._rearm_at:
            self._rearm()

        try:
            async with self._lock:
                await self._connect()

                power = self._apply_power_grace(await self._read_control(POWER))
                data[POWER.key] = power

                if self._last_power is not None and power != self._last_power:
                    # State change unlocks or locks a large part of the
                    # command set; re-test everything.
                    self._rearm()
                self._last_power = power

                for _ in range(min(SLOW_READS_PER_CYCLE, len(self._queue))):
                    key = self._queue[0]
                    self._queue.rotate(-1)
                    control = CONTROLS_BY_KEY[key]
                    try:
                        value = await self._read_control(control)
                    except CommandRefused:
                        # Not available in this state. Stop asking until
                        # something changes; the entity keeps its last value.
                        self._refused.add(key)
                        self._queue.remove(key)
                        continue
                    except TimeoutError:
                        _LOGGER.debug("No reply for %s; keeping previous value", key)
                        continue
                    if value is not None:
                        data[key] = value

        except CommandRefused as err:
            raise UpdateFailed("Projector refused the power query") from err
        except (OSError, TimeoutError) as err:
            await self.async_disconnect()
            raise UpdateFailed(f"Projector at {self.host} not responding: {err}") from err

        return data

    def _apply_power_grace(self, reported: bool) -> bool:
        """Prefer the commanded power state while the lamp is still changing."""
        if self._power_assumed is None:
            return reported

        if asyncio.get_running_loop().time() >= self._power_grace_until:
            self._power_assumed = None
            return reported

        if reported != self._power_assumed:
            return self._power_assumed

        # Projector agrees; stop second-guessing it.
        self._power_assumed = None
        return reported
