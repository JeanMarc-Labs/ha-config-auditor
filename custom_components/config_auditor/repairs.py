"""H.A.C.A — HA Repairs Framework integration.

Pushes HIGH severity issues from HACA into the native HA Repairs panel
(Settings → System → Repairs) so users see critical problems without
needing to open the HACA custom panel.

Called after each coordinator refresh. Issues that are resolved on the
next scan are automatically removed from the Repairs panel.

Requires HA 2023.1+ (homeassistant.helpers.issue_registry).
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Maximum number of issues pushed to Repairs (avoid flooding)
MAX_REPAIR_ISSUES = 15

# ⚠️  Every issue is pushed with is_fixable=False, on purpose.
#
# HA only shows a working "Fix" button when the integration's repairs platform
# exposes `async_create_fix_flow()` returning a RepairsFlow. This module used to
# ship a `HacaFixFlow` for a handful of simple types (no_description, no_alias,
# compliance_*_no_description); it was removed along with the rest of the old
# repairs platform (see tests/test_repairs.py, skipped for that reason) and this
# file was reduced to a one-way push into the Repairs panel.
#
# Marking an issue fixable without that flow gives the user a "Fix" button that
# cannot open anything — HA fails to load the flow handler. Fixes live in the
# HACA panel, which the description links to.
#
# If a fix flow is ever reintroduced, restore `async_create_fix_flow` here first,
# then re-enable per-type fixability — never the other way round.


def _issue_key(issue: dict[str, Any]) -> str:
    """Generate a stable unique key for a HACA issue."""
    entity_id = issue.get("entity_id", "unknown")
    issue_type = issue.get("type", "unknown")
    return f"{entity_id}_{issue_type}"


def _readable_type(issue_type: str) -> str:
    """Convert a snake_case issue type to a human-readable string.

    e.g. 'device_id_in_trigger' → 'Device ID in trigger'
    """
    return issue_type.replace("_", " ").capitalize()


async def async_update_repairs(
    hass: HomeAssistant,
    coordinator_data: dict[str, Any],
) -> None:
    """Sync HACA HIGH issues with HA Repairs panel.

    - Deletes the HACA entries the current scan no longer reports.
    - Creates or refreshes an entry for every HIGH issue it does report.
    """
    try:
        from homeassistant.helpers import issue_registry as ir
    except ImportError:
        # HA version too old — silently skip
        _LOGGER.debug("[HACA Repairs] issue_registry not available — skipping")
        return

    if not coordinator_data:
        return

    # ── Step 1: Collect all HIGH severity issues across all categories ────
    all_high_issues: dict[str, dict[str, Any]] = {}
    for list_key in [
        "automation_issue_list", "script_issue_list", "scene_issue_list",
        "blueprint_issue_list", "entity_issue_list", "helper_issue_list",
        "performance_issue_list", "security_issue_list", "dashboard_issue_list",
    ]:
        for issue in coordinator_data.get(list_key, []):
            if issue.get("severity") == "high":
                key = _issue_key(issue)
                all_high_issues[key] = issue

    # Limit to avoid flooding the Repairs panel
    selected = dict(list(all_high_issues.items())[:MAX_REPAIR_ISSUES])
    reported = {f"haca_{key}" for key in selected}

    # ── Step 2: Remove the HACA repairs this scan no longer reports ───────
    # Only those. Deleting an entry that is still reported and creating it
    # again fires two issue-registry events per scan, which retriggers every
    # automation listening to them, and drops the user's dismissal, so an
    # ignored issue comes back. Entries kept from before an HA restart are in
    # the registry too, so a problem resolved meanwhile is still removed.
    try:
        registry = ir.async_get(hass)
        resolved = [
            (domain, issue_id)
            for (domain, issue_id) in list(registry.issues)
            if domain == DOMAIN and issue_id not in reported
        ]
        for domain, issue_id in resolved:
            ir.async_delete_issue(hass, domain, issue_id)
        if resolved:
            _LOGGER.debug("[HACA Repairs] Removed %d resolved repair entries", len(resolved))
    except Exception as exc:
        _LOGGER.debug("[HACA Repairs] Could not remove resolved issues: %s", exc)

    # ── Step 3: Create or refresh every reported entry ────────────────────
    # Called for entries that already exist too — never skip them. HA reloads
    # a non-persistent issue as *inactive* after a restart (still in the
    # registry, hidden from the Repairs panel) and only this call makes it
    # active again. It also updates an entry whose text changed, a renamed
    # automation for instance. On an identical entry it changes nothing and
    # fires no event, and an update keeps the user's dismissal.
    for key, issue in selected.items():
        issue_id = f"haca_{key}"

        entity_name = issue.get("alias") or issue.get("entity_id", "?")
        issue_type = issue.get("type", "unknown")
        message_text = (issue.get("message") or "")[:200]
        recommendation = (issue.get("recommendation") or "")[:200]

        try:
            # Build descriptive message with type explanation + recommendation
            description_parts = []
            if message_text:
                description_parts.append(message_text)
            if recommendation:
                description_parts.append(f"Recommendation: {recommendation}")

            ir.async_create_issue(
                hass,
                domain=DOMAIN,
                issue_id=issue_id,
                is_fixable=False,  # see the module-level note — no fix flow exists
                is_persistent=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="generic_high_issue",
                translation_placeholders={
                    "entity": entity_name,
                    "type": _readable_type(issue_type),
                    "message": "\n\n".join(description_parts),
                },
            )
        except Exception as exc:
            _LOGGER.debug("[HACA Repairs] Could not create issue %s: %s", issue_id, exc)

    if selected:
        _LOGGER.debug(
            "[HACA Repairs] Synced %d HIGH issue(s) to HA Repairs panel",
            len(selected),
        )
