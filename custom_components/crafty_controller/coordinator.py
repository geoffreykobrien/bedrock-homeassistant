"""Data update coordinator for Crafty Controller."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    CraftyApi,
    CraftyAuthError,
    CraftyConnectionError,
    CraftyError,
    CraftyPermissionError,
)
from .const import (
    CONF_PLAYER_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_SERVERS,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    EVENT_PLAYER_JOINED,
    EVENT_PLAYER_LEFT,
    PLAYER_SOURCE_AUTO,
    PLAYER_SOURCE_CRAFTY,
    PLAYER_SOURCE_LOGS,
)
from .parsing import (
    Player,
    clean_str,
    is_bedrock,
    parse_crafty_players,
    parse_log,
    to_int,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class ServerData:
    """Everything known about one Crafty server after a refresh."""

    server_id: str
    info: dict[str, Any]
    stats: dict[str, Any]
    bedrock: bool
    players: dict[str, Player] = field(default_factory=dict)
    player_source: str = PLAYER_SOURCE_CRAFTY
    version: str | None = None
    available: bool = True

    @property
    def name(self) -> str:
        return str(self.info.get("server_name") or f"Server {self.server_id}")

    @property
    def running(self) -> bool:
        return bool(self.stats.get("running"))

    @property
    def max_players(self) -> int | None:
        return to_int(self.stats.get("max"))


@dataclass
class CraftyData:
    servers: dict[str, ServerData] = field(default_factory=dict)
    host: dict[str, float] = field(default_factory=dict)


@dataclass
class PlayerEvent:
    server_id: str
    event_type: str  # "joined" | "left"
    player: str


class CraftyCoordinator(DataUpdateCoordinator[CraftyData]):
    """Polls Crafty for server list, stats and (optionally) logs."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: CraftyApi) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=interval),
        )
        self.api = api
        self._versions: dict[str, str] = {}
        self._host_supported = True
        self._first = True
        self.pending_events: list[PlayerEvent] = []

    @property
    def player_source_option(self) -> str:
        return self.config_entry.options.get(CONF_PLAYER_SOURCE, PLAYER_SOURCE_AUTO)

    @property
    def selected_servers(self) -> list[str]:
        return [str(s) for s in self.config_entry.options.get(CONF_SERVERS, [])]

    async def _async_update_data(self) -> CraftyData:
        try:
            servers = await self.api.async_get_servers()
        except CraftyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CraftyError as err:
            raise UpdateFailed(str(err)) from err

        wanted = set(self.selected_servers)
        servers = [
            s for s in servers
            if s.get("server_id") is not None and (not wanted or str(s["server_id"]) in wanted)
        ]

        results = await asyncio.gather(
            *(self._async_update_server(s) for s in servers), return_exceptions=True
        )
        data = CraftyData()
        for server, result in zip(servers, results, strict=True):
            if isinstance(result, ConfigEntryAuthFailed):
                raise result
            if isinstance(result, BaseException):
                _LOGGER.debug("Update failed for %s: %s", server.get("server_name"), result)
                sid = str(server["server_id"])
                prev = self.data.servers.get(sid) if self.data else None
                data.servers[sid] = ServerData(
                    server_id=sid, info=server, stats=prev.stats if prev else {},
                    bedrock=is_bedrock(server), available=False,
                )
                continue
            data.servers[result.server_id] = result

        if self._host_supported:
            try:
                data.host = await self.api.async_get_host_metrics()
            except CraftyPermissionError:
                self._host_supported = False
            except CraftyError as err:
                _LOGGER.debug("Host metrics unavailable: %s", err)
                if self.data:
                    data.host = self.data.host

        self._diff_players(data)
        self._first = False
        return data

    async def _async_update_server(self, server: dict[str, Any]) -> ServerData:
        sid = str(server["server_id"])
        try:
            stats = await self.api.async_get_stats(sid)
        except CraftyAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err

        # Stats embed the full server object under "server_id"; prefer it.
        info = stats.get("server_id") if isinstance(stats.get("server_id"), dict) else server
        info = {**server, **info}
        bedrock = is_bedrock(info)
        result = ServerData(server_id=sid, info=info, stats=stats, bedrock=bedrock)

        source = self.player_source_option
        if source == PLAYER_SOURCE_AUTO:
            ping_ok = stats.get("int_ping_results") not in (None, False, "False", "")
            source = PLAYER_SOURCE_LOGS if (bedrock or not ping_ok) else PLAYER_SOURCE_CRAFTY
        result.player_source = source

        log_version: str | None = None
        if result.running:
            if source == PLAYER_SOURCE_LOGS:
                try:
                    log = parse_log(await self.api.async_get_logs(sid, from_file=True))
                    result.players = log.players
                    log_version = log.version
                except CraftyAuthError as err:
                    raise ConfigEntryAuthFailed(str(err)) from err
                except CraftyError as err:
                    _LOGGER.debug("Log read failed for %s: %s", sid, err)
                    if self.data and sid in self.data.servers:
                        result.players = self.data.servers[sid].players
            else:
                now = dt_util.now().replace(tzinfo=None)
                prev = self.data.servers.get(sid) if self.data else None
                for name in parse_crafty_players(stats.get("players")):
                    key = name.lower()
                    joined = prev.players[key].joined if prev and key in prev.players else now
                    result.players[key] = Player(name=name, joined=joined)

        version = clean_str(stats.get("version")) or log_version or self._versions.get(sid)
        if version:
            self._versions[sid] = version
        result.version = version
        return result

    @callback
    def _diff_players(self, new: CraftyData) -> None:
        self.pending_events = []  # drop anything no entity consumed last cycle
        if self._first or self.data is None:
            return
        for sid, server in new.servers.items():
            old = self.data.servers.get(sid)
            if old is None or not server.available:
                continue
            before, after = set(old.players), set(server.players)
            for key in sorted(after - before):
                self._emit(sid, server.name, "joined", server.players[key].name)
            for key in sorted(before - after):
                self._emit(sid, server.name, "left", old.players[key].name)

    @callback
    def _emit(self, sid: str, server_name: str, event_type: str, player: str) -> None:
        self.pending_events.append(PlayerEvent(sid, event_type, player))
        self.hass.bus.async_fire(
            EVENT_PLAYER_JOINED if event_type == "joined" else EVENT_PLAYER_LEFT,
            {"server_id": sid, "server_name": server_name, "player": player},
        )

    def pop_events(self, server_id: str) -> list[PlayerEvent]:
        mine = [e for e in self.pending_events if e.server_id == server_id]
        self.pending_events = [e for e in self.pending_events if e.server_id != server_id]
        return mine

    async def async_run_action(self, server_id: str, action: str) -> None:
        await self.api.async_action(server_id, action)
        await asyncio.sleep(1)
        await self.async_request_refresh()


def player_since(player: Player) -> datetime | None:
    if player.joined is None:
        return None
    return player.joined.replace(tzinfo=dt_util.get_default_time_zone())
