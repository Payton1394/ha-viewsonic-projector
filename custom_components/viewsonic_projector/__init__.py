"""The ViewSonic Projector integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_INTERVAL, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL
from .coordinator import ViewSonicCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

type ViewSonicConfigEntry = ConfigEntry[ViewSonicCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: ViewSonicConfigEntry) -> bool:
    """Set up ViewSonic Projector from a config entry."""
    coordinator = ViewSonicCoordinator(
        hass,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        scan_interval=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    # Read everything once so entities start populated where the projector is
    # willing to answer. In standby it refuses most queries, but a refusal is
    # immediate, so this stays quick either way.
    await coordinator.async_prime()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_options))
    return True


async def _async_reload_on_options(
    hass: HomeAssistant, entry: ViewSonicConfigEntry
) -> None:
    """Reload so a changed poll interval takes effect immediately."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ViewSonicConfigEntry) -> bool:
    """Unload a config entry and close the socket behind it."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_disconnect()
    return unloaded
