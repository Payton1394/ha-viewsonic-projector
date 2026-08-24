"""Switch entities for the ViewSonic Projector integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ViewSonicConfigEntry
from .const import CONTROLS, POWER, Control, Kind
from .coordinator import ViewSonicCoordinator
from .entity import ControlEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ViewSonicConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up every switch in the command table."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [ViewSonicPowerSwitch(coordinator)]
    entities.extend(
        ViewSonicSwitch(coordinator, control)
        for control in CONTROLS
        if control.kind is Kind.SWITCH
    )
    async_add_entities(entities)


class ViewSonicPowerSwitch(ControlEntity, SwitchEntity):
    """Lamp power.

    Kept separate from the generic switch because power is the one control
    whose on and off differ in the command byte rather than the value, and
    because it needs the coordinator's warm-up grace handling.
    """

    def __init__(self, coordinator: ViewSonicCoordinator) -> None:
        """Initialise the power switch."""
        super().__init__(coordinator, POWER)

    @property
    def is_on(self) -> bool | None:
        """Return whether the lamp is on."""
        return self.value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the projector on."""
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the projector off."""
        await self.coordinator.async_set_power(False)


class ViewSonicSwitch(ControlEntity, SwitchEntity):
    """A plain on/off projector setting."""

    def __init__(self, coordinator: ViewSonicCoordinator, control: Control) -> None:
        """Initialise from a control definition."""
        super().__init__(coordinator, control)

    @property
    def is_on(self) -> bool | None:
        """Return the setting's current state."""
        return self.value

    @property
    def assumed_state(self) -> bool:
        """True where the projector accepts writes but refuses to report back.

        Home Assistant then shows separate on and off controls rather than a
        toggle reflecting a state it cannot actually verify.
        """
        return self.read_refused

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the setting."""
        assert self.control.on is not None
        cmd, value = self.control.on
        await self.coordinator.async_write(self.control, cmd, value, optimistic=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the setting."""
        assert self.control.off is not None
        cmd, value = self.control.off
        await self.coordinator.async_write(self.control, cmd, value, optimistic=False)
