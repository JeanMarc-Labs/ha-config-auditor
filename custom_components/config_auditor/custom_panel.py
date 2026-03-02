"""H.A.C.A Custom Panel."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


# Clé hass.data pour savoir si les paths statiques ont déjà été enregistrés
# dans ce process HA. Les routes aiohttp sont permanentes (durée de vie du process) :
# les ré-enregistrer lève RuntimeError → 403. On ne les enregistre donc qu'une seule fois.
_STATIC_PATHS_KEY = f"{DOMAIN}_static_paths_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Register H.A.C.A custom panel.

    Les paths statiques aiohttp ne peuvent pas être désenregistrés ni
    ré-enregistrés au sein d'un même process HA. On les enregistre une
    seule fois (flag _STATIC_PATHS_KEY dans hass.data) et on met à jour
    le panel frontend à chaque setup via update=True.
    """
    from .const import VERSION as _VERSION
    # Utiliser le hash du bundle JS comme cache_bust pour forcer le rechargement
    # du navigateur à chaque build (évite le cache navigateur avec l'ancien JS)
    hash_file = Path(__file__).parent / "www" / "haca-panel.hash"
    if hash_file.exists():
        cache_bust = hash_file.read_text().strip()
    else:
        cache_bust = _VERSION.replace(".", "_")

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

        # ── Static paths : une seule fois par process ──────────────────────
        # aiohttp lève RuntimeError si on tente d'enregistrer deux fois le même
        # chemin GET. Ce flag survit aux reload/unload mais pas au redémarrage HA.
        if not hass.data.get(_STATIC_PATHS_KEY):
            reports_dir = Path(hass.config.path("haca_reports"))
            reports_dir.mkdir(exist_ok=True)

            static_paths = [
                StaticPathConfig(f"/{DOMAIN}", str(www_dir), False),
                StaticPathConfig("/haca_reports", str(reports_dir), False),
            ]
            await hass.http.async_register_static_paths(static_paths)
            hass.data[_STATIC_PATHS_KEY] = True
            _LOGGER.info(
                "✅ Static paths registered: /%s, /haca_reports (js?v=%s)",
                DOMAIN, cache_bust,
            )
        else:
            _LOGGER.info(
                "ℹ️ Static paths already registered for this process — skipping"
            )

        # ── Panel frontend : enregistrer ou mettre à jour ──────────────────
        # async_register_built_in_panel accepte update=True pour écraser
        # un panel existant sans lever ValueError. On passe toujours update=True
        # pour garantir que le panel est présent après un reload.
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
            update=True,
        )
        _LOGGER.info(
            "✅ Panel registered/updated: /%s/haca-panel.js?v=%s",
            DOMAIN, cache_bust,
        )

    except Exception as e:
        _LOGGER.error("❌ Panel registration error: %s", e, exc_info=True)


async def async_unregister_panel(hass: HomeAssistant) -> None:
    """Unregister panel."""
    try:
        frontend.async_remove_panel(hass, DOMAIN)
        _LOGGER.info("✅ Panel unregistered")
    except Exception as e:
        _LOGGER.warning("⚠️ Unregister failed: %s", e)
