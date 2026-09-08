"""Automation Optimizer for H.A.C.A — Module 15.

Provides active AI-powered rewriting of automations:
  - Split God automations into specialised automations
  - Modernise deprecated templates and syntax
  - Match against installed blueprints
  - Optimise mode, conditions, actions
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant

from .const import BACKUP_DIR
from .translation_utils import notification_ts as _ts
from .yaml_sources import iter_domain_files
from .yaml_writer import (
    EditScan,
    create_backup,
    scan_list_domain_for_edit,
    write_back,
)

_LOGGER = logging.getLogger(__name__)

# ── Deprecated template patterns to detect ───────────────────────────────────
DEPRECATED_PATTERNS = [
    # is_state / is_state_attr template conditions → use state: condition
    (r"\{\{-?\s*is_state\s*\(", "is_state() template → use 'condition: state'"),
    (r"\{\{-?\s*is_state_attr\s*\(", "is_state_attr() template → use 'condition: state' with attribute"),
    # states.domain → should use states() helper or trigger
    (r"states\.[a-z_]+\.[a-z_]+\.state", "states.domain.entity.state → use states('entity_id')"),
    # now() / utcnow() in templates
    (r"\{\{-?\s*now\(\)", "now() in template → use 'time' trigger or condition instead"),
    # trigger.entity_id (deprecated in newer HA)
    (r"trigger\.entity_id", "trigger.entity_id → prefer trigger.to_state.entity_id"),
    # loop over states | selectattr without domain filter
    (r"states\s*\|\s*selectattr", "states | selectattr without domain → very expensive"),
]


class AutomationOptimizer:
    """AI-powered automation optimizer."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._config_dir = str(hass.config.config_dir)
        self._backup_dir = Path(hass.config.config_dir) / BACKUP_DIR
        self._backup_dir.mkdir(exist_ok=True)

    # ── Source resolution ──────────────────────────────────────────────────────

    def _find_owning_file(self, entity_id: str) -> EditScan:
        """Locate the YAML file that actually holds one automation.

        With a split config the entry lives in one of several files, so writes
        must land on that file rather than on <config>/automations.yaml, which
        HA may not even read. The file comes back open for editing, so
        :meth:`_write_automations` can replace the entry without flattening the
        comments around the automations that share the file.

        A file carrying HA tags (``!secret``, ``!include``) is skipped rather
        than rewritten with those tags lost — see :mod:`yaml_writer`.
        """
        slug = entity_id.split(".", 1)[-1] if "." in entity_id else entity_id

        def _matches(item: dict) -> bool:
            item_id = str(item.get("id", ""))
            item_alias = (item.get("alias") or "").lower().replace(" ", "_")
            return item_id == slug or item_alias == slug or item.get("alias") == slug

        return scan_list_domain_for_edit(
            self._config_dir, "automation", "automations.yaml", _matches
        )

    # ── Public API ─────────────────────────────────────────────────────────────

    async def optimize(
        self,
        entity_id: str,
        issues: list[dict],
        complexity_scores: list[dict],
    ) -> dict[str, Any]:
        """Run full AI optimisation pipeline.

        Returns
        -------
        {
          "entity_id":           str,
          "alias":               str,
          "original_yaml":       str,
          "analysis":            str,   — plain-text diagnosis
          "split_automations":   str,   — YAML for multiple specialised automations
          "modernised_yaml":     str,   — single automation with deprecated syntax fixed
          "blueprint_match":     dict | None,  — {path, name, reason, inputs_yaml}
          "optimised_yaml":      str,   — best single-file result (may == modernised)
          "detected_patterns":   list[str],
          "issues_found":        list[str],
          "has_split":           bool,
          "has_blueprint":       bool,
          "score":               int,
        }
        """
        # ── 1. Load YAML ──────────────────────────────────────────────────────
        original_yaml = await self._load_yaml(entity_id)
        alias = entity_id
        if original_yaml:
            try:
                parsed = yaml.safe_load(original_yaml)
                alias = parsed.get("alias", entity_id) if isinstance(parsed, dict) else entity_id
            except Exception:
                pass

        # ── 2. Static analysis ────────────────────────────────────────────────
        detected_patterns = self._detect_deprecated(original_yaml)
        issues_found = [i.get("message", "") for i in issues if i.get("entity_id") == entity_id]

        score = 0
        for row in complexity_scores:
            if row.get("entity_id") == entity_id:
                score = row.get("score", 0)
                break

        # ── 3. Scan available blueprints ──────────────────────────────────────
        available_blueprints = await self._scan_blueprints()

        # ── 4. Build AI prompt ────────────────────────────────────────────────
        prompt = self._build_prompt(
            entity_id=entity_id,
            alias=alias,
            original_yaml=original_yaml,
            score=score,
            issues=issues_found,
            patterns=detected_patterns,
            blueprints=available_blueprints,
        )

        # ── 5. Call AI ────────────────────────────────────────────────────────
        raw_reply = await self._call_ai(prompt)

        # ── 6. Parse structured response ──────────────────────────────────────
        parsed = self._parse_reply(raw_reply)

        return {
            "entity_id":         entity_id,
            "alias":             alias,
            "original_yaml":     original_yaml,
            "analysis":          parsed.get("analysis", ""),
            "split_automations": parsed.get("split_automations", ""),
            "modernised_yaml":   parsed.get("modernised_yaml", ""),
            "blueprint_match":   parsed.get("blueprint_match"),
            "optimised_yaml":    parsed.get("optimised_yaml", ""),
            "detected_patterns": detected_patterns,
            "issues_found":      issues_found,
            "has_split":         bool(parsed.get("split_automations", "").strip()),
            "has_blueprint":     bool(parsed.get("blueprint_match")),
            "score":             score,
        }

    async def apply(self, entity_id: str, new_yaml: str) -> dict[str, Any]:
        """Apply optimised YAML — backup + write atomically.

        For 'split' results the new_yaml contains multiple documents
        separated by '---'.  Each becomes a new automation (old one removed).

        Security
        --------
        - YAML is parsed with ``yaml.safe_load_all`` (no Python object
          constructors, no arbitrary code execution).
        - Each document must be a plain dict — raw strings, lists, or other
          types are rejected to prevent injecting unexpected config.
        - Each dict must contain at least one of the core automation keys
          (``triggers``/``trigger``, ``actions``/``action``) so that garbage
          or copied non-automation YAML is caught before it reaches the file.
        """
        try:
            # 1. Parse — safe_load_all never executes Python constructors
            docs = list(yaml.safe_load_all(new_yaml))
            docs = [d for d in docs if d]  # strip None (empty doc separators)
            if not docs:
                return {"success": False, "error": _ts(self.hass, "optimizer", "yaml_empty")}
        except yaml.YAMLError as e:
            return {"success": False, "error": _ts(self.hass, "optimizer", "yaml_invalid", error=e)}

        # 2. Structural validation — every document must be a dict that looks
        #    like an automation (has triggers/actions keys).
        REQUIRED_KEYS = {"triggers", "trigger", "actions", "action"}
        for i, doc in enumerate(docs):
            if not isinstance(doc, dict):
                return {
                    "success": False,
                    "error": _ts(
                        self.hass, "optimizer", "not_a_mapping",
                        index=i + 1, kind=type(doc).__name__,
                    ),
                }
            if not REQUIRED_KEYS.intersection(doc.keys()):
                return {
                    "success": False,
                    "error": _ts(
                        self.hass, "optimizer", "not_an_automation", index=i + 1,
                    ),
                }

        backup_path = await self._create_backup(entity_id)

        try:
            await self.hass.async_add_executor_job(
                self._write_automations, entity_id, docs
            )
            return {
                "success":     True,
                "message":     _ts(self.hass, "optimizer", "written", count=len(docs)),
                "backup_path": str(backup_path),
                "count":       len(docs),
            }
        except Exception as e:
            _LOGGER.error("AutomationOptimizer.apply failed: %s", e)
            return {"success": False, "error": str(e)}

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _load_yaml(self, entity_id: str) -> str:
        """Load raw YAML for one automation, wherever its file lives."""

        def _read() -> str:
            scan = self._find_owning_file(entity_id)
            if not scan.found:
                return ""
            buffer = io.StringIO()
            scan.yaml.dump(scan.entry, buffer)
            return buffer.getvalue()

        try:
            return await self.hass.async_add_executor_job(_read)
        except Exception as e:
            _LOGGER.warning("Could not load YAML for %s: %s", entity_id, e)
            return ""

    def _detect_deprecated(self, yaml_text: str) -> list[str]:
        """Return list of deprecated pattern descriptions found in YAML."""
        found = []
        for pattern, desc in DEPRECATED_PATTERNS:
            if re.search(pattern, yaml_text or ""):
                found.append(desc)
        return found

    async def _scan_blueprints(self) -> list[dict]:
        """Scan the blueprints/automation directory and return metadata."""
        bp_dir = Path(self.hass.config.config_dir) / "blueprints" / "automation"

        def _read_blueprints() -> list[dict]:
            result = []
            if not bp_dir.exists():
                return result
            for fp in sorted(bp_dir.rglob("*.yaml"))[:30]:  # cap at 30
                try:
                    raw = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
                    bp_meta = raw.get("blueprint", {})
                    result.append({
                        "path":        str(fp.relative_to(bp_dir)),
                        "name":        bp_meta.get("name", fp.stem),
                        "description": bp_meta.get("description", "")[:200],
                        "domain":      bp_meta.get("domain", "automation"),
                    })
                except Exception:
                    pass
            return result

        try:
            return await self.hass.async_add_executor_job(_read_blueprints)
        except Exception as e:
            _LOGGER.debug("Blueprint scan error: %s", e)
            return []

    def _build_prompt(
        self,
        entity_id: str,
        alias: str,
        original_yaml: str,
        score: int,
        issues: list[str],
        patterns: list[str],
        blueprints: list[dict],
    ) -> str:
        yaml_block = original_yaml[:4000] if original_yaml else "(YAML unavailable)"

        issues_block = "\n".join(f"  - {i}" for i in issues) if issues else "  (none)"
        patterns_block = "\n".join(f"  - {p}" for p in patterns) if patterns else "  (none)"

        bp_lines = "\n".join(
            f"  - [{bp['path']}] {bp['name']} — {bp['description'][:100]}"
            for bp in blueprints
        ) if blueprints else "  (no blueprint installed)"

        from .translation_utils import resolve_notification_language
        _lang = resolve_notification_language(self.hass)
        try:
            from . import _TS_CACHE  # noqa: PLC0415
            _cache = _TS_CACHE.get(_lang) or _TS_CACHE.get("en") or {}
            _ap = _cache.get("ai_prompts", {})
        except Exception:
            _ap = {}
        _tmpl = _ap.get("optimizer_system", "Optimise this automation:\n\n{content}")
        content = (
            f"Entity: {entity_id}\n"
            f"Alias: {alias}\n"
            f"Score: {score}\n\n"
            f"YAML:\n{yaml_block}\n\n"
            f"Issues:\n{issues_block}\n\n"
            f"Deprecated patterns:\n{patterns_block}\n\n"
            f"Available blueprints:\n{bp_lines}"
        )
        return _tmpl.format(content=content)

    async def _call_ai(self, prompt: str) -> str:
        """Call AI with automatic provider fallback via shared _async_call_ai."""
        from .conversation import _async_call_ai
        return await _async_call_ai(self.hass, prompt, "HACA Automation Optimizer")

    def _parse_reply(self, reply: str) -> dict[str, Any]:
        """Extract the 4 structured blocks from the AI reply."""
        result: dict[str, Any] = {
            "analysis":          "",
            "split_automations": "",
            "modernised_yaml":   "",
            "blueprint_match":   None,
            "optimised_yaml":    "",
        }
        if not reply:
            return result

        def _extract(tag: str) -> str:
            m = re.search(
                r"```" + tag + r"\s*(.*?)\s*```",
                reply, re.DOTALL | re.IGNORECASE
            )
            return m.group(1).strip() if m else ""

        result["analysis"] = _extract("analysis")

        split = _extract("split_automations")
        if split and "DECOUPAGE_NON_PERTINENT" not in split.upper():
            result["split_automations"] = split

        modern = _extract("modernised_yaml")
        result["modernised_yaml"] = modern
        result["optimised_yaml"] = modern  # default best result

        bp_raw = _extract("blueprint_suggestion")
        if bp_raw and "BLUEPRINT_NON_APPLICABLE" not in bp_raw.upper():
            # Try to extract path + inputs YAML
            path_m = re.search(r"(?:chemin|path)\s*[:\-]\s*([^\n]+)", bp_raw, re.IGNORECASE)
            reason_m = re.search(r"(?:pourquoi|reason|correspond)[^\n]*\n([^\n]+)", bp_raw, re.IGNORECASE)
            yaml_m = re.search(r"```ya?ml\s*(.*?)\s*```", bp_raw, re.DOTALL)
            result["blueprint_match"] = {
                "path":        path_m.group(1).strip() if path_m else "",
                "reason":      reason_m.group(1).strip() if reason_m else bp_raw[:200],
                "inputs_yaml": yaml_m.group(1).strip() if yaml_m else "",
                "raw":         bp_raw,
            }

        # If split exists, prefer it as optimised_yaml
        if result["split_automations"]:
            result["optimised_yaml"] = result["split_automations"]

        return result

    def _write_automations(self, entity_id: str, new_docs: list[dict]) -> None:
        """Replace one automation with new docs, in the file that holds it.

        The entry is deleted from the round-trip document and the replacements
        appended to it, so every other automation in the file keeps its
        comments and its formatting. The backup was taken by the caller.
        """
        scan = self._find_owning_file(entity_id)
        if not scan.found:
            raise ValueError(
                f"Automation '{entity_id}' not found in any file the "
                f"'automation:' key resolves to"
            )

        del scan.document[scan.index]
        scan.document.extend(new_docs)
        write_back(scan.target)

    async def _create_backup(self, entity_id: str | None = None) -> Path:
        """Backup the file about to be written, before any write.

        Through the shared :func:`yaml_writer.create_backup`, so the snapshot is
        named like every other one HACA takes and the panel can restore it. It
        used to be written as ``<stem>_optim_<ts>.yaml``, which the restore path
        could not resolve back to a source file: the listing offered it and the
        restore then refused it.
        """
        def _do() -> Path:
            source: Path | None = None
            if entity_id:
                scan = self._find_owning_file(entity_id)
                source = Path(scan.path) if scan.found else None
            if source is None:
                files = iter_domain_files(
                    self._config_dir, "automation", "automations.yaml"
                )
                source = Path(files[0]) if files else None
            if source is None:
                raise FileNotFoundError("no automation YAML file to back up")
            return Path(create_backup(self._config_dir, str(source)))

        return await self.hass.async_add_executor_job(_do)
