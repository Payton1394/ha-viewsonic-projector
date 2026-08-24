"""Binary sensor entities for the ViewSonic Projector integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViewSonicConfigEntry
from .entity import ViewSonicEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViewSonicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the projector binary sensors."""
    async_add_entities([ViewSonicOnlineBinarySensor(entry.runtime_data)])


class ViewSonicOnlineBinarySensor(ViewSonicEntity, BinarySensorEntity):
    """Whether the projector is answering over RS-232.

    This is the one entity that must survive the projector going quiet, so it
    deliberately overrides the coordinator's availability handling -- an
    unavailable connectivity sensor tells you nothing.
    """

    _attr_name = "Responding"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        """Initialise the connectivity sensor."""
        super().__init__(coordinator, "online")

    @property
    def available(self) -> bool:
        """Always report; that is the point of this entity."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the last poll got an answer."""
        return self.coordinator.last_update_success
