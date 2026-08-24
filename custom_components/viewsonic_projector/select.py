"""Select entities for the ViewSonic Projector integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViewSonicConfigEntry
from .const import CONTROLS, Control, Kind
from .coordinator import ViewSonicCoordinator
from .entity import ControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViewSonicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up every multi-option setting in the command table."""
    coordinator = entry.runtime_data
    async_add_entities(
        ViewSonicSelect(coordinator, control)
        for control in CONTROLS
        if control.kind is Kind.SELECT
    )


class ViewSonicSelect(ControlEntity, SelectEntity):
    """A projector setting with a fixed list of options."""

    def __init__(self, coordinator: ViewSonicCoordinator, control: Control) -> None:
        """Initialise from a control definition."""
        super().__init__(coordinator, control)
        self._attr_options = list(control.options)

    @property
    def current_option(self) -> str | None:
        """Return the selected option, or None if the projector hasn't said."""
        return self.value

    @property
    def assumed_state(self) -> bool:
        """True where the projector accepts writes but refuses to report back."""
        return self.read_refused

    async def async_select_option(self, option: str) -> None:
        """Apply the chosen option."""
        assert self.control.option_cmd is not None
        await self.coordinator.async_write(
            self.control,
            self.control.option_cmd,
            self.control.options[option],
            optimistic=option,
        )
