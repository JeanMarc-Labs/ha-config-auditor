"""H.A.C.A Custom Panel."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register H.A.C.A custom panel."""

    try:
        integration_dir = Path(__file__).parent
        www_dir = integration_dir / "www"

        if not www_dir.exists():
            _LOGGER.error("❌ WWW directory not found: %s", www_dir)
            return

        js_file = www_dir / "haca-panel.js"
        if not js_file.exists():
            _LOGGER.error("❌ JS file not found: %s", js_file)
            return

        _LOGGER.info("✅ Found JS file: %s", js_file)

        # Register static paths
        static_paths = [
            StaticPathConfig(f"/{DOMAIN}", str(www_dir), False)
        ]
        
        # Add reports directory if it exists
        reports_dir = Path(hass.config.path("haca_reports"))
        if reports_dir.exists():
            _LOGGER.info("✅ Found reports directory: %s", reports_dir)
            static_paths.append(StaticPathConfig("/haca_reports", str(reports_dir), False))
        
        await hass.http.async_register_static_paths(static_paths)
        
        _LOGGER.info("✅ Static paths registered: /%s, /haca_reports", DOMAIN)

        # Register custom panel with proper config
        import time
        cache_bust = int(time.time())
        
        # Register custom panel only if not already present
        if DOMAIN not in hass.data.get("frontend_panels", {}):
            frontend.async_register_built_in_panel(
                hass,
                component_name="custom",
                sidebar_title="H.A.C.A",
                sidebar_icon="mdi:shield-check",
                frontend_url_path=DOMAIN,
                config={
                    "_panel_custom": {
                        "name": "haca-panel",
                        "js_url": f"/{DOMAIN}/haca-panel.js?v={cache_bust}",
                        "embed_iframe": False,
                        "trust_external": False,
                    }
                },
                require_admin=False,
            )
            _LOGGER.info("✅ Custom panel registered: /%s/haca-panel.js?v=%s", DOMAIN, cache_bust)
        else:
            _LOGGER.info("ℹ️ Panel %s already registered, skipping", DOMAIN)

    except Exception as e:
        _LOGGER.error("❌ Panel registration error: %s", e, exc_info=True)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister panel."""
    try:
        frontend.async_remove_panel(hass, DOMAIN)
        _LOGGER.info("✅ Panel unregistered")
    except Exception as e:
        _LOGGER.warning("⚠️ Unregister failed: %s", e)
