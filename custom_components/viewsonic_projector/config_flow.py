"""Config and options flows for the ViewSonic Projector integration."""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback

from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    POWER,
    REPLY_TIMEOUT,
)
from .protocol import build_read, take_reply

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
    }
)


async def _probe(host: str, port: int) -> None:
    """Confirm the bridge is reachable and the projector answers.

    Raises OSError or TimeoutError if either half of that is untrue.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(host, port), timeout=REPLY_TIMEOUT * 2
    )
    try:
        assert POWER.read_cmd is not None
        writer.write(build_read(POWER.group, POWER.read_cmd))
        await writer.drain()

        buffer = bytearray()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + REPLY_TIMEOUT
        while take_reply(buffer) is None:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError("projector did not answer a power query")
            chunk = await asyncio.wait_for(reader.read(128), timeout=remaining)
            if not chunk:
                raise ConnectionError("bridge closed the connection")
            buffer.extend(chunk)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (OSError, TimeoutError):
            pass


class ViewSonicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ViewSonic Projector."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the bridge address and verify the projector responds."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            try:
                await _probe(host, port)
            except (OSError, TimeoutError):
                # Either the bridge is unreachable or the projector is not
                # wired to it. Both look the same from here.
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> ViewSonicOptionsFlow:
        """Return the options flow."""
        return ViewSonicOptionsFlow()


class ViewSonicOptionsFlow(OptionsFlow):
    """Let the poll interval be tuned after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the poll interval."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL),
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
