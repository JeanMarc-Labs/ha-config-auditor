"""Instance-wide tools: services, backups, reloads, raw configuration files.

``_auto_backup`` lives here beside the backup tool it delegates to; the write
tools in the sibling modules call it before they touch a file.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from ..yaml_sources import is_within, iter_domain_files
from .common import _async_read_file, _atomic_write, _caller_context, _LOGGER, _slugify


def _service_wants_response(hass: "HomeAssistant", domain: str, service: str) -> bool:
    """True when HA requires or allows ``return_response`` for this action.

    Home Assistant tags every action NONE / OPTIONAL / ONLY, and
    ``ServiceRegistry.async_call`` validates the flag both ways: an ONLY action
    (``weather.get_forecasts``, ``calendar.get_events``, ``todo.get_items``,
    ``conversation.process``, …) raises unless ``return_response=True``, and a
    NONE action raises if it is passed. OPTIONAL runs either way, but the
    response is dropped when the flag is off — which is what used to happen to
    every one of them.

    An unregistered action returns False, so the call still goes through and
    fails in the caller's ``except`` with HA's own "action not found" message,
    exactly as before. ``async_services_for_domain`` is the cheap single-domain
    lookup but postdates the 2024.1 floor in ``hacs.json``; the whole-registry
    copy is the fallback there.
    """
    try:
        from homeassistant.core import SupportsResponse

        for_domain = getattr(hass.services, "async_services_for_domain", None)
        services = (
            for_domain(domain) if for_domain is not None
            else hass.services.async_services().get(domain, {})
        )
        svc = services.get(service)
        return svc is not None and svc.supports_response is not SupportsResponse.NONE
    except Exception:  # noqa: BLE001 — a probe must never break the call itself
        return False


async def _tool_ha_call_service(hass: HomeAssistant, params: dict) -> dict:
    """Appelle un service HA."""
    domain = params.get("domain", "").strip()
    service = params.get("service", "").strip()
    data = params.get("data") or {}

    if not domain or not service:
        return {"error": "domain and service are required"}

    wants_response = _service_wants_response(hass, domain, service)

    try:
        response = await hass.services.async_call(
            domain, service, data, blocking=True, return_response=wants_response,
            context=_caller_context(),
        )
        result: dict[str, Any] = {
            "success": True,
            "called": f"{domain}.{service}",
            "data": data,
        }
        if response is not None:
            result["response"] = response
        return result
    except Exception as exc:
        return {"error": f"Service call failed: {exc}"}


async def _auto_backup(hass: HomeAssistant, reason: str) -> None:
    """Déclenche un backup HA en arrière-plan avant une opération destructive.

    Délègue à _tool_ha_backup_create (source unique de la logique backup)
    et lance la tâche en arrière-plan pour ne pas bloquer l'outil.
    """
    from datetime import datetime as _dt
    name = f"HACA auto — {reason[:40]} — {_dt.now().strftime('%Y-%m-%d %H:%M')}"
    _LOGGER.warning("[HACA] Auto-backup avant opération destructive : %s", name)

    async def _run():
        try:
            result = await _tool_ha_backup_create(hass, {"name": name})
            if result.get("success") or result.get("started"):
                _LOGGER.info("[HACA] Auto-backup lancé : %s", name)
            else:
                _LOGGER.warning("[HACA] Auto-backup résultat : %s", result)
        except Exception as exc:
            _LOGGER.warning("[HACA] Auto-backup échoué (non bloquant) : %s", exc)

    hass.async_create_task(_run())


async def _tool_ha_backup_create(hass: HomeAssistant, params: dict) -> dict:
    """Create a full HA backup. Supports HA 2024.x (service) and HA 2025.x (manager API)."""
    from datetime import datetime
    import inspect

    name = params.get("name", "").strip()
    if not name:
        name = f"HACA backup {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    errors: list[str] = []

    # ── Strategy 1: BackupManager internal API (HA 2025.1+) ──────────────
    # DATA_MANAGER key is set in hass.data by the backup component
    try:
        from homeassistant.components.backup.const import DATA_MANAGER  # type: ignore
    except ImportError:
        DATA_MANAGER = None  # type: ignore

    if DATA_MANAGER is not None:
        try:
            manager = hass.data.get(DATA_MANAGER)
            if manager is None:
                errors.append("hass.data[DATA_MANAGER] is None — backup component not loaded?")
            else:
                create_fn = getattr(manager, "async_create_backup", None)
                if create_fn is None:
                    errors.append("BackupManager has no async_create_backup method")
                else:
                    sig = inspect.signature(create_fn)
                    # HA 2025.1+ takes agent_ids + include_* kwargs
                    if "agent_ids" in sig.parameters:
                        # Collect available agent IDs from the manager
                        agents = getattr(manager, "backup_agents", {})
                        agent_ids = list(agents.keys()) if agents else []

                        kwargs: dict = {
                            "agent_ids": agent_ids,
                            "include_all_addons": True,
                            "include_database": True,
                            "include_homeassistant": True,
                            "name": name,
                            "password": None,
                        }
                        # Some HA versions require these extra params
                        if "include_addons" in sig.parameters:
                            kwargs["include_addons"] = None
                        if "include_folders" in sig.parameters:
                            # Mirror the native HA full-backup behaviour:
                            # include media, share, ssl and locally-installed addons.
                            try:
                                from homeassistant.components.backup import Folder  # type: ignore
                                kwargs["include_folders"] = list(Folder)
                            except Exception:
                                # Fallback: pass the string values directly
                                kwargs["include_folders"] = ["media", "share", "ssl", "addons/local"]
                    else:
                        # Older manager API (no agent_ids)
                        kwargs = {}
                        if "name" in sig.parameters:
                            kwargs["name"] = name

                    # Fail fast on the one failure mode we can already see:
                    # async_create_backup rejects an empty agent list, and that
                    # error would otherwise vanish inside the background task.
                    if "agent_ids" in sig.parameters and not kwargs.get("agent_ids"):
                        errors.append(
                            "No backup agent registered (manager.backup_agents is empty) "
                            "— the backup component may not be fully started yet."
                        )
                    else:
                        # Fire as background task — backups take minutes and the MCP
                        # client would time out long before completion.
                        task = hass.async_create_task(create_fn(**kwargs))

                        def _log_backup_result(t: asyncio.Task, _name: str = name) -> None:
                            if t.cancelled():
                                _LOGGER.warning("[HACA] Background backup '%s' was cancelled", _name)
                                return
                            if (exc := t.exception()) is not None:
                                _LOGGER.error("[HACA] Background backup '%s' failed: %s", _name, exc)
                            else:
                                _LOGGER.info("[HACA] Background backup '%s' finished", _name)

                        task.add_done_callback(_log_backup_result)
                        return {
                            "started": True,
                            "completed": False,
                            "name": name,
                            "message": (
                                f"Backup '{name}' STARTED via BackupManager — it is NOT finished yet. "
                                "This may take several minutes: verify in Settings → System → Backups "
                                "before reporting the backup as done."
                            ),
                        }
        except Exception as exc:
            errors.append(f"BackupManager API: {exc}")

    # ── Strategy 2: backup.create service (HA pre-2025.1, Core/Container) ──
    if hass.services.has_service("backup", "create"):
        try:
            await hass.services.async_call("backup", "create", blocking=False, context=_caller_context())
            return {
                "started": True,
                "completed": False,
                "name": name,
                "message": "Backup TRIGGERED via the backup.create service — it is NOT finished yet. "
                           "Verify in Settings → System → Backups in a few minutes "
                           "before reporting the backup as done.",
            }
        except Exception as exc:
            errors.append(f"backup.create service: {exc}")

    # ── Strategy 3: Supervisor REST API (HAOS / Supervised) ────────────────
    try:
        import os
        import aiohttp
        supervisor_token = os.environ.get("SUPERVISOR_TOKEN") or os.environ.get("HASSIO_TOKEN")
        if supervisor_token:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "http://supervisor/backups/new/full",
                    json={"name": name},
                    headers={
                        "Authorization": f"Bearer {supervisor_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=300),
                ) as resp:
                    if resp.status in (200, 201):
                        data = await resp.json()
                        return {
                            "success": True,
                            "backup_id": data.get("data", {}).get("slug"),
                            "name": name,
                            "message": f"Backup '{name}' created via Supervisor REST API. "
                                       "Visible in Settings → System → Backups.",
                        }
                    text = await resp.text()
                    errors.append(f"Supervisor API HTTP {resp.status}: {text[:200]}")
        else:
            errors.append("No SUPERVISOR_TOKEN env var (not HAOS/Supervised)")
    except Exception as exc:
        errors.append(f"Supervisor REST API: {exc}")

    return {
        "error": "All backup strategies failed.",
        "attempts": errors,
        "hint": (
            "Create a manual backup: Settings → System → Backups → Create backup.\n"
            "Ensure the 'Backup' integration is loaded in Home Assistant."
        ),
    }


async def _tool_ha_check_config(hass: HomeAssistant, params: dict) -> dict:
    """Validate HA config files without restarting.

    Uses the check_config helper directly: the homeassistant.check_config
    service is registered without supports_response, so calling it with
    return_response=True always raises before the handler even runs.
    """
    try:
        from homeassistant.helpers.check_config import async_check_ha_config_file

        result = await async_check_ha_config_file(hass)
        errors = result.errors if hasattr(result, "errors") else []
        warnings = result.warnings if hasattr(result, "warnings") else []

        if not errors:
            return {
                "valid": True,
                "warnings": [str(w) for w in warnings],
                "message": "Configuration is valid.",
            }
        return {
            "valid": False,
            "errors": [str(e) for e in errors],
            "warnings": [str(w) for w in warnings],
            "message": f"{len(errors)} error(s) found in configuration — do NOT reload until fixed.",
        }

    except Exception as exc:
        return {"error": f"Config check failed: {exc}"}


async def _tool_ha_eval_template(hass: HomeAssistant, params: dict) -> dict:
    """Render a Jinja2 template against the live HA state."""
    template_str = params.get("template", "").strip()
    if not template_str:
        return {"error": "template string is required"}

    try:
        from homeassistant.helpers.template import Template

        tpl = Template(template_str, hass)
        rendered = await hass.async_add_executor_job(tpl.async_render)

        return {
            "success": True,
            "template": template_str,
            "result": str(rendered),
            "type": type(rendered).__name__,
        }

    except Exception as exc:
        return {
            "success": False,
            "template": template_str,
            "error": str(exc),
            "hint": "Template raised an error. Check entity_ids and Jinja2 syntax.",
        }


async def _tool_ha_deep_search(hass: HomeAssistant, params: dict) -> dict:
    """Search inside automation/script YAML content."""
    import yaml
    from pathlib import Path

    query = params.get("query", "").strip()
    if not query:
        return {"error": "query is required"}

    scope = params.get("scope", "all")
    config_dir = Path(hass.config.config_dir)

    matches: list[dict] = []
    query_lower = query.lower()

    def _search_files() -> list[dict]:
        """Lecture + recherche dans le thread executor — avec timeout implicite."""
        # Tous les fichiers des clés `automation:` / `script:` : sur une config
        # splittée, chercher uniquement les fichiers plats ne trouvait rien.
        files_to_search: list[tuple[str, Path]] = []
        if scope in ("automations", "all"):
            files_to_search += [
                ("automation", Path(p))
                for p in iter_domain_files(str(config_dir), "automation", "automations.yaml")
            ]
        if scope in ("scripts", "all"):
            files_to_search += [
                ("script", Path(p))
                for p in iter_domain_files(str(config_dir), "script", "scripts.yaml")
            ]

        results: list[dict] = []
        for kind, path in files_to_search:
            try:
                raw = path.read_text(encoding="utf-8")
                data = yaml.safe_load(raw) or {}
            except Exception:
                continue
            items = data if isinstance(data, list) else [
                {"id": k, "alias": k, **v} for k, v in data.items()
                if isinstance(v, dict)
            ]
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_str = yaml.dump(item, allow_unicode=True).lower()
                if query_lower in item_str:
                    alias = item.get("alias") or item.get("id", "?")
                    context_lines = [
                        line.strip() for line in item_str.splitlines()
                        if query_lower in line.lower()
                    ][:5]
                    results.append({
                        "type": kind,
                        "alias": alias,
                        "id": item.get("id", ""),
                        "entity_id": f"{kind}.{_slugify(str(alias))}",
                        "matches_in": context_lines,
                    })
        return results

    try:
        import asyncio as _asyncio
        matches = await _asyncio.wait_for(
            hass.async_add_executor_job(_search_files),
            timeout=15.0,
        )

        return {
            "success": True,
            "query": query,
            "scope": scope,
            "total_matches": len(matches),
            "results": matches,
            "note": "Use ha_get_entities(domain='automation') to get live entity_ids for matched automations." if matches else "",
        }

    except Exception as exc:
        return {"error": f"Deep search failed: {exc}"}


# ── Handlers — low priority tools ───────────────────────────────────────────

async def _tool_ha_get_system_health(hass: HomeAssistant, params: dict) -> dict:
    """Get HA system health."""
    try:
        from homeassistant.components import system_health as sh

        info: dict[str, Any] = {
            "ha_version": hass.config.version if hasattr(hass.config, "version") else "unknown",
            "config_dir": hass.config.config_dir,
            "timezone": str(hass.config.time_zone),
            "unit_system": hass.config.units.name if hasattr(hass.config.units, "name") else str(hass.config.units),
            "state_count": len(hass.states.async_all()),
            "component_count": len(hass.config.components),
        }

        # Integrations in error state
        try:
            errors = [
                entry.domain
                for entry in hass.config_entries.async_entries()
                if entry.state.value in ("setup_error", "setup_retry", "failed_unload", "not_loaded")
            ]
            info["integrations_with_errors"] = errors
            info["integration_error_count"] = len(errors)
        except Exception:
            pass

        # Recorder info
        try:
            from homeassistant.components.recorder import get_instance
            rec = get_instance(hass)
            info["recorder_db_path"] = str(rec.db_url) if hasattr(rec, "db_url") else "unknown"
        except Exception:
            info["recorder"] = "unavailable"

        # System health data if available
        try:
            health_data = {}
            for domain, info_coro in sh.async_get_system_health(hass):
                try:
                    health_data[domain] = await info_coro
                except Exception:
                    health_data[domain] = "error"
            info["system_health"] = health_data
        except Exception:
            pass

        return {"success": True, "system": info}

    except Exception as exc:
        # Minimal fallback
        try:
            return {
                "success": True,
                "system": {
                    "ha_version": hass.config.version if hasattr(hass.config, "version") else "unknown",
                    "state_count": len(hass.states.async_all()),
                    "note": f"Full system health unavailable: {exc}",
                },
            }
        except Exception as exc2:
            return {"error": f"System health query failed: {exc2}"}


async def _tool_ha_get_updates(hass: HomeAssistant, params: dict) -> dict:
    """List available HA updates."""
    try:
        updates: list[dict] = []

        # Check update entities (HA 2022.4+ exposes update.* entities)
        for state in hass.states.async_all():
            if not state.entity_id.startswith("update."):
                continue
            attrs = state.attributes
            if state.state == "on":  # "on" = update available
                updates.append({
                    "entity_id": state.entity_id,
                    "name": attrs.get("friendly_name", state.entity_id),
                    "installed_version": attrs.get("installed_version"),
                    "latest_version": attrs.get("latest_version"),
                    "release_url": attrs.get("release_url"),
                    "auto_update": attrs.get("auto_update", False),
                })

        return {
            "success": True,
            "updates_available": len(updates),
            "updates": updates,
            "note": "Updates shown are for entities in the 'update' domain. "
                    "Ensure the 'updates' integration is enabled for full coverage." if not updates else "",
        }

    except Exception as exc:
        return {"error": f"Failed to retrieve updates: {exc}"}


_RELOADABLE_DOMAINS = {
    "automation", "script", "scene", "group",
    "input_boolean", "input_number", "input_text", "input_select", "input_datetime",
    "timer", "counter", "template", "customize", "core",
}


# Domains whose reload is not `<domain>.reload`. `core` and `customize` are not
# integrations at all — they are sections of `configuration.yaml`, and Home
# Assistant reloads both through the same homeassistant.reload_core_config
# action. The tool used to call `core.reload_config_entry` (a service that has
# never existed under that domain, and whose homeassistant.* namesake reloads
# one config entry by entry_id, not the core config) and `customize.reload`.
_RELOAD_ACTIONS = {
    "core": ("homeassistant", "reload_core_config"),
    "customize": ("homeassistant", "reload_core_config"),
}


async def _tool_ha_reload_core(hass: HomeAssistant, params: dict) -> dict:
    """Reload a HA domain without restarting."""
    domain = params.get("domain", "").strip().lower()
    if not domain:
        return {"error": "domain is required"}
    if domain not in _RELOADABLE_DOMAINS:
        return {
            "error": f"Domain '{domain}' is not reloadable via this tool. "
                     f"Reloadable domains: {sorted(_RELOADABLE_DOMAINS)}",
        }

    svc_domain, svc_name = _RELOAD_ACTIONS.get(domain, (domain, "reload"))

    # `template.reload`, `timer.reload`, … only exist once the integration is
    # loaded. Without this check an install with no `template:` section got a
    # raw "Action template.reload not found" back instead of an explanation.
    if not hass.services.has_service(svc_domain, svc_name):
        return {
            "error": f"Domain '{domain}' has no reload action registered "
                     f"({svc_domain}.{svc_name}) — the integration is most "
                     f"likely not loaded on this instance.",
        }

    try:
        await hass.services.async_call(svc_domain, svc_name, blocking=True, context=_caller_context())
        return {
            "success": True,
            "domain": domain,
            "action": f"{svc_domain}.{svc_name}",
            "message": f"Domain '{domain}' reloaded successfully.",
        }
    except Exception as exc:
        return {"error": f"Failed to reload '{domain}': {exc}"}


async def _tool_ha_list_services(hass: HomeAssistant, params: dict) -> dict:
    """List available HA services."""
    domain_filter = params.get("domain", "").strip().lower()

    try:
        all_services = hass.services.async_services()
        result: dict[str, dict] = {}

        for domain, services in all_services.items():
            if domain_filter and domain != domain_filter:
                continue
            domain_dict: dict[str, Any] = {}
            for svc_name, svc in services.items():
                domain_dict[svc_name] = {
                    "description": (svc.description or "") if hasattr(svc, "description") else "",
                    "fields": (
                        {k: {"description": v.get("description", "")}
                         for k, v in (svc.fields or {}).items()}
                        if hasattr(svc, "fields") else {}
                    ),
                }
            result[domain] = domain_dict

        total = sum(len(v) for v in result.values())
        return {
            "success": True,
            "domain_filter": domain_filter or None,
            "domain_count": len(result),
            "service_count": total,
            "services": result,
        }

    except Exception as exc:
        return {"error": f"Failed to list services: {exc}"}


# ── CONFIG FILES (SECURITY FIXES) ────────────────────────────────────────────

async def _tool_ha_get_config_file(hass: HomeAssistant, params: dict) -> dict:
    """Read any HA config file (configuration.yaml, secrets.yaml, automations.yaml, etc.).

    Returns the raw content. Useful to inspect hardcoded secrets or misconfigured entries.
    Files outside /config are blocked for safety.
    """
    import os
    filename = params.get("filename", "").strip()
    if not filename:
        return {"error": "filename required (e.g. 'configuration.yaml', 'secrets.yaml', 'automations.yaml')"}

    # Resolve path — only allow files inside /config
    if os.path.isabs(filename):
        fpath = filename
    else:
        fpath = hass.config.path(filename)

    # realpath() follows symlinks and isfile() stats: three blocking calls,
    # grouped into one executor hop.
    def _resolve_for_read() -> tuple[str, str, bool]:
        root = os.path.realpath(hass.config.config_dir)
        real = os.path.realpath(fpath)
        return root, real, os.path.isfile(real)

    config_root, fpath_real, _is_file = await hass.async_add_executor_job(_resolve_for_read)
    if not fpath_real.startswith(config_root + os.sep) and fpath_real != config_root:
        return {"error": f"Cannot read files outside {config_root}"}

    if not _is_file:
        return {"error": f"File not found: {fpath_real}"}

    try:
        content = await _async_read_file(hass, fpath_real)
    except Exception as exc:
        return {"error": f"Failed to read {fpath_real}: {exc}"}

    # Warn if file contains potential secrets in plaintext
    import re
    sensitive_patterns = [
        r"(?i)(password|token|secret|api_key|access_token|bearer)\s*[=:]\s*\S+",
        r"(?i)(password|token|secret)\s*:\s*['\"]?[^'\"\n]{8,}['\"]?",
    ]
    warnings: list[str] = []
    for pat in sensitive_patterns:
        matches = re.findall(pat, content)
        if matches:
            warnings.append(f"Potential hardcoded sensitive value detected ({len(matches)} match(es))")
            break

    return {
        "filename": fpath,
        "content": content,
        "lines": content.count("\n") + 1,
        "size_bytes": len(content.encode()),
        "warnings": warnings,
    }


async def _tool_ha_update_config_file(hass: HomeAssistant, params: dict) -> dict:
    """Write to a HA config file (safe subset: automations, scripts, scenes, secrets, groups).

    Can do: full replace, line replace, or append.
    ALWAYS validate with ha_check_config after editing configuration.yaml.
    """
    import os
    filename = params.get("filename", "").strip()
    content  = params.get("content")
    mode     = params.get("mode", "replace").lower()  # replace | append | patch_line

    if not filename:
        return {"error": "filename required"}
    if content is None:
        return {"error": "content required"}

    # Safety: only allowed filenames/patterns
    _ALLOWED = {
        "automations.yaml", "scripts.yaml", "scenes.yaml",
        "secrets.yaml", "groups.yaml", "customize.yaml",
        "configuration.yaml", "ui-lovelace.yaml",
    }
    basename = os.path.basename(filename)

    if os.path.isabs(filename):
        fpath = filename
    else:
        fpath = hass.config.path(filename)

    # Path traversal protection — os.path.realpath résout les symlinks et les ../
    # Both resolutions, plus the packages/ test below, in one executor hop.
    def _resolve_for_write() -> tuple[str, str, bool]:
        root = os.path.realpath(hass.config.config_dir)
        real = os.path.realpath(fpath)
        return root, real, is_within(real, os.path.join(root, "packages"))

    config_root, fpath_real, in_packages = await hass.async_add_executor_job(_resolve_for_write)
    if not fpath_real.startswith(config_root + os.sep) and fpath_real != config_root:
        return {"error": f"Cannot write files outside {config_root} (resolved: {fpath_real})"}

    # A package file is allowed on top of the flat list. The test used to read
    # `basename.startswith("packages/")` — `os.path.basename()` never returns a
    # separator, so that branch could never fire and every package write was
    # refused. It now runs on the RESOLVED path, after the traversal guard, so
    # `packages/../secrets.yaml` cannot ride in on the prefix.
    if basename not in _ALLOWED and not in_packages:
        return {
            "error": (
                f"'{basename}' is not in the allowed write list: {sorted(_ALLOWED)}, "
                f"plus any file under 'packages/'. "
                "Use ha_create_automation/ha_create_script for automation changes."
            )
        }

    # Backup automatique avant toute écriture
    await _auto_backup(hass, f"update_config_file:{basename}")

    def _do_write():
        """Blocking file operations — runs in executor."""
        if mode == "append":
            try:
                existing = open(fpath_real, encoding="utf-8").read()
            except FileNotFoundError:
                existing = ""
            _atomic_write(fpath_real, existing + "\n" + content)
        elif mode == "patch_line":
            old_text = params.get("old_text", "")
            if not old_text:
                raise ValueError("patch_line mode requires old_text")
            try:
                existing = open(fpath_real, encoding="utf-8").read()
            except FileNotFoundError:
                raise FileNotFoundError(f"File not found: {fpath_real}")
            if old_text not in existing:
                raise ValueError(f"old_text not found in {filename}")
            _atomic_write(fpath_real, existing.replace(old_text, content, 1))
        else:  # replace
            _atomic_write(fpath_real, content)

    try:
        await hass.async_add_executor_job(_do_write)
    except (ValueError, FileNotFoundError) as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"Failed to write {fpath_real}: {exc}"}

    return {
        "success": True,
        "filename": fpath,
        "mode": mode,
        "message": (
            f"File '{filename}' updated (mode={mode}). "
            "Run ha_check_config() to validate before reloading."
        ),
    }
