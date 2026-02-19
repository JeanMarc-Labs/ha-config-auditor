"""H.A.C.A - Home Assistant Config Auditor v1.0.0."""
from __future__ import annotations

import logging
import os
import shutil
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.helpers import device_registry as dr, config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DOMAIN,
    NAME,
    VERSION,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_SCAN_ALL,
    SERVICE_SCAN_AUTOMATIONS,
    SERVICE_SCAN_ENTITIES,
    SERVICE_GENERATE_REPORT,
    SERVICE_LIST_REPORTS,
    SERVICE_GET_REPORT_CONTENT,
    SERVICE_FIX_DEVICE_ID,
    SERVICE_PREVIEW_DEVICE_ID,
    SERVICE_FIX_MODE,
    SERVICE_PREVIEW_MODE,
    SERVICE_FIX_TEMPLATE,
    SERVICE_PREVIEW_TEMPLATE,
    SERVICE_LIST_BACKUPS,
    SERVICE_RESTORE_BACKUP,
    SERVICE_PURGE_GHOSTS,
    SERVICE_FUZZY_SUGGESTIONS,
    MODULE_4_COMPLIANCE_REPORT,
    MODULE_5_REFACTORING_ASSISTANT,
    BACKUP_DIR,
    REPORTS_DIR,
    HISTORY_FILE,
)
from .automation_analyzer import AutomationAnalyzer
from .entity_analyzer import EntityAnalyzer
from .performance_analyzer import PerformanceAnalyzer
from .security_analyzer import SecurityAnalyzer
from .custom_panel import async_register_panel, async_unregister_panel
from .websocket import async_register_websocket_handlers
from .conversation import async_setup_conversation, explain_issue_ai

if MODULE_4_COMPLIANCE_REPORT:
    from .report_generator import ReportGenerator

if MODULE_5_REFACTORING_ASSISTANT:
    from .refactoring_assistant import RefactoringAssistant

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the H.A.C.A component."""
    hass.data.setdefault(DOMAIN, {})
    return True


def calculate_health_score(
    automation_issues: list,
    entity_issues: list,
    performance_issues: list | None = None,
    security_issues: list | None = None,
) -> int:
    """Calculate health score with progressive formula.
    
    All four issue categories are included in the score:
    - automation + entity: full weight (primary quality indicators)
    - performance + security: half weight (optimization indicators)
    """
    import math
    severity_weights = {"high": 5, "medium": 3, "low": 1}

    # Full weight for automation and entity issues
    all_issues = list(automation_issues) + list(entity_issues)
    total_weight = sum(
        severity_weights.get(issue.get("severity", "low"), 1)
        for issue in all_issues
    )

    # Half weight for performance and security issues (they're optimizations, not critical)
    for issue in (performance_issues or []) + (security_issues or []):
        total_weight += severity_weights.get(issue.get("severity", "low"), 1) // 2

    # score = 100 * 0.99^total_weight
    # e.g. 20 low-weight issues → ~81%, 100 → ~36%
    score = int(100 * math.pow(0.99, total_weight))
    return max(0, score)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up H.A.C.A from a config entry."""
    _LOGGER.info("Setting up %s v%s", NAME, VERSION)

    hass.data.setdefault(DOMAIN, {})
    
    if entry.entry_id in hass.data[DOMAIN]:
        _LOGGER.warning("H.A.C.A already set up for this entry")
        return True
    
    # Create analyzers
    automation_analyzer = AutomationAnalyzer(hass)
    entity_analyzer = EntityAnalyzer(hass)
    performance_analyzer = PerformanceAnalyzer(hass)
    security_analyzer = SecurityAnalyzer(hass)
    
    # Create optional modules
    report_generator = ReportGenerator(hass) if MODULE_4_COMPLIANCE_REPORT else None
    refactoring_assistant = RefactoringAssistant(hass) if MODULE_5_REFACTORING_ASSISTANT else None
    
    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    
    async def async_update_data() -> dict[str, Any]:
        """Update data."""
        _LOGGER.debug("Running scheduled scan")
        
        automation_issues = await automation_analyzer.analyze_all()
        entity_issues = await entity_analyzer.analyze_all(
            automation_analyzer._automation_configs,
            automation_analyzer._script_configs,
        )
        # Pass automation configs to performance analyzer for complexity checks
        performance_issues = await performance_analyzer.analyze_all(
            automation_analyzer._automation_configs
        )
        # Run security analysis
        security_issues = await security_analyzer.analyze_all(
            automation_analyzer._automation_configs
        )
        
        # Get separated issue lists from automation analyzer
        automation_only_issues = automation_analyzer.automation_issues
        script_issues = automation_analyzer.script_issues
        scene_issues = automation_analyzer.scene_issues
        blueprint_issues = automation_analyzer.blueprint_issues
        
        health_score = calculate_health_score(
            automation_issues, entity_issues, performance_issues, security_issues
        )
        
        _LOGGER.info(
            "Health Score Calculation: Automation Issues=%d, Script Issues=%d, Blueprint Issues=%d, Entity Issues=%d, Performance Issues=%d. Score=%d%%", 
            len(automation_only_issues), len(script_issues), len(blueprint_issues), len(entity_issues), len(performance_issues), health_score
        )
        
        return {
            "health_score": health_score,
            "automation_issues": len(automation_only_issues),
            "script_issues": len(script_issues),
            "scene_issues": len(scene_issues),
            "blueprint_issues": len(blueprint_issues),
            "entity_issues": len(entity_issues),
            "performance_issues": len(performance_issues),
            "security_issues": len(security_issues),
            "total_issues": len(automation_only_issues) + len(script_issues) + len(scene_issues)
                          + len(blueprint_issues) + len(entity_issues)
                          + len(performance_issues) + len(security_issues),
            "automation_issue_list": automation_only_issues,
            "script_issue_list": script_issues,
            "scene_issue_list": scene_issues,
            "blueprint_issue_list": blueprint_issues,
            "entity_issue_list": entity_issues,
            "performance_issue_list": performance_issues,
            "security_issue_list": security_issues,
        }
    
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=scan_interval),
    )
    
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "entry": entry,
        "automation_analyzer": automation_analyzer,
        "entity_analyzer": entity_analyzer,
        "performance_analyzer": performance_analyzer,
        "report_generator": report_generator,
        "refactoring_assistant": refactoring_assistant,
        "security_analyzer": security_analyzer,
    }
    
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=NAME,
        manufacturer="Community",
        model="Config Auditor",
        sw_version=VERSION,
    )
    
    await coordinator.async_config_entry_first_refresh()
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register panel - CORRECTION: enregistrer le panneau seulement pour la première instance
    if len([e for e in hass.config_entries.async_entries(DOMAIN)]) == 1:
        await async_register_panel(hass)
        async_register_websocket_handlers(hass)
        await async_setup_conversation(hass, entry)
        _LOGGER.info("Panel, WebSocket handlers and Conversation agent registered")
    
    if len([e for e in hass.config_entries.async_entries(DOMAIN)]) == 1:
        await async_setup_services(hass, entry)
    
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    
    # Setup real-time issue detection for automations/scripts/scenes
    async def setup_realtime_detection():
        """Setup listeners for configuration changes to detect new issues."""
        
        # Store known issues to detect only NEW ones
        known_issues_file = hass.config.path(".haca_known_issues.json")
        
        def _load_known_issues() -> set:
            """Load known issues from file."""
            try:
                if os.path.exists(known_issues_file):
                    with open(known_issues_file, 'r') as f:
                        return set(json.load(f))
            except Exception as e:
                _LOGGER.debug("Could not load known issues: %s", e)
            return set()
        
        def _save_known_issues(issues: set):
            """Save known issues to file."""
            try:
                with open(known_issues_file, 'w') as f:
                    json.dump(list(issues), f)
            except Exception as e:
                _LOGGER.debug("Could not save known issues: %s", e)
        
        def _get_issue_signature(issue: dict) -> str:
            """Create a unique signature for an issue."""
            return f"{issue.get('entity_id', '')}|{issue.get('type', '')}|{issue.get('message', '')[:100]}"
        
        async def _check_for_new_issues(entity_type: str = None):
            """Check for new issues after a configuration change."""
            _LOGGER.debug("Checking for new issues (entity_type=%s)", entity_type)
            
            data = hass.data[DOMAIN][entry.entry_id]
            automation_analyzer = data["automation_analyzer"]
            coordinator = data["coordinator"]
            
            # Run a quick scan
            new_automation_issues = await automation_analyzer.analyze_all()
            
            # Get all current issues
            current_issues = []
            current_issues.extend(automation_analyzer.automation_issues)
            current_issues.extend(automation_analyzer.script_issues)
            current_issues.extend(automation_analyzer.scene_issues)

            # Load known issues (in executor to avoid blocking the event loop)
            known_issues = await hass.async_add_executor_job(_load_known_issues)

            # Find new issues
            new_issues = []
            for issue in current_issues:
                sig = _get_issue_signature(issue)
                if sig not in known_issues:
                    new_issues.append(issue)
            
            # If new issues found, notify
            if new_issues:
                _LOGGER.info("Found %d new issues!", len(new_issues))
                
                # Create detailed notification message
                if len(new_issues) == 1:
                    issue = new_issues[0]
                    title = "🛡️ H.A.C.A - Nouvelle issue détectée"
                    severity = issue.get('severity', 'low')
                    severity_icon = "🔴" if severity == "high" else ("🟠" if severity == "medium" else "🔵")
                    message = f"""**{severity_icon} Sévérité: {severity.upper()}**

**Élément:** {issue.get('alias', issue.get('entity_id', 'Inconnu'))}
**ID:** `{issue.get('entity_id', 'N/A')}`
**Type:** {issue.get('type', 'N/A')}

**Description:**
{issue.get('message', '')[:300]}

---
*🔍 Signalé par H.A.C.A - Home Assistant Config Auditor*"""
                else:
                    title = f"🛡️ H.A.C.A - {len(new_issues)} nouvelles issues détectées"
                    
                    # Build detailed list
                    message_parts = ["**Issues détectées:**\n"]
                    
                    # Group by entity type for summary
                    by_type = {}
                    for issue in new_issues:
                        etype = issue.get('entity_id', '').split('.')[0] if issue.get('entity_id') else 'unknown'
                        by_type.setdefault(etype, []).append(issue)
                    
                    # Add summary by type
                    for etype, issues in by_type.items():
                        type_icon = {"automation": "🤖", "script": "📜", "scene": "🎨"}.get(etype, "⚠️")
                        message_parts.append(f"{type_icon} **{etype.capitalize()}**: {len(issues)} issue(s)")
                    
                    message_parts.append("\n**Détails:**")
                    
                    # Add details for each issue (max 5)
                    for i, issue in enumerate(new_issues[:5], 1):
                        severity = issue.get('severity', 'low')
                        severity_icon = "🔴" if severity == "high" else ("🟠" if severity == "medium" else "🔵")
                        alias = issue.get('alias', issue.get('entity_id', 'Inconnu'))
                        msg_preview = issue.get('message', '')[:80]
                        message_parts.append(f"\n{i}. {severity_icon} **{alias}**\n   └─ {msg_preview}...")
                    
                    if len(new_issues) > 5:
                        message_parts.append(f"\n\n*...et {len(new_issues) - 5} autre(s) issue(s)*")
                    
                    message_parts.append("\n\n---\n*🔍 Signalé par H.A.C.A - Home Assistant Config Auditor*")
                    message = "\n".join(message_parts)
                
                # Fire a custom event for the panel to catch
                hass.bus.async_fire("haca_new_issues_detected", {
                    "count": len(new_issues),
                    "issues": new_issues[:10]  # Send max 10 issues
                })
                
                # Also create persistent notification
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": title,
                        "message": message,
                        "notification_id": "haca_new_issues"
                    }
                )
                
                # Update known issues
                for issue in current_issues:
                    known_issues.add(_get_issue_signature(issue))
                await hass.async_add_executor_job(_save_known_issues, known_issues)

                # Update coordinator data
                current_data = coordinator.data or {}
                updated_data = {
                    **current_data,
                    "automation_issues": len(automation_analyzer.automation_issues),
                    "script_issues": len(automation_analyzer.script_issues),
                    "scene_issues": len(automation_analyzer.scene_issues),
                    "automation_issue_list": automation_analyzer.automation_issues,
                    "script_issue_list": automation_analyzer.script_issues,
                    "scene_issue_list": automation_analyzer.scene_issues,
                }
                
                # Recalculate health score (with all 4 categories)
                all_auto = updated_data.get("automation_issue_list", [])
                all_entity = updated_data.get("entity_issue_list", [])
                all_perf = updated_data.get("performance_issue_list", [])
                all_sec = updated_data.get("security_issue_list", [])
                updated_data["health_score"] = calculate_health_score(all_auto, all_entity, all_perf, all_sec)
                
                coordinator.async_set_updated_data(updated_data)
            else:
                # No new issues, but update known issues anyway
                for issue in current_issues:
                    known_issues.add(_get_issue_signature(issue))
                await hass.async_add_executor_job(_save_known_issues, known_issues)
        
        # Listen for automation/script/scene reload events
        @callback
        def _handle_automation_reloaded(event):
            """Handle automation reloaded event."""
            _LOGGER.debug("Automation reloaded event received")
            hass.async_create_task(_check_for_new_issues("automation"))
        
        @callback
        def _handle_script_reloaded(event):
            """Handle script reloaded event."""
            _LOGGER.debug("Script reloaded event received")
            hass.async_create_task(_check_for_new_issues("script"))
        
        @callback
        def _handle_scene_reloaded(event):
            """Handle scene reloaded event."""
            _LOGGER.debug("Scene reloaded event received")
            hass.async_create_task(_check_for_new_issues("scene"))
        
        # Subscribe to events
        hass.bus.async_listen("automation_reloaded", _handle_automation_reloaded)
        hass.bus.async_listen("script_reloaded", _handle_script_reloaded)
        hass.bus.async_listen("scene_reloaded", _handle_scene_reloaded)
        
        # Also listen for core config changed (broader catch)
        @callback
        def _handle_core_config_changed(event):
            """Handle core config changed - delayed check."""
            _LOGGER.debug("Core config changed, scheduling issue check")
            # Delay to allow config to settle
            hass.loop.call_later(5, lambda: hass.async_create_task(_check_for_new_issues()))
        
        hass.bus.async_listen("core_config_updated", _handle_core_config_changed)
        
        # Initial population of known issues
        current_data = coordinator.data or {}
        known_issues = set()
        for issue in current_data.get("automation_issue_list", []):
            known_issues.add(_get_issue_signature(issue))
        for issue in current_data.get("script_issue_list", []):
            known_issues.add(_get_issue_signature(issue))
        for issue in current_data.get("scene_issue_list", []):
            known_issues.add(_get_issue_signature(issue))
        for issue in current_data.get("entity_issue_list", []):
            known_issues.add(_get_issue_signature(issue))
        await hass.async_add_executor_job(_save_known_issues, known_issues)

        _LOGGER.info("Real-time issue detection enabled")
    
    # Setup realtime detection after first refresh
    hass.async_create_task(setup_realtime_detection())
    
    _LOGGER.info("%s v%s setup complete - All 5 modules loaded", NAME, VERSION)
    return True


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Setup all services."""
    
    async def handle_scan_all(call: ServiceCall) -> None:
        """Handle scan_all service."""
        _LOGGER.info("Starting full scan in background")
        
        data = hass.data[DOMAIN][entry.entry_id]
        coordinator = data["coordinator"]
        
        # Refresh in background to avoid blocking and timing out the service call
        hass.async_create_task(coordinator.async_refresh())
        
        # Return immediately
    
    async def handle_scan_automations(call: ServiceCall) -> None:
        """Handle scan_automations service."""
        _LOGGER.info("Scanning automations")
        
        data = hass.data[DOMAIN][entry.entry_id]
        automation_analyzer = data["automation_analyzer"]
        coordinator = data["coordinator"]
        
        async def _run_scan():
            await automation_analyzer.analyze_all()
            
            # Mettre à jour le coordinator avec les nouvelles données séparées
            current_data = coordinator.data or {}
            updated_data = {
                **current_data,
                "automation_issues": len(automation_analyzer.automation_issues),
                "automation_issue_list": automation_analyzer.automation_issues,
                "script_issues": len(automation_analyzer.script_issues),
                "script_issue_list": automation_analyzer.script_issues,
                "scene_issues": len(automation_analyzer.scene_issues),
                "scene_issue_list": automation_analyzer.scene_issues,
                "blueprint_issues": len(automation_analyzer.blueprint_issues),
                "blueprint_issue_list": automation_analyzer.blueprint_issues,
            }
            
            # Recalculer le health_score avec les 4 catégories
            auto_issues = updated_data.get("automation_issue_list", [])
            entity_issues = updated_data.get("entity_issue_list", [])
            perf_issues = updated_data.get("performance_issue_list", [])
            sec_issues = updated_data.get("security_issue_list", [])
            
            updated_data["health_score"] = calculate_health_score(auto_issues, entity_issues, perf_issues, sec_issues)
            updated_data["total_issues"] = (
                len(auto_issues)
                + len(updated_data.get("script_issue_list", []))
                + len(updated_data.get("scene_issue_list", []))
                + len(updated_data.get("blueprint_issue_list", []))
                + len(entity_issues) + len(perf_issues) + len(sec_issues)
            )
            
            coordinator.async_set_updated_data(updated_data)
        
        hass.async_create_task(_run_scan())
    
    async def handle_scan_entities(call: ServiceCall) -> None:
        """Handle scan_entities service."""
        _LOGGER.info("Scanning entities")
        
        data = hass.data[DOMAIN][entry.entry_id]
        entity_analyzer = data["entity_analyzer"]
        automation_analyzer = data["automation_analyzer"]
        coordinator = data["coordinator"]
        
        async def _run_scan():
            issues = await entity_analyzer.analyze_all(
                automation_analyzer._automation_configs,
                automation_analyzer._script_configs,
            )
            
            # Mettre à jour le coordinator avec les nouvelles données
            current_data = coordinator.data or {}
            updated_data = {
                **current_data,
                "entity_issues": len(issues),
                "entity_issue_list": issues,
            }
            
            # Recalculer le health_score
            auto_issues = updated_data.get("automation_issue_list", [])
            entity_issues = updated_data.get("entity_issue_list", [])
            perf_issues = updated_data.get("performance_issue_list", [])
            sec_issues = updated_data.get("security_issue_list", [])
            
            updated_data["health_score"] = calculate_health_score(auto_issues, entity_issues, perf_issues, sec_issues)
            updated_data["total_issues"] = (
                len(updated_data.get("automation_issue_list", []))
                + len(updated_data.get("script_issue_list", []))
                + len(updated_data.get("scene_issue_list", []))
                + len(updated_data.get("blueprint_issue_list", []))
                + len(entity_issues) + len(perf_issues) + len(sec_issues)
            )
            
            coordinator.async_set_updated_data(updated_data)

        hass.async_create_task(_run_scan())
    
    # Module 4: Report services
    if MODULE_4_COMPLIANCE_REPORT:
        async def handle_generate_report(call: ServiceCall) -> None:
            """Handle generate_report service."""
            _LOGGER.info("Generating report")
            
            data = hass.data[DOMAIN][entry.entry_id]
            coordinator = data["coordinator"]
            report_gen = data["report_generator"]
            
            # Get the current language from Home Assistant
            language = hass.config.language or "en"
            
            summary = {
                "health_score": coordinator.data.get("health_score", 0),
                "automation_issues": coordinator.data.get("automation_issues", 0),
                "entity_issues": coordinator.data.get("entity_issues", 0),
                "total_issues": coordinator.data.get("total_issues", 0),
                "script_issues": coordinator.data.get("script_issues", 0),
                "scene_issues": coordinator.data.get("scene_issues", 0),
                "performance_issues": coordinator.data.get("performance_issues", 0),
                "security_issues": coordinator.data.get("security_issues", 0),
            }
            
            # Use generate_all_reports to ensure all formats have the same timestamp
            result = await report_gen.generate_all_reports(
                summary,
                coordinator.data.get("automation_issue_list", []),
                coordinator.data.get("entity_issue_list", []),
                language=language
            )
            
            _LOGGER.info("Reports generated with timestamp: %s", result.get("timestamp"))
        
        async def handle_list_reports(call: ServiceCall) -> dict:
            """Handle list_reports service."""
            data = hass.data[DOMAIN][entry.entry_id]
            report_gen = data["report_generator"]
            reports = report_gen.list_reports()
            return {"reports": reports, "count": len(reports)}

        async def handle_get_report_content(call: ServiceCall) -> dict:
            """Handle get_report_content service."""
            filename = call.data.get("filename")
            data = hass.data[DOMAIN][entry.entry_id]
            report_gen = data["report_generator"]
            
            result = await report_gen.get_report_content(filename)
            if not result:
                return {"success": False, "error": f"Report '{filename}' not found"}
                
            return {"success": True, **result}
        
        async def handle_delete_report(call: ServiceCall) -> dict:
            """Handle delete_report service."""
            session_id = call.data.get("session_id")
            data = hass.data[DOMAIN][entry.entry_id]
            report_gen = data["report_generator"]
            
            result = await report_gen.delete_report_session(session_id)
            
            if result.get("success"):
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "🗑️ Report Deleted",
                        "message": f"Deleted {result.get('deleted_count', 0)} report file(s)",
                        "notification_id": "haca_report_deleted"
                    }
                )
            
            return result
    
    # Module 5: Refactoring services
    if MODULE_5_REFACTORING_ASSISTANT:
        async def handle_preview_device_id(call: ServiceCall) -> dict:
            """Handle preview_device_id service."""
            automation_id = call.data.get("automation_id")
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.preview_device_id_fix(automation_id)
            
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Preview: device_id Fix",
                    "message": f"Automation: {result.get('alias', automation_id)}\n"
                              f"Changes: {result.get('changes_count', 0)}",
                    "notification_id": "haca_preview"
                }
            )
            
            return result
        
        async def handle_fix_device_id(call: ServiceCall) -> dict:
            """Handle fix_device_id service."""
            automation_id = call.data.get("automation_id")
            dry_run = call.data.get("dry_run", False)
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.apply_device_id_fix(automation_id, dry_run=dry_run)
            
            if result.get("success"):
                title = "✅ Fix Applied" if not dry_run else "🔍 Dry Run Fix"
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": title,
                        "message": result.get("message", ""),
                        "notification_id": "haca_fix"
                    }
                )
            
            return result
        
        async def handle_preview_mode(call: ServiceCall) -> dict:
            """Handle preview_mode service."""
            automation_id = call.data.get("automation_id")
            new_mode = call.data.get("mode")
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.preview_mode_fix(automation_id, new_mode)
            
            await hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Preview: Mode Change",
                    "message": f"Automation: {result.get('alias', automation_id)}\n"
                              f"New Mode: {new_mode}",
                    "notification_id": "haca_preview"
                }
            )
            
            return result
        
        async def handle_fix_mode(call: ServiceCall) -> dict:
            """Handle fix_mode service."""
            automation_id = call.data.get("automation_id")
            new_mode = call.data.get("mode")
            dry_run = call.data.get("dry_run", False)
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.apply_mode_fix(automation_id, new_mode, dry_run=dry_run)
            
            if result.get("success"):
                title = "✅ Mode Changed" if not dry_run else "🔍 Dry Run Mode"
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": title,
                        "message": result.get("message", ""),
                        "notification_id": "haca_fix"
                    }
                )
            
            return result
            
        async def handle_preview_template(call: ServiceCall) -> dict:
            """Handle preview_template service."""
            automation_id = call.data.get("automation_id")
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.preview_template_fix(automation_id)
            return result
            
        async def handle_fix_template(call: ServiceCall) -> dict:
            """Handle fix_template service."""
            automation_id = call.data.get("automation_id")
            dry_run = call.data.get("dry_run", False)
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.apply_template_fix(automation_id, dry_run=dry_run)
            return result
        
        async def handle_list_backups(call: ServiceCall) -> dict:
            """Handle list_backups service."""
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            backups = await refactoring.list_backups()
            return {"backups": backups, "count": len(backups)}
            
        async def handle_create_backup(call: ServiceCall) -> dict:
            """Handle create_backup service."""
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.create_backup()
            
            if result.get("success"):
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "✅ Backup Created",
                        "message": result.get("message", ""),
                        "notification_id": "haca_backup"
                    }
                )
            return result
        
        async def handle_restore_backup(call: ServiceCall) -> dict:
            """Handle restore_backup service."""
            backup_path = call.data.get("backup_path")
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.restore_backup(backup_path)
            
            if result.get("success"):
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "✅ Backup Restored",
                        "message": result.get("message", ""),
                        "notification_id": "haca_restore"
                    }
                )
            
            return result
        
        async def handle_delete_backup(call: ServiceCall) -> dict:
            """Handle delete_backup service."""
            backup_path = call.data.get("backup_path")
            
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            
            result = await refactoring.delete_backup(backup_path)
            
            if result.get("success"):
                await hass.services.async_call(
                    "persistent_notification",
                    "create",
                    {
                        "title": "🗑️ Backup Deleted",
                        "message": result.get("message", ""),
                        "notification_id": "haca_backup_deleted"
                    }
                )
            
            return result
        
        async def handle_purge_ghosts(call: ServiceCall) -> dict:
            """Handle purge_ghosts service."""
            dry_run = call.data.get("dry_run", True)
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            return await refactoring.purge_orphaned_entities(dry_run=dry_run)
            
        async def handle_fuzzy_suggestions(call: ServiceCall) -> dict:
            """Handle get_fuzzy_suggestions service."""
            entity_id = call.data.get("entity_id")
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            suggestions = await refactoring.get_fuzzy_suggestions(entity_id)
            return {"suggestions": suggestions}
            
        async def handle_suggest_description_ai(call: ServiceCall) -> dict:
            """Handle suggest_description_ai service."""
            entity_id = call.data.get("entity_id")
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            return await refactoring.suggest_description_ai(entity_id)
            
        async def handle_fix_description(call: ServiceCall) -> dict:
            """Handle fix_description service."""
            entity_id = call.data.get("entity_id")
            description = call.data.get("description")
            data = hass.data[DOMAIN][entry.entry_id]
            refactoring = data["refactoring_assistant"]
            return await refactoring.apply_description_fix(entity_id, description)
    
    # Register services
    hass.services.async_register(DOMAIN, SERVICE_SCAN_ALL, handle_scan_all, schema=vol.Schema({}))
    hass.services.async_register(DOMAIN, SERVICE_SCAN_AUTOMATIONS, handle_scan_automations, schema=vol.Schema({}))
    hass.services.async_register(DOMAIN, SERVICE_SCAN_ENTITIES, handle_scan_entities, schema=vol.Schema({}))
    
    if MODULE_4_COMPLIANCE_REPORT:
        hass.services.async_register(DOMAIN, SERVICE_GENERATE_REPORT, handle_generate_report, schema=vol.Schema({}))
        hass.services.async_register(
            DOMAIN, SERVICE_LIST_REPORTS, handle_list_reports,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, SERVICE_GET_REPORT_CONTENT, handle_get_report_content,
            schema=vol.Schema({vol.Required("filename"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, "delete_report", handle_delete_report,
            schema=vol.Schema({vol.Required("session_id"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )
    
    if MODULE_5_REFACTORING_ASSISTANT:
        hass.services.async_register(
            DOMAIN, SERVICE_PREVIEW_DEVICE_ID, handle_preview_device_id,
            schema=vol.Schema({vol.Required("automation_id"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, SERVICE_FIX_DEVICE_ID, handle_fix_device_id,
            schema=vol.Schema({
                vol.Required("automation_id"): cv.string,
                vol.Optional("dry_run", default=False): cv.boolean
            }),
            supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREVIEW_MODE, handle_preview_mode,
            schema=vol.Schema({
                vol.Required("automation_id"): cv.string,
                vol.Required("mode"): vol.In(["single", "restart", "queued", "parallel"])
            }),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, SERVICE_FIX_MODE, handle_fix_mode,
            schema=vol.Schema({
                vol.Required("automation_id"): cv.string,
                vol.Required("mode"): vol.In(["single", "restart", "queued", "parallel"]),
                vol.Optional("dry_run", default=False): cv.boolean
            }),
            supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PREVIEW_TEMPLATE, handle_preview_template,
            schema=vol.Schema({vol.Required("automation_id"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, "suggest_description_ai", handle_suggest_description_ai,
            schema=vol.Schema({vol.Required("entity_id"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, "fix_description", handle_fix_description,
            schema=vol.Schema({
                vol.Required("entity_id"): cv.string,
                vol.Required("description"): cv.string
            }),
            supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN, SERVICE_FIX_TEMPLATE, handle_fix_template,
            schema=vol.Schema({
                vol.Required("automation_id"): cv.string,
                vol.Optional("dry_run", default=False): cv.boolean
            }),
            supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN, SERVICE_LIST_BACKUPS, handle_list_backups,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, "create_backup", handle_create_backup,
            schema=vol.Schema({}),
            supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN, SERVICE_RESTORE_BACKUP, handle_restore_backup,
            schema=vol.Schema({vol.Required("backup_path"): cv.string}),
            supports_response=SupportsResponse.OPTIONAL
        )
        hass.services.async_register(
            DOMAIN, "delete_backup", handle_delete_backup,
            schema=vol.Schema({vol.Required("backup_path"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, SERVICE_PURGE_GHOSTS, handle_purge_ghosts,
            schema=vol.Schema({vol.Optional("dry_run", default=True): cv.boolean}),
            supports_response=SupportsResponse.ONLY
        )
        hass.services.async_register(
            DOMAIN, SERVICE_FUZZY_SUGGESTIONS, handle_fuzzy_suggestions,
            schema=vol.Schema({vol.Required("entity_id"): cv.string}),
            supports_response=SupportsResponse.ONLY
        )

    async def handle_explain_issue(call: ServiceCall) -> dict:
        """Handle explain_issue_ai service."""
        issue_data = call.data.get("issue")
        explanation = await explain_issue_ai(hass, issue_data)
        return {"explanation": explanation}

    hass.services.async_register(
        DOMAIN, "explain_issue_ai", handle_explain_issue,
        schema=vol.Schema({vol.Required("issue"): dict}),
        supports_response=SupportsResponse.ONLY
    )
    
    _LOGGER.info("All services registered")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading %s", NAME)
    
    # Unregister panel when last instance is removed
    if len(hass.config_entries.async_entries(DOMAIN)) == 1:
        await async_unregister_panel(hass)
        _LOGGER.info("Panel unregistered - last instance removed")
    
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry - Clean Uninstall."""
    _LOGGER.info("Tracer: Removing %s - Clean Uninstall Initialized", NAME)

    # 0. Ensure panel is unregistered
    await async_unregister_panel(hass)

    # 1. Paths
    reports_path = hass.config.path(REPORTS_DIR)
    backups_path = hass.config.path(BACKUP_DIR)
    history_path = hass.config.path(HISTORY_FILE)
    integration_path = Path(__file__).parent

    # 2. Helper functions for safe deletion
    def safe_remove_dir(path_str: str | Path):
        path = Path(path_str)
        if path.exists() and path.is_dir():
            try:
                shutil.rmtree(path)
                _LOGGER.info("✅ Removed directory: %s", path)
            except Exception as e:
                _LOGGER.error("❌ Failed to remove directory %s: %s", path, e)

    def safe_remove_file(path_str: str | Path):
        path = Path(path_str)
        if path.exists() and path.is_file():
            try:
                os.remove(path)
                _LOGGER.info("✅ Removed file: %s", path)
            except Exception as e:
                _LOGGER.error("❌ Failed to remove file %s: %s", path, e)

    # 3. Delete data directories and files
    safe_remove_dir(reports_path)
    safe_remove_dir(backups_path)
    safe_remove_file(history_path)

    # 4. Delete the integration folder itself
    _LOGGER.info("🗑️ Removing technical integration folder: %s", integration_path)
    safe_remove_dir(integration_path)

    # 5. Persistent notification
    await hass.services.async_call(
        "persistent_notification",
        "create",
        {
            "title": f"{NAME} Uninstalled",
            "message": "The integration and all its data (reports, backups) have been cleanly removed. Please restart Home Assistant.",
            "notification_id": "haca_uninstall_notice"
        }
    )
