"""Player join/leave event entity per server."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CraftyConfigEntry
from .coordinator import CraftyCoordinator
from .entity import CraftyServerEntity, setup_dynamic_servers


async def async_setup_entry(
    hass: HomeAssistant, entry: CraftyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry.async_on_unload(
        setup_dynamic_servers(
            entry.runtime_data.coordinator,
            async_add_entities,
            lambda coord, sid: [CraftyPlayerEvent(coord, sid)],
        )
    )


class CraftyPlayerEvent(CraftyServerEntity, EventEntity):
    _attr_event_types = ["joined", "left"]

    def __init__(self, coordinator: CraftyCoordinator, sid: str) -> None:
        super().__init__(coordinator, sid, "player_activity")

    @callback
    def _handle_coordinator_update(self) -> None:
        for event in self.coordinator.pop_events(self.server_id):
            self._trigger_event(event.event_type, {"player": event.player})
        super()._handle_coordinator_update()
