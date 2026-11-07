"""The Crafty Controller integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN, CONF_URL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import CraftyApi, CraftyError
from .const import (
    ATTR_COMMAND,
    CARD_FILENAME,
    CARD_URL_BASE,
    CONF_VERIFY_SSL,
    DOMAIN,
    SERVICE_SEND_COMMAND,
    VERSION,
)
from .coordinator import CraftyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_DEVICE_ID = "device_id"
SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_COMMAND): cv.string,
    }
)


@dataclass
class CraftyRuntimeData:
    coordinator: CraftyCoordinator


type CraftyConfigEntry = ConfigEntry[CraftyRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the dashboard card and the send_command service once."""
    card_dir = Path(__file__).parent / "frontend"
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(card_dir), cache_headers=False)]
    )
    add_extra_js_url(hass, f"{CARD_URL_BASE}/{CARD_FILENAME}?v={VERSION}")

    async def _send_command(call: ServiceCall) -> None:
        command: str = call.data[ATTR_COMMAND]
        registry = dr.async_get(hass)
        for device_id in call.data[ATTR_DEVICE_ID]:
            coordinator, server_id = _resolve_device(hass, registry, device_id)
            try:
                await coordinator.api.async_send_command(server_id, command)
            except CraftyError as err:
                raise HomeAssistantError(f"Crafty rejected the command: {err}") from err

    hass.services.async_register(
        DOMAIN, SERVICE_SEND_COMMAND, _send_command, schema=SEND_COMMAND_SCHEMA
    )
    return True


def _resolve_device(
    hass: HomeAssistant, registry: dr.DeviceRegistry, device_id: str
) -> tuple[CraftyCoordinator, str]:
    device = registry.async_get(device_id)
    if device is None:
        raise ServiceValidationError(f"Unknown device {device_id}")
    for domain, ident in device.identifiers:
        if domain != DOMAIN or "_" not in ident:
            continue
        entry_id, server_id = ident.split("_", 1)
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or not hasattr(entry, "runtime_data"):
            continue
        return entry.runtime_data.coordinator, server_id
    raise ServiceValidationError(
        f"Device {device.name} is not a Crafty Minecraft server"
    )


async def async_setup_entry(hass: HomeAssistant, entry: CraftyConfigEntry) -> bool:
    session = async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, False))
    api = CraftyApi(session, entry.data[CONF_URL], entry.data[CONF_API_TOKEN])
    coordinator = CraftyCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = CraftyRuntimeData(coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: CraftyConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: CraftyConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: CraftyConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing devices for servers that no longer exist in Crafty."""
    coordinator = entry.runtime_data.coordinator
    live = {
        (DOMAIN, f"{entry.entry_id}_{sid}") for sid in (coordinator.data.servers if coordinator.data else {})
    }
    live.add((DOMAIN, entry.entry_id))
    return not (device.identifiers & live)
