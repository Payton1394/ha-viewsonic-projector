"""Button entities for the ViewSonic Projector integration.

Two kinds live here: one-shot actions, and the up/down pairs for settings the
projector only exposes as increment and decrement. Those have no absolute
"set to 42" command in the protocol -- the only way to move contrast is to nudge
it -- so a pair of buttons is an honest representation. The current value is
published alongside as a sensor.
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up action buttons and step pairs."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = []

    for control in CONTROLS:
        if control.kind is Kind.EXECUTE:
            entities.append(ViewSonicActionButton(coordinator, control))
        elif control.kind is Kind.STEP:
            entities.append(ViewSonicStepButton(coordinator, control, up=True))
            entities.append(ViewSonicStepButton(coordinator, control, up=False))

    async_add_entities(entities)


class ViewSonicActionButton(ControlEntity, ButtonEntity):
    """A one-shot projector action."""

    def __init__(self, coordinator: ViewSonicCoordinator, control: Control) -> None:
        """Initialise from a control definition."""
        super().__init__(coordinator, control)

    async def async_press(self) -> None:
        """Fire the action."""
        assert self.control.execute is not None
        cmd, value = self.control.execute
        await self.coordinator.async_write(self.control, cmd, value)


class ViewSonicStepButton(ControlEntity, ButtonEntity):
    """One direction of an increment/decrement setting."""

    def __init__(
        self, coordinator: ViewSonicCoordinator, control: Control, *, up: bool
    ) -> None:
        """Initialise one half of a step pair."""
        direction = "up" if up else "down"
        super().__init__(
            coordinator,
            control,
            key_suffix=f"_{direction}",
            name=f"{control.name} {direction}",
        )
        self._up = up
        self._attr_icon = "mdi:plus" if up else "mdi:minus"

    async def async_press(self) -> None:
        """Nudge the setting one step."""
        step = self.control.up if self._up else self.control.down
        assert step is not None
        cmd, value = step
        await self.coordinator.async_write(self.control, cmd, value)
