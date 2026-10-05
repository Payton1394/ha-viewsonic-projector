"""Let the tests run without Home Assistant installed.

Importing anything from the integration runs its ``__init__``, which imports a
handful of Home Assistant names. When Home Assistant is not installed, these
stand-ins provide just those names; with it installed, they stay out of the way.
"""

from __future__ import annotations

import enum
import sys
import types

try:
    import homeassistant  # noqa: F401
except ImportError:

    class _Subscriptable:
        def __class_getitem__(cls, item):
            return cls

    class _HomeAssistant:
        pass

    class _ConfigEntry(_Subscriptable):
        pass

    class _UpdateFailed(Exception):
        pass

    class _DataUpdateCoordinator(_Subscriptable):
        def __init__(self, hass, logger, name=None, update_interval=None, **_):
            self.hass, self.logger, self.name = hass, logger, name
            self.update_interval = update_interval
            self.data = None

        def async_set_updated_data(self, data):
            self.data = data

    class _Platform(enum.StrEnum):
        BINARY_SENSOR = "binary_sensor"
        BUTTON = "button"
        SELECT = "select"
        SENSOR = "sensor"
        SWITCH = "switch"

    def _module(name: str, **attrs) -> types.ModuleType:
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        sys.modules[name] = module
        return module

    _module("homeassistant")
    _module("homeassistant.core", HomeAssistant=_HomeAssistant)
    _module("homeassistant.config_entries", ConfigEntry=_ConfigEntry)
    _module("homeassistant.const", CONF_HOST="host", CONF_NAME="name", CONF_PORT="port", Platform=_Platform)
    _module("homeassistant.helpers")
    _module(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=_DataUpdateCoordinator,
        UpdateFailed=_UpdateFailed,
    )
