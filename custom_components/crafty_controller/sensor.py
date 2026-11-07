"""Sensors for Crafty Controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import CraftyConfigEntry
from .coordinator import CraftyCoordinator, Player, ServerData, player_since
from .entity import CraftyHubEntity, CraftyServerEntity, setup_dynamic_servers
from .parsing import clean_str, parse_started, size_to_mib, to_float, to_int


@dataclass(frozen=True, kw_only=True)
class ServerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ServerData], Any]


def _started(server: ServerData) -> datetime | None:
    if not server.running:
        return None
    started = parse_started(server.stats.get("started"))
    return started.replace(tzinfo=dt_util.get_default_time_zone()) if started else None


SERVER_SENSORS: tuple[ServerSensorDescription, ...] = (
    ServerSensorDescription(
        key="players_online",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="players",
        value_fn=lambda s: len(s.players) if s.running else 0,
    ),
    ServerSensorDescription(
        key="version",
        value_fn=lambda s: s.version,
    ),
    ServerSensorDescription(
        key="started",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_started,
    ),
    ServerSensorDescription(
        key="cpu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: to_float(s.stats.get("cpu")) if s.running else 0,
    ),
    ServerSensorDescription(
        key="memory",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda s: size_to_mib(s.stats.get("mem")) if s.running else 0,
    ),
    ServerSensorDescription(
        key="memory_percent",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda s: to_float(s.stats.get("mem_percent")) if s.running else 0,
    ),
    ServerSensorDescription(
        key="world_size",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        suggested_display_precision=1,
        value_fn=lambda s: size_to_mib(s.stats.get("world_size")),
    ),
    ServerSensorDescription(
        key="world_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: clean_str(s.stats.get("world_name")),
    ),
    ServerSensorDescription(
        key="port",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: to_int(s.stats.get("server_port") or s.info.get("server_port")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: CraftyConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data.coordinator

    def _factory(coord: CraftyCoordinator, sid: str):
        return [CraftyServerSensor(coord, sid, desc) for desc in SERVER_SENSORS]

    entry.async_on_unload(setup_dynamic_servers(coordinator, async_add_entities, _factory))
    async_add_entities(
        [CraftyTotalPlayersSensor(coordinator),
         CraftyHostSensor(coordinator, "host_cpu", "CPU_Usage"),
         CraftyHostSensor(coordinator, "host_memory", "Mem_Usage")]
    )


def _player_dict(player: Player) -> dict[str, Any]:
    since = player_since(player)
    return {
        "name": player.name,
        "since": since.isoformat() if since else None,
        **({"xuid": player.xuid} if player.xuid else {}),
    }


def _sorted_players(server: ServerData) -> list[Player]:
    if not server.running:
        return []
    return sorted(server.players.values(), key=lambda p: p.name.lower())


class CraftyServerSensor(CraftyServerEntity, SensorEntity):
    entity_description: ServerSensorDescription

    def __init__(self, coordinator: CraftyCoordinator, sid: str, desc: ServerSensorDescription) -> None:
        super().__init__(coordinator, sid, desc.key)
        self.entity_description = desc

    @property
    def native_value(self) -> Any:
        server = self.server
        return self.entity_description.value_fn(server) if server else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        server = self.server
        if server is None or self.entity_description.key != "players_online":
            return None
        players = _sorted_players(server)
        return {
            "players": [p.name for p in players],
            "player_details": [_player_dict(p) for p in players],
            "max_players": server.max_players,
            "source": server.player_source,
            "edition": "bedrock" if server.bedrock else "java",
        }


class CraftyHostSensor(CraftyHubEntity, SensorEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: CraftyCoordinator, key: str, metric: str) -> None:
        super().__init__(coordinator, key)
        self._metric = metric

    @property
    def available(self) -> bool:
        return super().available and self._metric in (self.coordinator.data.host if self.coordinator.data else {})

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.host.get(self._metric) if self.coordinator.data else None


class CraftyTotalPlayersSensor(CraftyHubEntity, SensorEntity):
    """Players online across every server, with a per-server breakdown."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "players"

    def __init__(self, coordinator: CraftyCoordinator) -> None:
        super().__init__(coordinator, "players_total")

    def _servers(self) -> list[ServerData]:
        data = self.coordinator.data
        if not data:
            return []
        return sorted(
            (s for s in data.servers.values() if s.available),
            key=lambda s: s.name.lower(),
        )

    @property
    def native_value(self) -> int:
        return sum(len(_sorted_players(s)) for s in self._servers())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        servers = self._servers()
        return {
            "servers": [
                {
                    "server_id": s.server_id,
                    "name": s.name,
                    "running": s.running,
                    "edition": "bedrock" if s.bedrock else "java",
                    "count": len(players := _sorted_players(s)),
                    "players": [_player_dict(p) for p in players],
                }
                for s in servers
            ],
            "players": sorted(
                {p.name for s in servers for p in _sorted_players(s)}, key=str.lower
            ),
            "servers_with_players": sum(1 for s in servers if _sorted_players(s)),
        }
