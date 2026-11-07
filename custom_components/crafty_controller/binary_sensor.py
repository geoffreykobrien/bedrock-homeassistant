"""Binary sensors for Crafty Controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import CraftyConfigEntry
from .coordinator import CraftyCoordinator, ServerData
from .entity import CraftyServerEntity, setup_dynamic_servers


@dataclass(frozen=True, kw_only=True)
class ServerBinaryDescription(BinarySensorEntityDescription):
    value_fn: Callable[[ServerData], bool]


DESCRIPTIONS: tuple[ServerBinaryDescription, ...] = (
    ServerBinaryDescription(
        key="running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda s: s.running,
    ),
    ServerBinaryDescription(
        key="crashed",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: bool(s.stats.get("crashed")),
    ),
    ServerBinaryDescription(
        key="updating",
        device_class=BinarySensorDeviceClass.UPDATE,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: bool(s.stats.get("updating")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: CraftyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    def _factory(coord: CraftyCoordinator, sid: str):
        return [CraftyBinarySensor(coord, sid, d) for d in DESCRIPTIONS]

    entry.async_on_unload(
        setup_dynamic_servers(entry.runtime_data.coordinator, async_add_entities, _factory)
    )


class CraftyBinarySensor(CraftyServerEntity, BinarySensorEntity):
    entity_description: ServerBinaryDescription

    def __init__(self, coordinator: CraftyCoordinator, sid: str, desc: ServerBinaryDescription) -> None:
        super().__init__(coordinator, sid, desc.key)
        self.entity_description = desc

    @property
    def is_on(self) -> bool | None:
        server = self.server
        return self.entity_description.value_fn(server) if server else None
