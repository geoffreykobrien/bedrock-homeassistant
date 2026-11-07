"""Pure helpers for turning Crafty stats and server logs into clean values.

Kept free of Home Assistant imports so it can be unit tested in isolation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Any

# --- Bedrock Dedicated Server log lines -------------------------------------
# [2026-11-07 17:10:12:815 INFO] Player connected: Steve, xuid: 2535...
# [2026-11-07 17:20:00:001 INFO] Player disconnected: Steve, xuid: 2535..., pfid: ...
_BEDROCK_TS = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
_BEDROCK_JOIN = re.compile(r"Player connected: (?P<name>[^,]+), xuid: ?(?P<xuid>\d*)")
_BEDROCK_LEAVE = re.compile(r"Player disconnected: (?P<name>[^,]+), xuid")
_BEDROCK_START = re.compile(r"\] Starting Server\s*$")
_BEDROCK_VERSION = re.compile(r"\] Version: (?P<version>\d+(?:\.\d+)+)")

# --- Java (vanilla / Paper / Fabric ...) log lines ---------------------------
# [17:10:12] [Server thread/INFO]: Steve joined the game
_JAVA_NAME = r"(?P<name>\.?[A-Za-z0-9_\-]{1,32})"
_JAVA_JOIN = re.compile(rf"\]: {_JAVA_NAME} joined the game")
_JAVA_LEAVE = re.compile(rf"\]: {_JAVA_NAME} left the game")
_JAVA_START = re.compile(r"Starting minecraft server version (?P<version>\S+)")

_FALSY = {"", "false", "none", "null", "n/a"}


@dataclass
class Player:
    """A player currently online."""

    name: str
    joined: datetime | None = None
    xuid: str | None = None


@dataclass
class LogState:
    """Result of reading a server log."""

    players: dict[str, Player] = field(default_factory=dict)
    version: str | None = None


def parse_log(lines: list[str]) -> LogState:
    """Replay a full log from scratch."""
    state = LogState()
    apply_log_lines(state, lines)
    return state


def apply_log_lines(state: LogState, lines: list[str]) -> None:
    """Apply join/leave lines to `state` in order; a server start resets it."""
    for line in lines:
        if _BEDROCK_START.search(line):
            state.players.clear()
            continue
        if m := _JAVA_START.search(line):
            state.players.clear()
            state.version = m.group("version")
            continue
        if m := _BEDROCK_VERSION.search(line):
            state.version = m.group("version")
            continue
        if m := _BEDROCK_JOIN.search(line):
            name = m.group("name").strip()
            state.players[name.lower()] = Player(
                name=name, joined=_bedrock_time(line), xuid=m.group("xuid") or None
            )
            continue
        if m := _BEDROCK_LEAVE.search(line):
            state.players.pop(m.group("name").strip().lower(), None)
            continue
        if m := _JAVA_JOIN.search(line):
            name = m.group("name")
            state.players[name.lower()] = Player(name=name)
            continue
        if m := _JAVA_LEAVE.search(line):
            state.players.pop(m.group("name").lower(), None)


def _bedrock_time(line: str) -> datetime | None:
    if m := _BEDROCK_TS.search(line):
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    return None


def is_bedrock(server: dict[str, Any]) -> bool:
    """Best-effort check of a Crafty server object for Bedrock."""
    blob = " ".join(
        str(server.get(key, "")) for key in ("type", "executable", "execution_command")
    ).lower()
    return "bedrock" in blob or "bedrock_server" in blob


def clean_str(value: Any) -> str | None:
    """Crafty uses the string 'False' for 'no value' in many fields."""
    if value is None or value is False:
        return None
    text = str(value).strip()
    return None if text.lower() in _FALSY else text


def to_float(value: Any) -> float | None:
    text = clean_str(value)
    if text is None:
        return None
    try:
        return float(text.rstrip("%"))
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    number = to_float(value)
    return None if number is None else int(number)


_SIZE = re.compile(r"^\s*([\d.]+)\s*([KMGTP]?i?B?)\s*$", re.IGNORECASE)
_SIZE_MULT = {"": 1, "B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "P": 1024**5}


def size_to_mib(value: Any) -> float | None:
    """'42.2MB' / '1.3GB' / '512KB' -> MiB (Crafty uses 1024-based units)."""
    text = clean_str(value)
    if text is None:
        return None
    m = _SIZE.match(text)
    if not m:
        return None
    unit = m.group(2).upper().replace("I", "").rstrip("B") or "B"
    if unit == "B" and m.group(2).upper() not in ("", "B"):
        unit = "B"
    try:
        size = float(m.group(1)) * _SIZE_MULT.get(unit, 1)
    except ValueError:
        return None
    return round(size / 1024**2, 2)


def parse_started(value: Any) -> datetime | None:
    """Crafty reports `started` as 'False' or 'YYYY-MM-DD HH:MM:SS' (naive)."""
    text = clean_str(value)
    if text is None:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def parse_crafty_players(value: Any) -> list[str]:
    """Crafty's `players` stat is a stringified Python/JSON list of names."""
    if isinstance(value, list):
        raw = value
    else:
        text = clean_str(value)
        if text is None:
            return []
        try:
            raw = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return []
    if not isinstance(raw, (list, tuple)):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            item = item.get("name")
        if item:
            names.append(str(item))
    return names
