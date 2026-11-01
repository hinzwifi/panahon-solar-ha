"""Config flow for DOST-PAGASA PANaHON & PH Solar Forecast."""

from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME
from homeassistant.core import callback

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
    """Handle a step-by-step, reconfigurable flow for PANaHON & PH Solar Forecast."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return PanahonSolarOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 1 (KISS): Essential Location and Solar Array Size."""
        if user_input is not None:
            self._user_input.update(user_input)
            return await self.async_step_advanced()

        default_lat = self.hass.config.latitude or 14.5995
        default_lon = self.hass.config.longitude or 120.9842

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
                vol.Required(CONF_ARRAY_KWP, default=DEFAULT_ARRAY_KWP): vol.Coerce(float),
                vol.Required(CONF_PANEL_TILT, default=DEFAULT_PANEL_TILT): vol.Coerce(float),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Step 2 (Optional): Roof Orientation and Optional PANaHON App Credentials."""
        if user_input is not None:
            self._user_input.update(user_input)
            return self.async_create_entry(
                title=self._user_input.get(CONF_NAME, DEFAULT_NAME),
                data=self._user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_PANEL_AZIMUTH, default=DEFAULT_PANEL_AZIMUTH): vol.Coerce(float),
                vol.Required(CONF_SYS_EFFICIENCY, default=DEFAULT_SYS_EFFICIENCY): vol.Coerce(float),
                vol.Optional(CONF_DEVICE_ID, default=""): str,
                vol.Optional(CONF_ACCESS_TOKEN, default=""): str,
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle reconfiguring the existing config entry."""
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if entry is None:
            return self.async_abort(reason="reconfigure_failed")

        if user_input is not None:
            return self.async_update_reload_and_abort(
                entry,
                data={**entry.data, **user_input},
                reason="reconfigure_successful",
            )

        current = {**entry.data, **entry.options}
        schema = vol.Schema(
            {
                vol.Required(CONF_LATITUDE, default=current.get(CONF_LATITUDE, 14.5995)): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=current.get(CONF_LONGITUDE, 120.9842)): vol.Coerce(float),
                vol.Required(CONF_ARRAY_KWP, default=current.get(CONF_ARRAY_KWP, DEFAULT_ARRAY_KWP)): vol.Coerce(float),
                vol.Required(CONF_PANEL_TILT, default=current.get(CONF_PANEL_TILT, DEFAULT_PANEL_TILT)): vol.Coerce(float),
                vol.Required(CONF_PANEL_AZIMUTH, default=current.get(CONF_PANEL_AZIMUTH, DEFAULT_PANEL_AZIMUTH)): vol.Coerce(float),
                vol.Required(CONF_SYS_EFFICIENCY, default=current.get(CONF_SYS_EFFICIENCY, DEFAULT_SYS_EFFICIENCY)): vol.Coerce(float),
                vol.Optional(CONF_DEVICE_ID, default=current.get(CONF_DEVICE_ID, "")): str,
                vol.Optional(CONF_ACCESS_TOKEN, default=current.get(CONF_ACCESS_TOKEN, "")): str,
            }
        )
        return self.async_show_form(step_id="reconfigure", data_schema=schema)


class PanahonSolarOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for live reconfiguring via Configure button."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        entry = self.config_entry
        current = {**entry.data, **entry.options}
        schema = vol.Schema(
            {
                vol.Required(CONF_ARRAY_KWP, default=current.get(CONF_ARRAY_KWP, DEFAULT_ARRAY_KWP)): vol.Coerce(float),
                vol.Required(CONF_PANEL_TILT, default=current.get(CONF_PANEL_TILT, DEFAULT_PANEL_TILT)): vol.Coerce(float),
                vol.Required(CONF_PANEL_AZIMUTH, default=current.get(CONF_PANEL_AZIMUTH, DEFAULT_PANEL_AZIMUTH)): vol.Coerce(float),
                vol.Required(CONF_SYS_EFFICIENCY, default=current.get(CONF_SYS_EFFICIENCY, DEFAULT_SYS_EFFICIENCY)): vol.Coerce(float),
                vol.Optional(CONF_DEVICE_ID, default=current.get(CONF_DEVICE_ID, "")): str,
                vol.Optional(CONF_ACCESS_TOKEN, default=current.get(CONF_ACCESS_TOKEN, "")): str,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
