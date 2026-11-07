"""Diagnostics for Crafty Controller."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN
from homeassistant.core import HomeAssistant

from . import CraftyConfigEntry

TO_REDACT = {CONF_API_TOKEN, "xuid", "execution_command", "path", "backup_path", "log_path"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CraftyConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data.coordinator
    data = coordinator.data
    servers: dict[str, Any] = {}
    if data:
        for sid, server in data.servers.items():
            servers[sid] = {
                "name": server.name,
                "bedrock": server.bedrock,
                "available": server.available,
                "player_source": server.player_source,
                "version": server.version,
                "players": [asdict(p) for p in server.players.values()],
                "stats": server.stats,
            }
    return async_redact_data(
        {
            "entry": {"data": dict(entry.data), "options": dict(entry.options)},
            "last_update_success": coordinator.last_update_success,
            "host": data.host if data else None,
            "servers": servers,
        },
        TO_REDACT,
    )
