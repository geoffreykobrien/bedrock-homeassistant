"""Fixtures."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.components import frontend

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def stub_frontend():
    """The test env has no hass_frontend package; fake the parts we use."""

    async def _setup(hass, config):
        hass.data[frontend.DATA_EXTRA_MODULE_URL] = frontend.UrlManager(lambda *a: None, [])
        hass.data[frontend.DATA_EXTRA_JS_URL_ES5] = frontend.UrlManager(lambda *a: None, [])
        return True

    with patch.object(frontend, "async_setup", _setup):
        yield
