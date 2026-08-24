"""Base entities for the ViewSonic Projector integration."""

from __future__ import annotations

from typing import Any

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, Control
from .coordinator import ViewSonicCoordinator


class ViewSonicEntity(CoordinatorEntity[ViewSonicCoordinator]):
    """Common device wiring for every ViewSonic entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ViewSonicCoordinator, unique_key: str) -> None:
        """Attach the entity to the projector device."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.host}_{coordinator.port}_{unique_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.host}:{coordinator.port}")},
            name=coordinator.name,
            manufacturer="ViewSonic",
            model="PJD7820HD",
            configuration_url=f"http://{coordinator.host}",
        )


class ControlEntity(ViewSonicEntity):
    """An entity backed by a row of the command table.

    Controls marked `primary` sit in the main device view; the rest are filed
    under config so that thirty-odd projector settings do not bury the handful
    anyone actually touches.
    """

    def __init__(
        self,
        coordinator: ViewSonicCoordinator,
        control: Control,
        *,
        key_suffix: str = "",
        name: str | None = None,
    ) -> None:
        """Initialise from a control definition."""
        super().__init__(coordinator, control.key + key_suffix)
        self.control = control
        self._attr_name = name or control.name
        self._attr_icon = control.icon

        if control.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        elif not control.primary:
            self._attr_entity_category = EntityCategory.CONFIG

    @property
    def value(self) -> Any:
        """The coordinator's current value for this control."""
        return self.coordinator.data.get(self.control.key)

    @property
    def read_refused(self) -> bool:
        """Whether the projector refuses to report this control's state."""
        return self.coordinator.is_read_refused(self.control)
