"""A power switch per server (on = start, off = graceful stop)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CraftyConfigEntry
from .api import CraftyError
from .const import ACTION_START, ACTION_STOP
from .coordinator import CraftyCoordinator
from .entity import CraftyServerEntity, setup_dynamic_servers


async def async_setup_entry(
    hass: HomeAssistant, entry: CraftyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry.async_on_unload(
        setup_dynamic_servers(
            entry.runtime_data.coordinator,
            async_add_entities,
            lambda coord, sid: [CraftyServerSwitch(coord, sid)],
        )
    )


class CraftyServerSwitch(CraftyServerEntity, SwitchEntity):
    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(self, coordinator: CraftyCoordinator, sid: str) -> None:
        super().__init__(coordinator, sid, "server")
        self._pending: bool | None = None

    @property
    def is_on(self) -> bool | None:
        if self._pending is not None:
            return self._pending
        server = self.server
        return server.running if server else None

    @callback
    def _handle_coordinator_update(self) -> None:
        server = self.server
        if self._pending is not None and server and server.running == self._pending:
            self._pending = None
        super()._handle_coordinator_update()

    async def _run(self, action: str, target: bool) -> None:
        try:
            await self.coordinator.async_run_action(self.server_id, action)
        except CraftyError as err:
            raise HomeAssistantError(f"Crafty error: {err}") from err
        server = self.server
        self._pending = None if server and server.running == target else target
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._run(ACTION_START, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._run(ACTION_STOP, False)
