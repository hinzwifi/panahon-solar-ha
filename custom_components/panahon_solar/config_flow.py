"""Config flow for DOST-PAGASA PANaHON & PH Solar Forecast."""

from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ARRAY_KWP,
    CONF_DEVICE_ID,
    CONF_PANEL_AZIMUTH,
    CONF_PANEL_TILT,
    CONF_SYS_EFFICIENCY,
    DEFAULT_ARRAY_KWP,
    DEFAULT_NAME,
    DEFAULT_PANEL_AZIMUTH,
    DEFAULT_PANEL_TILT,
    DEFAULT_SYS_EFFICIENCY,
    DOMAIN,
)


class PanahonSolarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PANaHON & PH Solar Forecast."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data=user_input,
            )

        default_lat = self.hass.config.latitude or 14.5995
        default_lon = self.hass.config.longitude or 120.9842

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
                vol.Required(CONF_ARRAY_KWP, default=DEFAULT_ARRAY_KWP): vol.Coerce(float),
                vol.Required(CONF_PANEL_TILT, default=DEFAULT_PANEL_TILT): vol.Coerce(float),
                vol.Required(CONF_PANEL_AZIMUTH, default=DEFAULT_PANEL_AZIMUTH): vol.Coerce(float),
                vol.Required(CONF_SYS_EFFICIENCY, default=DEFAULT_SYS_EFFICIENCY): vol.Coerce(float),
                vol.Optional(CONF_DEVICE_ID, default=""): str,
                vol.Optional(CONF_ACCESS_TOKEN, default=""): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)
