"""Sensor entities for the ViewSonic Projector integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViewSonicConfigEntry
from .const import CONTROLS, KEY_ERROR_STATUS, KEY_LAMP_HOURS, Control, Kind
from .coordinator import ViewSonicCoordinator
from .entity import ControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViewSonicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up value sensors for readable controls."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    for control in CONTROLS:
        if control.key == KEY_LAMP_HOURS:
            entities.append(ViewSonicLampHoursSensor(coordinator, control))
        elif control.key == KEY_ERROR_STATUS:
            entities.append(ViewSonicErrorStatusSensor(coordinator, control))
        elif control.kind is Kind.STEP:
            # The readback for an increment/decrement setting.
            entities.append(ViewSonicValueSensor(coordinator, control))

    async_add_entities(entities)


class ViewSonicValueSensor(ControlEntity, SensorEntity):
    """Current value of a stepped setting."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: ViewSonicCoordinator, control: Control) -> None:
        """Initialise from a control definition."""
        super().__init__(coordinator, control, key_suffix="_value")
        # Overrides the CONFIG category ControlEntity would otherwise apply:
        # this is a readback, not something you set.
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Hide the readback when the projector refuses to provide one.

        Unlike the switches and selects, a sensor has nothing useful to offer
        if it can never be read -- reporting "unavailable" is honest, where a
        permanent "unknown" just looks broken.
        """
        return super().available and not (self.read_refused and self.value is None)

    @property
    def native_value(self) -> int | None:
        """Return the setting's current numeric value."""
        return self.value


class ViewSonicLampHoursSensor(ControlEntity, SensorEntity):
    """Hours the lamp has run, as counted by the projector."""

    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: ViewSonicCoordinator, control: Control) -> None:
        """Initialise the lamp hours sensor."""
        super().__init__(coordinator, control)

    @property
    def native_value(self) -> int | None:
        """Return the lamp hour count."""
        return self.value


class ViewSonicErrorStatusSensor(ControlEntity, SensorEntity):
    """Raw error-status block.

    The projector returns a 29-byte structure here and the user guide documents
    only the query, never the layout. Rather than invent a decoding, the bytes
    are surfaced verbatim so they can be compared against observed faults.
    """

    def __init__(self, coordinator: ViewSonicCoordinator, control: Control) -> None:
        """Initialise the error status sensor."""
        super().__init__(coordinator, control)

    @property
    def native_value(self) -> str | None:
        """Return the status block as spaced hex."""
        value = self.value
        if value is None:
            return None
        # Sensor states cap at 255 characters.
        return value[:255]
