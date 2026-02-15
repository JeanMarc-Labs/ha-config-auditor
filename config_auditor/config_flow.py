"""Config flow for H.A.C.A."""
from __future__ import annotations

import voluptuous as vol
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL


class ConfigAuditorConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for H.A.C.A."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if already configured
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()

            # Validate scan interval
            scan_interval = user_input.get("scan_interval", DEFAULT_SCAN_INTERVAL)
            if not (5 <= scan_interval <= 1440):
                errors["scan_interval"] = "invalid_interval"
            else:
                return self.async_create_entry(
                    title="H.A.C.A",
                    data={},
                    options={
                        "scan_interval": scan_interval,
                        "auto_fix_enabled": False,
                        "backup_enabled": True,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval", default=DEFAULT_SCAN_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for H.A.C.A."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        # Ne pas écraser la property 'config_entry' de la classe parente
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=options.get("scan_interval", DEFAULT_SCAN_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=1440)),
                    vol.Optional(
                        "auto_fix_enabled",
                        default=options.get("auto_fix_enabled", False),
                    ): cv.boolean,
                    vol.Optional(
                        "backup_enabled",
                        default=options.get("backup_enabled", True),
                    ): cv.boolean,
                }
            ),
        )
