"""Async client for the Crafty Controller 4 API (v2)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

REQUEST_TIMEOUT = 15


class CraftyError(Exception):
    """Generic Crafty API error."""


class CraftyConnectionError(CraftyError):
    """Crafty could not be reached."""


class CraftyAuthError(CraftyError):
    """The API token was rejected."""


class CraftyPermissionError(CraftyError):
    """The token is valid but lacks permission for this call."""


class CraftyApi:
    """Thin wrapper around the Crafty Controller v2 REST API."""

    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self._url = normalize_url(url)
        self._token = token

    @property
    def url(self) -> str:
        return self._url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        data: str | None = None,
        expect_json: bool = True,
    ) -> Any:
        headers = {"Authorization": f"Bearer {self._token}"}
        if data is not None:
            headers["Content-Type"] = "text/plain"
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                resp = await self._session.request(
                    method,
                    f"{self._url}{path}",
                    params=params,
                    data=data.encode() if data is not None else None,
                    headers=headers,
                )
                if resp.status == 401:
                    raise CraftyAuthError("Crafty rejected the API token")
                if resp.status == 403:
                    raise CraftyPermissionError(f"No permission for {path}")
                if not expect_json:
                    if resp.status >= 400:
                        raise CraftyError(f"HTTP {resp.status} for {path}")
                    return await resp.text()
                try:
                    payload = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise CraftyError(
                        f"Unexpected response from {path} (HTTP {resp.status})"
                    ) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise CraftyConnectionError(f"Cannot reach Crafty at {self._url}: {err}") from err

        if not isinstance(payload, dict):
            raise CraftyError(f"Unexpected payload from {path}")
        if payload.get("status") != "ok":
            error = payload.get("error") or payload.get("error_data") or resp.status
            if str(error).upper() in {"ACCESS_DENIED", "NOT_AUTHORIZED", "INVALID_TOKEN"}:
                raise CraftyPermissionError(f"{error} on {path}")
            raise CraftyError(f"Crafty error on {path}: {error}")
        return payload.get("data")

    async def async_get_servers(self) -> list[dict[str, Any]]:
        # Crafty answers a bad/expired token with 403 ACCESS_DENIED rather than
        # 401, so a denial on the most basic call means the token itself is bad.
        try:
            data = await self._request("GET", "/api/v2/servers")
        except CraftyPermissionError as err:
            raise CraftyAuthError(str(err)) from err
        return data if isinstance(data, list) else []

    async def async_get_stats(self, server_id: str) -> dict[str, Any]:
        data = await self._request("GET", f"/api/v2/servers/{server_id}/stats")
        return data if isinstance(data, dict) else {}

    async def async_get_logs(self, server_id: str, *, from_file: bool = True) -> list[str]:
        data = await self._request(
            "GET",
            f"/api/v2/servers/{server_id}/logs",
            params={"file": "true" if from_file else "false"},
        )
        return [str(line) for line in data] if isinstance(data, list) else []

    async def async_action(self, server_id: str, action: str) -> None:
        await self._request("POST", f"/api/v2/servers/{server_id}/action/{action}")

    async def async_send_command(self, server_id: str, command: str) -> None:
        await self._request(
            "POST", f"/api/v2/servers/{server_id}/stdin", data=command.lstrip("/")
        )

    async def async_get_host_metrics(self) -> dict[str, float]:
        """Read host CPU/memory from Crafty's Prometheus endpoint."""
        text = await self._request("GET", "/metrics/host", expect_json=False)
        return parse_prometheus(text)


def normalize_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    for suffix in ("/panel/dashboard", "/panel", "/api/v2", "/login"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


def parse_prometheus(text: str) -> dict[str, float]:
    """Parse simple `name value` / `name{labels} value` Prometheus lines."""
    out: dict[str, float] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.rsplit(" ", 1)
        if len(parts) != 2:
            continue
        name = parts[0].split("{", 1)[0].strip()
        try:
            out[name] = float(parts[1])
        except ValueError:
            continue
    return out
