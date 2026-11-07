from custom_components.crafty_controller.parsing import (
    parse_crafty_players, parse_log, parse_started, size_to_mib, to_float,
)

BEDROCK = """[2026-11-07 17:10:12:815 INFO] Starting Server
[2026-11-07 17:10:12:815 INFO] Version: 1.26.63.1
[2026-11-07 17:12:00:001 INFO] Player connected: Liam OB, xuid: 2535411111111111
[2026-11-07 17:12:30:001 INFO] Player connected: Cool Kid, xuid: 2535422222222222
[2026-11-07 17:12:31:001 INFO] Player Spawned: Cool Kid xuid: 2535422222222222, pfid: abc
[2026-11-07 17:20:00:001 INFO] Player disconnected: Cool Kid, xuid: 2535422222222222, pfid: abc""".splitlines()


def test_bedrock_log():
    state = parse_log(BEDROCK)
    assert state.version == "1.26.63.1"
    assert [p.name for p in state.players.values()] == ["Liam OB"]
    p = state.players["liam ob"]
    assert p.xuid == "2535411111111111"
    assert p.joined.hour == 17 and p.joined.minute == 12


def test_restart_resets():
    lines = BEDROCK + ["[2026-11-07 18:00:00:000 INFO] Starting Server"]
    assert parse_log(lines).players == {}


def test_java_log():
    lines = [
        "[17:00:00] [Server thread/INFO]: Starting minecraft server version 1.21.4",
        "[17:01:00] [Server thread/INFO]: Steve joined the game",
        "[17:02:00] [Server thread/INFO]: .BedrockKid joined the game",
        "[17:03:00] [Server thread/INFO]: Steve left the game",
    ]
    state = parse_log(lines)
    assert state.version == "1.21.4"
    assert [p.name for p in state.players.values()] == [".BedrockKid"]


def test_helpers():
    assert size_to_mib("42.5MB") == 42.5
    assert size_to_mib("1.5GB") == 1536.0
    assert size_to_mib("512KB") == 0.5
    assert size_to_mib("False") is None
    assert to_float("False") is None
    assert to_float("3.5") == 3.5
    assert parse_started("False") is None
    assert parse_started("2026-11-07 17:10:12").minute == 10
    assert parse_crafty_players("['Steve', 'Alex']") == ["Steve", "Alex"]
    assert parse_crafty_players("[]") == []
    assert parse_crafty_players("False") == []
