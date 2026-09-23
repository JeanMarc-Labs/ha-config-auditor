"""Tests for JS frontend integrity — translation keys, prompt patterns, bundle consistency."""
from __future__ import annotations

import re
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import panel_bundle_path

BASE = Path(__file__).parent.parent
SRC  = BASE / "www" / "src"
FR_JSON = BASE / "translations" / "fr.json"
BUNDLE = panel_bundle_path()


def get_panel_keys():
    """Flatten all keys under panel.* in fr.json."""
    data = json.loads(FR_JSON.read_text(encoding="utf-8"))
    panel = data.get("panel", {})
    def flatten(d, prefix=""):
        keys = set()
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys |= flatten(v, full)
            else:
                keys.add(full)
        return keys
    return flatten(panel)


# ── Bundle freshness ──────────────────────────────────────────────────────────

class TestBundleFreshness:
    """The compiled bundle must be consistent with source files."""

    def test_bundle_exists(self):
        assert BUNDLE.exists(), f"Compiled bundle not found: {BUNDLE}"

    def test_only_one_bundle_is_shipped(self):
        """build.sh emits haca-panel.<hash>.js and nothing else.

        Up to 1.8.0 it also wrote a byte-identical haca-panel.js, which nothing
        loaded: 656 KB of dead weight in the repository and in every HACS
        download. The build now deletes it, so a copy reappearing means someone
        restored the old script or copied a file by hand.
        """
        www = BASE / "www"
        assert not (www / "haca-panel.js").exists(), (
            "www/haca-panel.js is back. Only the hashed bundle is served — "
            "run www/build.sh, which deletes this file."
        )
        hashed = sorted(p.name for p in www.glob("haca-panel.*.js")
                        if re.fullmatch(r"haca-panel\.[0-9a-f]{8}\.js", p.name))
        assert len(hashed) == 1, (
            f"expected exactly one hashed bundle in www/, found {hashed} — "
            "build.sh cleans up older ones, so a leftover means a stale copy"
        )

    def test_bundle_has_reasonable_size(self):
        size = BUNDLE.stat().st_size
        assert size > 200_000, f"Bundle seems too small ({size} bytes) — build may have failed"
        assert size < 5_000_000, f"Bundle seems too large ({size} bytes)"

    def test_bundle_contains_buildactionprompt(self):
        """_buildActionPrompt must be present in compiled bundle."""
        content = BUNDLE.read_text(encoding="utf-8")
        assert "_buildActionPrompt" in content, (
            "_buildActionPrompt missing from compiled bundle. "
            "Run build.sh to recompile."
        )

    def test_bundle_contains_redundancy_direct_chat(self):
        """_showRedundancyAI must use _openChatWithMessage directly, not suggestion modal."""
        content = BUNDLE.read_text(encoding="utf-8")
        assert "_showRedundancyAI" in content
        # Must NOT contain the old suggestion pattern
        assert "Suggestion IA" not in content, \
            "Old 'Suggestion IA' pattern found in bundle — intermediate modal not fully removed"
        assert "Applique cette modification" not in content, \
            "Old 'Applique cette modification' pattern found — intermediate modal not removed"

    def test_bundle_contains_area_direct_chat(self):
        """_showAreaSuggestionAI must go directly to chat."""
        content = BUNDLE.read_text(encoding="utf-8")
        assert "_showAreaSuggestionAI" in content
        # Must NOT call haca/explain_issue
        bundle_area_idx = content.find("_showAreaSuggestionAI")
        area_fn = content[bundle_area_idx:bundle_area_idx + 1000]
        assert "haca/explain_issue" not in area_fn, \
            "_showAreaSuggestionAI still calls haca/explain_issue (suggestion modal pattern)"

    def test_no_explainwithai_called_for_blueprint(self):
        """Blueprint button must not call explainWithAI."""
        content = BUNDLE.read_text(encoding="utf-8")
        # Find blueprint-ai-btn handler
        idx = content.find("blueprint-ai-btn")
        if idx >= 0:
            handler_section = content[idx:idx + 500]
            assert "explainWithAI(issue)" not in handler_section, \
                "Blueprint button still calls explainWithAI — will produce suggestion not action"


# ── No suggestion-style prompts ───────────────────────────────────────────────

class TestNoSuggestionPrompts:
    """JS must not build suggestion-style prompts that contaminate the chat."""

    BAD_PATTERNS = [
        "Suggestion IA",
        "Applique cette modification",
        "Explique comment migrer",
        "fournis un exemple YAML",
        r"propose.*YAML.*remplacement",
        "Analyse les risques.*propose",
    ]

    @pytest.mark.parametrize("filename", [
        "redundancy.js", "area_heatmap.js", "ai_explain.js",
        "issues.js", "core.js", "scan.js",
    ])
    def test_no_suggestion_pattern_in_source(self, filename):
        fpath = SRC / filename
        if not fpath.exists():
            pytest.skip(f"{filename} not found")
        content = fpath.read_text(encoding="utf-8")
        for pat in self.BAD_PATTERNS:
            assert not re.search(pat, content, re.IGNORECASE), (
                f"Suggestion-style pattern '{pat}' found in {filename}. "
                "This causes the Chat AI to receive explanation prompts instead of action commands."
            )

    def test_no_suggestion_pattern_in_bundle(self):
        content = BUNDLE.read_text(encoding="utf-8")
        for pat in self.BAD_PATTERNS:
            assert not re.search(pat, content, re.IGNORECASE), (
                f"Suggestion-style pattern '{pat}' found in compiled bundle."
            )


# ── Translation key coverage ──────────────────────────────────────────────────

class TestTranslationCoverage:
    """All this.t('x.y') calls in JS source must have corresponding keys in fr.json."""

    def test_all_used_keys_exist_in_fr_json(self):
        panel_keys = get_panel_keys()
        js_keys = set()
        for f in SRC.glob("*.js"):
            content = f.read_text(encoding="utf-8")
            for m in re.finditer(r"""this\.t\(['"]([a-z_][a-z0-9_.]+)['"]\)""", content):
                k = m.group(1)
                if "." in k:
                    js_keys.add(k)

        missing = js_keys - panel_keys
        assert not missing, (
            f"{len(missing)} translation keys used in JS but missing from fr.json panel.*:\n"
            + "\n".join(f"  ❌ {k}" for k in sorted(missing)[:20])
            + ("\n  ..." if len(missing) > 20 else "")
        )

    def test_all_translation_files_have_same_panel_keys(self):
        """All language files must have the same panel.* keys as fr.json."""
        fr_keys = get_panel_keys()
        trans_dir = BASE / "translations"
        errors = []
        for f in sorted(trans_dir.glob("*.json")):
            if f.stem == "fr":
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            panel = data.get("panel", {})
            def flatten(d, prefix=""):
                keys = set()
                for k, v in d.items():
                    full = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, dict):
                        keys |= flatten(v, full)
                    else:
                        keys.add(full)
                return keys
            lang_keys = flatten(panel)
            missing = fr_keys - lang_keys
            extra = lang_keys - fr_keys
            if missing or extra:
                errors.append(f"{f.stem}: missing={len(missing)}, extra={len(extra)}")
        assert not errors, "Translation file key mismatches:\n" + "\n".join(errors)


# ── _buildActionPrompt coverage ──────────────────────────────────────────────

class TestBuildActionPromptCoverage:
    """_buildActionPrompt must cover all actionable issue types."""

    ACTIONABLE_TYPES = [
        # Automations
        "no_alias", "no_description", "never_triggered", "ghost_automation",
        "duplicate_automation", "probable_duplicate_automation",
        "device_id_in_trigger", "device_id_in_action", "device_id_in_condition",
        "deprecated_service", "unknown_service", "unknown_area_reference",
        "incorrect_mode_motion_single", "script_blueprint_candidate",
        "blueprint_missing_path", "blueprint_file_not_found",
        # Scripts
        "empty_script", "script_orphan", "script_cycle",
        # Scenes
        "empty_scene", "scene_duplicate", "scene_not_triggered",
        # Entities
        "zombie_entity", "ghost_registry_entry", "disabled_but_referenced",
        # Helpers
        "helper_unused", "timer_orphaned",
        # Security
        "hardcoded_secret", "sensitive_data_exposure",
        # Dashboard
        "dashboard_missing_entity",
    ]

    def test_actionable_types_handled_in_source(self):
        """Each actionable issue type must have a branch in _buildActionPrompt."""
        ai_explain = (SRC / "ai_explain.js").read_text(encoding="utf-8")
        missing = []
        for issue_type in self.ACTIONABLE_TYPES:
            if f"'{issue_type}'" not in ai_explain and f'"{issue_type}"' not in ai_explain:
                missing.append(issue_type)
        assert not missing, (
            "Issue types with no action prompt in _buildActionPrompt:\n"
            + "\n".join(f"  ❌ {t}" for t in missing)
        )

    def test_buildactionprompt_returns_null_for_informational(self):
        """Purely informational issues should return null (fall back to explainWithAI)."""
        ai_explain = (SRC / "ai_explain.js").read_text(encoding="utf-8")
        assert "return null;" in ai_explain, \
            "_buildActionPrompt must return null for informational issues (fallback to explainWithAI)"


# ── HTML escaping in the panel ───────────────────────────────────────────────

class TestHtmlEscaping:
    """Audit data must never reach the panel's HTML unescaped.

    The panel runs in the HA frontend origin, where the auth token lives. Issue
    fields are not all authored by the admin: an automation alias, a
    friendly_name or a device name can come from MQTT/Bluetooth/mDNS discovery,
    so a malicious device name would otherwise execute in that origin.

    This test flags any `${...}` interpolation that (a) sits on a line building
    HTML and (b) reads one of the fields below without an escaping wrapper.
    """

    FIELDS = ("entity_id", "message", "alias", "path", "name", "location", "device_id")

    # Wrappers that make an interpolation safe.
    SAFE_WRAPPERS = (
        "escapeHtml(", "esc(", "escM(", "encodeURIComponent(", "JSON.stringify(",
    )

    # Reviewed exceptions: the expression reads a field but its *value* is a
    # fixed literal, so nothing user-controlled reaches the HTML.
    ALLOWED = {
        # Renders ' checked' or '' — the entity_id only feeds a Set lookup.
        "this._orphanSel.has(o.entity_id) ? ' checked' : ''",
    }

    INTERP = re.compile(r"\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}")
    STRING_LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")
    # A line is "HTML" if it opens/closes a tag or assigns to an HTML sink.
    HTML_LINE = re.compile(r"<\s*/?[a-zA-Z]|innerHTML|_updateContent|createModal")

    def _offenders(self, path: Path) -> list[str]:
        field_re = re.compile(r"\b(" + "|".join(self.FIELDS) + r")\b")
        found = []
        for lineno, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if not self.HTML_LINE.search(line):
                continue
            for match in self.INTERP.finditer(line):
                expr = match.group(1).strip()
                if expr in self.ALLOWED:
                    continue
                # String literals ('name', 'tables.path'…) are not data.
                if not field_re.search(self.STRING_LITERAL.sub("", expr)):
                    continue
                if any(w in expr for w in self.SAFE_WRAPPERS):
                    continue
                found.append(f"{path.name}:{lineno}: ${{{expr}}}")
        return found

    def test_no_unescaped_field_in_html(self):
        offenders = []
        for f in sorted(SRC.glob("*.js")):
            offenders += self._offenders(f)
        assert not offenders, (
            f"{len(offenders)} unescaped interpolation(s) of audit data into HTML — "
            "wrap them in this.escapeHtml(...):\n" + "\n".join(offenders)
        )

    def test_escapehtml_handles_non_strings(self):
        """escapeHtml must not blow up on numbers/null — it used to call
        .replace() on whatever it was given."""
        utils = (SRC / "utils.js").read_text(encoding="utf-8")
        assert "String(text)" in utils, (
            "escapeHtml no longer coerces its argument; a numeric issue field "
            "would throw and blank the modal it was rendering."
        )


# ── MCP tool list ─────────────────────────────────────────────────────────────

class TestMcpToolCategories:
    """The panel's tool grouping must cover exactly what the server registers.

    `toolCategories` in mcp_panel.js is hand-kept, for reading order and icons.
    It silently drifted to 67 of the 69 registered tools — the two missing ones,
    ha_list_issue_catalog and ha_fix_batch, were exactly the aliases nobody
    thought to add — while a hardcoded "67 tools" label in all 13 languages said
    the count was right. The count comes from the server now; this pins the list.
    """

    @staticmethod
    def _panel_tools() -> set[str]:
        js = (SRC / "mcp_panel.js").read_text(encoding="utf-8")
        block = js.split("var toolCategories = [", 1)[1].split("\n  ];", 1)[0]
        return set(re.findall(r"'((?:ha|haca)_\w+)'", block))

    def test_no_duplicate_badges(self):
        js = (SRC / "mcp_panel.js").read_text(encoding="utf-8")
        block = js.split("var toolCategories = [", 1)[1].split("\n  ];", 1)[0]
        names = re.findall(r"'((?:ha|haca)_\w+)'", block)
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert not dupes, f"tool listed in two categories: {dupes}"

    def test_categories_match_the_registry(self):
        mcp = pytest.importorskip("custom_components.config_auditor.mcp_server")
        registered = set(mcp.TOOL_HANDLERS)
        listed = self._panel_tools()
        missing = registered - listed
        unknown = listed - registered
        assert not missing, (
            f"{len(missing)} tool(s) the server registers are absent from the panel's "
            f"categories, so the MCP tab under-reports what an agent can call: "
            f"{sorted(missing)}"
        )
        assert not unknown, (
            f"the panel advertises tool(s) the server does not register: {sorted(unknown)}"
        )

    def test_count_is_not_hardcoded(self):
        """The label used to read "67 tools" in all 13 languages."""
        label = json.loads(FR_JSON.read_text(encoding="utf-8"))["panel"]["mcp"]["tools_count_label"]
        assert "{declared}" in label and "{callable}" in label, (
            "tools_count_label must be filled from the server's own counts, not "
            "written out as a number that nothing keeps true"
        )
        js = (SRC / "mcp_panel.js").read_text(encoding="utf-8")
        assert "mcpStatus.tools" in js and "mcpStatus.callable_tools" in js, (
            "the panel must read both counts from haca/mcp_status"
        )

    def test_status_sends_the_real_lists(self):
        """haca/mcp_status used to send seven hardcoded names nothing read."""
        ws = (BASE / "websocket.py").read_text(encoding="utf-8")
        block = ws.split("async def handle_mcp_status(", 1)[1].split("\nasync def ", 1)[0]
        assert '"tools": [tool["name"] for tool in MCP_TOOLS]' in block, \
            "the advertised list must come from MCP_TOOLS"
        assert '"callable_tools": sorted(TOOL_HANDLERS)' in block, \
            "the callable list must come from TOOL_HANDLERS"


# ── Backups tab ───────────────────────────────────────────────────────────────

class TestBackupsPanel:
    def test_restore_reads_the_service_answer(self):
        """A bare callService never read `success: false`: a restore that did
        nothing was announced as done."""
        core = (SRC / "core.js").read_text(encoding="utf-8")
        body = core.split("async restoreBackup(path) {", 1)[1].split("\n    async ", 1)[0]
        assert "return_response: true" in body
        assert "response.success" in body
        assert "callService(" not in body

    def test_no_switch_for_the_retired_backup_option(self):
        """`backup_enabled` was shown as "Auto-backup before fix" and read by nothing."""
        assert "backup_enabled" not in (SRC / "config_tab.js").read_text(encoding="utf-8")
        assert "backup_enabled" not in (BASE / "config_flow.py").read_text(encoding="utf-8")
