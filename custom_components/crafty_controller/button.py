"""Server action buttons for Crafty Controller."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CraftyConfigEntry
from .api import CraftyError
from .const import (
    ACTION_BACKUP,
    ACTION_KILL,
    ACTION_RESTART,
    ACTION_START,
    ACTION_STOP,
    ACTION_UPDATE,
)
from .coordinator import CraftyCoordinator
from .entity import CraftyServerEntity, setup_dynamic_servers


@dataclass(frozen=True, kw_only=True)
class ServerButtonDescription(ButtonEntityDescription):
    action: str


DESCRIPTIONS: tuple[ServerButtonDescription, ...] = (
    ServerButtonDescription(key="start", action=ACTION_START),
    ServerButtonDescription(key="stop", action=ACTION_STOP),
    ServerButtonDescription(
        key="restart", action=ACTION_RESTART, device_class=ButtonDeviceClass.RESTART
    ),
    ServerButtonDescription(key="backup", action=ACTION_BACKUP),
    ServerButtonDescription(
        key="kill", action=ACTION_KILL, entity_registry_enabled_default=False,
        entity_category=EntityCategory.CONFIG,
    ),
    ServerButtonDescription(
        key="update_executable", action=ACTION_UPDATE, device_class=ButtonDeviceClass.UPDATE,
        entity_registry_enabled_default=False, entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: CraftyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def _factory(coord: CraftyCoordinator, sid: str):
        return [CraftyButton(coord, sid, d) for d in DESCRIPTIONS]

    entry.async_on_unload(
        setup_dynamic_servers(entry.runtime_data.coordinator, async_add_entities, _factory)
    )


class CraftyButton(CraftyServerEntity, ButtonEntity):
    entity_description: ServerButtonDescription

    def __init__(self, coordinator: CraftyCoordinator, sid: str, desc: ServerButtonDescription) -> None:
        super().__init__(coordinator, sid, desc.key)
        self.entity_description = desc

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_run_action(self.server_id, self.entity_description.action)
        except CraftyError as err:
            raise HomeAssistantError(f"Crafty could not {self.entity_description.key}: {err}") from err
