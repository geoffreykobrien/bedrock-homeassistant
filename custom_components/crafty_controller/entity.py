"""Base entities and dynamic-server helpers."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME
from .coordinator import CraftyCoordinator, ServerData


def hub_identifier(coordinator: CraftyCoordinator) -> tuple[str, str]:
    return (DOMAIN, coordinator.config_entry.entry_id)


def server_identifier(coordinator: CraftyCoordinator, server_id: str) -> tuple[str, str]:
    return (DOMAIN, f"{coordinator.config_entry.entry_id}_{server_id}")


class CraftyServerEntity(CoordinatorEntity[CraftyCoordinator]):
    """An entity that belongs to one Minecraft server."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CraftyCoordinator, server_id: str, key: str) -> None:
        super().__init__(coordinator)
        self.server_id = server_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{server_id}_{key}"
        server = self.server
        self._attr_device_info = DeviceInfo(
            identifiers={server_identifier(coordinator, server_id)},
            name=server.name if server else f"Minecraft {server_id}",
            manufacturer="Crafty Controller",
            model=("Minecraft Bedrock" if server and server.bedrock else "Minecraft Java"),
            sw_version=server.version if server else None,
            via_device=hub_identifier(coordinator),
            configuration_url=f"{coordinator.api.url}/panel/server_detail?id={server_id}",
        )

    @property
    def server(self) -> ServerData | None:
        data = self.coordinator.data
        return data.servers.get(self.server_id) if data else None

    @property
    def available(self) -> bool:
        server = self.server
        return super().available and server is not None and server.available


class CraftyHubEntity(CoordinatorEntity[CraftyCoordinator]):
    """An entity on the Crafty host device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CraftyCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_hub_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={hub_identifier(coordinator)},
            name=NAME,
            manufacturer="Crafty Controller",
            model="Crafty 4",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.api.url,
        )


def setup_dynamic_servers(
    coordinator: CraftyCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[CraftyCoordinator, str], Iterable[Entity]],
) -> Callable[[], None]:
    """Add entities for servers now, and again whenever a new server appears."""
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        if not coordinator.data:
            return
        new_ids = [sid for sid in coordinator.data.servers if sid not in known]
        if not new_ids:
            return
        known.update(new_ids)
        entities: list[Entity] = []
        for sid in new_ids:
            entities.extend(factory(coordinator, sid))
        async_add_entities(entities)

    _add_new()
    return coordinator.async_add_listener(_add_new)
