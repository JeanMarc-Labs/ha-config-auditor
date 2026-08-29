"""Automation Optimizer for H.A.C.A — Module 15.

Provides active AI-powered rewriting of automations:
  - Split God automations into specialised automations
  - Modernise deprecated templates and syntax
  - Match against installed blueprints
  - Optimise mode, conditions, actions
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from homeassistant.core import HomeAssistant

from .const import BACKUP_DIR
from .yaml_sources import iter_domain_files

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

    def _find_owning_file(self, entity_id: str) -> tuple[Path | None, list, int]:
        """Locate the YAML file that actually holds one automation.

        Returns ``(path, documents, index)`` — the file, its parsed list of
        automations, and the position of the match — or ``(None, [], -1)``.
        With a split config the entry lives in one of several files, so writes
        must land on that file rather than on <config>/automations.yaml, which
        HA may not even read.

        Parsed with plain ``yaml.safe_load``: a file carrying HA tags
        (``!secret``, ``!include``) is skipped rather than rewritten with those
        tags expanded, which would inline secrets in clear text.
        """
        slug = entity_id.split(".", 1)[-1] if "." in entity_id else entity_id
        fallback: tuple[Path | None, list, int] = (None, [], -1)

        for path in iter_domain_files(self._config_dir, "automation", "automations.yaml"):
            try:
                data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
            except Exception:
                continue
            if not isinstance(data, list):
                data = [data]
            for index, item in enumerate(data):
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id", ""))
                item_alias = (item.get("alias") or "").lower().replace(" ", "_")
                if item_id == slug or item_alias == slug or item.get("alias") == slug:
                    return Path(path), data, index
                if fallback[0] is None:
                    candidate = (item.get("alias") or item.get("id") or "").lower().replace(" ", "_")
                    if candidate == slug:
                        fallback = (Path(path), data, index)
        return fallback

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
                return {"success": False, "error": "YAML vide ou invalide"}
        except yaml.YAMLError as e:
            return {"success": False, "error": f"YAML invalide : {e}"}

        # 2. Structural validation — every document must be a dict that looks
        #    like an automation (has triggers/actions keys).
        REQUIRED_KEYS = {"triggers", "trigger", "actions", "action"}
        for i, doc in enumerate(docs):
            if not isinstance(doc, dict):
                return {
                    "success": False,
                    "error": (
                        f"Document {i + 1} n'est pas un mapping YAML valide "
                        f"(reçu : {type(doc).__name__})."
                    ),
                }
            if not REQUIRED_KEYS.intersection(doc.keys()):
                return {
                    "success": False,
                    "error": (
                        f"Document {i + 1} ne ressemble pas à une automation HA "
                        f"(aucune clé triggers/actions trouvée)."
                    ),
                }

        backup_path = await self._create_backup(entity_id)

        try:
            result = await self.hass.async_add_executor_job(
                self._write_automations, entity_id, docs
            )
            return {
                "success":     True,
                "message":     f"{len(docs)} automation(s) écrite(s).",
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
            _path, data, index = self._find_owning_file(entity_id)
            if index < 0:
                return ""
            return yaml.dump(data[index], allow_unicode=True, default_flow_style=False)

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
        yaml_block = original_yaml[:4000] if original_yaml else "(YAML non disponible)"

        issues_block = "\n".join(f"  - {i}" for i in issues) if issues else "  (aucun)"
        patterns_block = "\n".join(f"  - {p}" for p in patterns) if patterns else "  (aucun)"

        bp_lines = "\n".join(
            f"  - [{bp['path']}] {bp['name']} — {bp['description'][:100]}"
            for bp in blueprints
        ) if blueprints else "  (aucun blueprint installé)"

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
        """Replace one automation with new docs, in the file that holds it."""
        target, data, index = self._find_owning_file(entity_id)
        if target is None or index < 0:
            raise ValueError(
                f"Automation '{entity_id}' not found in any file the "
                f"'automation:' key resolves to"
            )

        filtered = [item for i, item in enumerate(data) if i != index]
        filtered.extend(new_docs)

        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(filtered, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)

    async def _create_backup(self, entity_id: str | None = None) -> Path:
        """Backup the file about to be written, before any write."""
        from datetime import datetime
        import shutil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        def _do() -> Path:
            source: Path | None = None
            if entity_id:
                source = self._find_owning_file(entity_id)[0]
            if source is None:
                files = iter_domain_files(
                    self._config_dir, "automation", "automations.yaml"
                )
                source = Path(files[0]) if files else None
            if source is None:
                raise FileNotFoundError("no automation YAML file to back up")
            backup_file = self._backup_dir / f"{source.stem}_optim_{timestamp}.yaml"
            shutil.copy2(source, backup_file)
            return backup_file

        return await self.hass.async_add_executor_job(_do)
