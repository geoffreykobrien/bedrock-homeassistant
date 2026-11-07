"""Constants for the Crafty Controller integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "crafty_controller"
NAME: Final = "Crafty Controller"
VERSION: Final = "0.2.0"

CONF_VERIFY_SSL: Final = "verify_ssl"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_PLAYER_SOURCE: Final = "player_source"
CONF_SERVERS: Final = "servers"

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600

PLAYER_SOURCE_AUTO: Final = "auto"
PLAYER_SOURCE_CRAFTY: Final = "crafty"
PLAYER_SOURCE_LOGS: Final = "logs"
PLAYER_SOURCES: Final = [PLAYER_SOURCE_AUTO, PLAYER_SOURCE_CRAFTY, PLAYER_SOURCE_LOGS]

EVENT_PLAYER_JOINED: Final = "crafty_controller_player_joined"
EVENT_PLAYER_LEFT: Final = "crafty_controller_player_left"

SERVICE_SEND_COMMAND: Final = "send_command"
ATTR_COMMAND: Final = "command"

CARD_FILENAME: Final = "crafty-server-card.js"
CARD_URL_BASE: Final = f"/{DOMAIN}_frontend"

ACTION_START: Final = "start_server"
ACTION_STOP: Final = "stop_server"
ACTION_RESTART: Final = "restart_server"
ACTION_KILL: Final = "kill_server"
ACTION_BACKUP: Final = "backup_server"
ACTION_UPDATE: Final = "update_executable"
