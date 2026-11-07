"""End-to-end tests against a mocked Crafty API."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry, async_fire_time_changed,
)

from custom_components.crafty_controller.const import (
    CONF_VERIFY_SSL, DOMAIN, EVENT_PLAYER_JOINED,
)

URL = "https://crafty.local:8443"
SID = "3f8a1c2e-0000-4000-8000-000000000001"
JID = "3f8a1c2e-0000-4000-8000-000000000002"

SERVER = {"server_id": SID, "server_name": "Bedrock Creative", "type": "minecraft-bedrock",
          "executable": "bedrock_server", "server_port": 19132}
JAVA = {"server_id": JID, "server_name": "Paper Survival", "type": "minecraft-java",
        "executable": "paper.jar", "server_port": 25565}


def stats(server, **kw):
    base = {"server_id": server, "running": True, "cpu": 4.2, "mem": "512.0MB",
            "mem_percent": 6.4, "world_name": "Bedrock level", "world_size": "1.5GB",
            "server_port": server["server_port"], "int_ping_results": "False", "online": 0,
            "max": 10, "players": "False", "version": "False", "started": "2026-11-07 17:10:12",
            "crashed": False, "updating": False}
    base.update(kw)
    return {"status": "ok", "data": base}


LOG = [
    "[2026-11-07 17:10:12:815 INFO] Starting Server",
    "[2026-11-07 17:10:12:815 INFO] Version: 1.26.63.1",
    "[2026-11-07 17:12:00:001 INFO] Player connected: Liam OB, xuid: 2535411111111111",
]


def mock_all(aioclient_mock, log=LOG, java_players="['Steve']"):
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/v2/servers", json={"status": "ok", "data": [SERVER, JAVA]})
    aioclient_mock.get(f"{URL}/api/v2/servers/{SID}/stats", json=stats(SERVER))
    aioclient_mock.get(f"{URL}/api/v2/servers/{JID}/stats",
                       json=stats(JAVA, int_ping_results="True", online=1, players=java_players,
                                  version="Paper 1.21.4"))
    aioclient_mock.get(f"{URL}/api/v2/servers/{SID}/logs", json={"status": "ok", "data": log})
    aioclient_mock.get(f"{URL}/metrics/host", text="# HELP\nCPU_Usage 12.5\nMem_Usage 63.8\n")
    aioclient_mock.post(f"{URL}/api/v2/servers/{SID}/action/start_server", json={"status": "ok"})
    aioclient_mock.post(f"{URL}/api/v2/servers/{SID}/action/stop_server", json={"status": "ok"})
    aioclient_mock.post(f"{URL}/api/v2/servers/{SID}/stdin", json={"status": "ok"})


async def setup(hass, aioclient_mock):
    mock_all(aioclient_mock)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=URL,
                            data={CONF_URL: URL, CONF_API_TOKEN: "tok", CONF_VERIFY_SSL: False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_user_flow(hass: HomeAssistant, aioclient_mock):
    mock_all(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.crafty_controller.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: "crafty.local:8443/panel/dashboard", CONF_API_TOKEN: "tok", CONF_VERIFY_SSL: False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_URL] == URL


async def test_user_flow_bad_token(hass, aioclient_mock):
    aioclient_mock.get(f"{URL}/api/v2/servers", status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_API_TOKEN: "bad", CONF_VERIFY_SSL: False})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_crafty_403(hass, aioclient_mock):
    """Crafty answers a bad token with 403 ACCESS_DENIED."""
    aioclient_mock.get(f"{URL}/api/v2/servers", status=403,
                       json={"status": "error", "error": "ACCESS_DENIED"})
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL, CONF_API_TOKEN: "bad", CONF_VERIFY_SSL: False})
    assert result["errors"] == {"base": "invalid_auth"}


async def test_missing_logs_permission(hass, aioclient_mock, caplog):
    mock_all(aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/v2/servers", json={"status": "ok", "data": [SERVER]})
    aioclient_mock.get(f"{URL}/api/v2/servers/{SID}/stats", json=stats(SERVER))
    aioclient_mock.get(f"{URL}/api/v2/servers/{SID}/logs", status=403,
                       json={"status": "error", "error": "NOT_AUTHORIZED"})
    aioclient_mock.get(f"{URL}/metrics/host", status=403)
    entry = MockConfigEntry(domain=DOMAIN, unique_id=URL,
                            data={CONF_URL: URL, CONF_API_TOKEN: "tok", CONF_VERIFY_SSL: False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.bedrock_creative_running").state == "on"
    assert hass.states.get("sensor.bedrock_creative_players_online").state == "0"
    assert "lacks the Logs permission" in caplog.text
    assert hass.states.get("sensor.crafty_controller_host_cpu").state == "unavailable"


async def test_entities_and_values(hass, aioclient_mock):
    await setup(hass, aioclient_mock)
    assert hass.states.get("binary_sensor.bedrock_creative_running").state == "on"
    players = hass.states.get("sensor.bedrock_creative_players_online")
    assert players.state == "1"
    assert players.attributes["players"] == ["Liam OB"]
    assert players.attributes["source"] == "logs"
    assert players.attributes["edition"] == "bedrock"
    assert hass.states.get("sensor.bedrock_creative_version").state == "1.26.63.1"
    assert float(hass.states.get("sensor.bedrock_creative_world_size").state) == pytest.approx(1536.0)
    assert hass.states.get("sensor.paper_survival_players_online").state == "1"
    assert hass.states.get("sensor.paper_survival_players_online").attributes["source"] == "crafty"
    assert hass.states.get("sensor.paper_survival_version").state == "Paper 1.21.4"
    assert hass.states.get("switch.bedrock_creative_server").state == "on"
    assert hass.states.get("sensor.crafty_controller_host_cpu").state == "12.5"
    devs = dr.async_get(hass)
    dev = next(d for d in devs.devices.values() if d.name == "Bedrock Creative")
    assert dev.model == "Minecraft Bedrock"


async def test_join_event(hass, aioclient_mock):
    await setup(hass, aioclient_mock)
    events = []
    hass.bus.async_listen(EVENT_PLAYER_JOINED, lambda e: events.append(e))
    mock_all(aioclient_mock, log=LOG + ["[2026-11-07 17:15:00:001 INFO] Player connected: Cool Kid, xuid: 2535422222222222"])
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done(wait_background_tasks=True)
    assert hass.states.get("sensor.bedrock_creative_players_online").state == "2"
    assert [e.data["player"] for e in events] == ["Cool Kid"]
    ev = hass.states.get("event.bedrock_creative_player_activity")
    assert ev.attributes["event_type"] == "joined"
    assert ev.attributes["player"] == "Cool Kid"


async def test_button_and_service(hass, aioclient_mock):
    await setup(hass, aioclient_mock)
    with patch("custom_components.crafty_controller.coordinator.asyncio.sleep"):
        await hass.services.async_call("button", "press", {"entity_id": "button.bedrock_creative_stop"}, blocking=True)
    assert any(str(c[1]).endswith("/action/stop_server") for c in aioclient_mock.mock_calls)
    devs = dr.async_get(hass)
    dev = next(d for d in devs.devices.values() if d.name == "Bedrock Creative")
    await hass.services.async_call(DOMAIN, "send_command", {"device_id": dev.id, "command": "/say hi"}, blocking=True)
    call = next(c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/stdin"))
    assert call[2] == b"say hi"


async def test_reconfigure_flow(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    new = "https://10.0.0.5:8443"
    aioclient_mock.get(f"{new}/api/v2/servers", json={"status": "ok", "data": []})
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    with patch("custom_components.crafty_controller.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_URL: new, CONF_VERIFY_SSL: False})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_URL] == new
    assert entry.data[CONF_API_TOKEN] == "tok"


async def test_reauth_on_401(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/v2/servers", status=401)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done(wait_background_tasks=True)
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"]["source"] == "reauth" for f in flows)


async def test_options_flow(hass, aioclient_mock):
    entry = await setup(hass, aioclient_mock)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 60, "player_source": "logs", "servers": [SID]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["servers"] == [SID]


async def test_card_served(hass, aioclient_mock, hass_client):
    await setup(hass, aioclient_mock)
    client = await hass_client()
    resp = await client.get("/crafty_controller_frontend/crafty-server-card.js")
    assert resp.status == 200
    assert "crafty-server-card" in await resp.text()
