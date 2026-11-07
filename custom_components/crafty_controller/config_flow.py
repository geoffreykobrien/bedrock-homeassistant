"""Config, reconfigure, reauth and options flows for Crafty Controller."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    CraftyApi,
    CraftyAuthError,
    CraftyConnectionError,
    CraftyError,
    normalize_url,
)
from .const import (
    CONF_PLAYER_SOURCE,
    CONF_SCAN_INTERVAL,
    CONF_SERVERS,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    NAME,
    PLAYER_SOURCE_AUTO,
    PLAYER_SOURCES,
)

_LOGGER = logging.getLogger(__name__)

_TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))


def _connection_schema(defaults: Mapping[str, Any], *, include_token: bool = True) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(CONF_URL, default=defaults.get(CONF_URL, "https://")): _URL_SELECTOR,
    }
    if include_token:
        fields[vol.Required(CONF_API_TOKEN, default=defaults.get(CONF_API_TOKEN, ""))] = (
            _TOKEN_SELECTOR
        )
    fields[vol.Required(CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False))] = (
        BooleanSelector()
    )
    return vol.Schema(fields)


async def _validate(hass: HomeAssistant, url: str, token: str, verify_ssl: bool) -> int:
    """Return number of servers visible to the token; raise on failure."""
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)
    api = CraftyApi(session, url, token)
    servers = await api.async_get_servers()
    return len(servers)


async def _check(
    hass: HomeAssistant, user_input: dict[str, Any], errors: dict[str, str]
) -> int | None:
    try:
        return await _validate(
            hass,
            user_input[CONF_URL],
            user_input[CONF_API_TOKEN],
            user_input.get(CONF_VERIFY_SSL, False),
        )
    except CraftyAuthError:
        errors["base"] = "invalid_auth"
    except CraftyConnectionError as err:
        _LOGGER.debug("Connection failed: %s", err)
        errors["base"] = "ssl_error" if "ssl" in str(err).lower() or "certificate" in str(err).lower() else "cannot_connect"
    except CraftyError as err:
        _LOGGER.debug("Unexpected Crafty response: %s", err)
        errors["base"] = "not_crafty"
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error validating Crafty")
        errors["base"] = "unknown"
    return None


class CraftyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Crafty Controller."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = normalize_url(user_input[CONF_URL])
            await self.async_set_unique_id(user_input[CONF_URL].lower())
            self._abort_if_unique_id_configured()
            count = await _check(self.hass, user_input, errors)
            if count is not None:
                host = user_input[CONF_URL].split("://", 1)[-1]
                return self.async_create_entry(title=f"{NAME} ({host})", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _connection_schema({}), user_input or {}
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_URL] = normalize_url(user_input[CONF_URL])
            if not user_input.get(CONF_API_TOKEN):
                user_input[CONF_API_TOKEN] = entry.data[CONF_API_TOKEN]
            if await _check(self.hass, user_input, errors) is not None:
                host = user_input[CONF_URL].split("://", 1)[-1]
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=user_input[CONF_URL].lower(),
                    title=f"{NAME} ({host})",
                    data_updates=user_input,
                )
        defaults = {**entry.data, CONF_API_TOKEN: ""}
        schema = vol.Schema(
            {
                vol.Required(CONF_URL, default=defaults[CONF_URL]): _URL_SELECTOR,
                vol.Optional(CONF_API_TOKEN): _TOKEN_SELECTOR,
                vol.Required(
                    CONF_VERIFY_SSL, default=defaults.get(CONF_VERIFY_SSL, False)
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {**entry.data, CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
            if await _check(self.hass, candidate, errors) is not None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_TOKEN: user_input[CONF_API_TOKEN]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): _TOKEN_SELECTOR}),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return CraftyOptionsFlow()


class CraftyOptionsFlow(OptionsFlow):
    """Polling interval, player tracking source and server selection."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            user_input[CONF_SCAN_INTERVAL] = int(user_input[CONF_SCAN_INTERVAL])
            return self.async_create_entry(data=user_input)

        server_options: list[SelectOptionDict] = []
        runtime = getattr(self.config_entry, "runtime_data", None)
        if runtime and runtime.coordinator.data:
            # Show every server Crafty knows about, not just the selected ones.
            try:
                all_servers = await runtime.coordinator.api.async_get_servers()
            except CraftyError:
                all_servers = [s.info for s in runtime.coordinator.data.servers.values()]
            server_options = [
                SelectOptionDict(value=str(s["server_id"]), label=str(s.get("server_name", s["server_id"])))
                for s in all_servers
                if s.get("server_id") is not None
            ]

        opts = self.config_entry.options
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=5,
                    unit_of_measurement="s", mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_PLAYER_SOURCE, default=opts.get(CONF_PLAYER_SOURCE, PLAYER_SOURCE_AUTO)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=PLAYER_SOURCES,
                    translation_key=CONF_PLAYER_SOURCE,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
        if server_options:
            schema[vol.Optional(CONF_SERVERS, default=opts.get(CONF_SERVERS, []))] = SelectSelector(
                SelectSelectorConfig(options=server_options, multiple=True, mode=SelectSelectorMode.LIST)
            )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
