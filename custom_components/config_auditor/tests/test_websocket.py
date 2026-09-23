"""Tests for websocket.py — handler registration, chat fallback, field fix, security."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import mcp_package_source  # noqa: E402

WS_FILE   = Path(__file__).parent.parent / "websocket.py"
CONTENT   = WS_FILE.read_text(encoding="utf-8")
# mcp_server is a package since the 1.8.0 split — read all of it.
MCP_CONTENT = mcp_package_source()
YAML_SOURCES_FILE = Path(__file__).parent.parent / "yaml_sources.py"
YAML_SOURCES_CONTENT = YAML_SOURCES_FILE.read_text(encoding="utf-8")
YAML_WRITER_FILE = Path(__file__).parent.parent / "yaml_writer.py"
YAML_WRITER_CONTENT = YAML_WRITER_FILE.read_text(encoding="utf-8")


# ── Handler registration ──────────────────────────────────────────────────────

class TestWebsocketHandlers:
    """All websocket handlers must be registered."""

    def test_handle_chat_registered(self):
        assert "handle_chat" in CONTENT
        assert "websocket_api.async_register_command(hass, handle_chat)" in CONTENT

    def test_handle_translations_registered(self):
        assert "handle_get_translations" in CONTENT
        assert "websocket_api.async_register_command(hass, handle_get_translations)" in CONTENT

    def test_handle_explain_issue_registered(self):
        assert "handle_explain_issue" in CONTENT
        assert "websocket_api.async_register_command(hass, handle_explain_issue)" in CONTENT

    def test_handle_ai_suggest_fix_registered(self):
        assert "handle_ai_suggest_fix" in CONTENT
        assert "websocket_api.async_register_command(hass, handle_ai_suggest_fix)" in CONTENT

    def test_handle_apply_field_fix_registered(self):
        assert "handle_apply_field_fix" in CONTENT
        assert "websocket_api.async_register_command(hass, handle_apply_field_fix)" in CONTENT

    def test_valid_python_syntax(self):
        import py_compile, tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(CONTENT.encode())
            fname = f.name
        try:
            py_compile.compile(fname, doraise=True)
        except py_compile.PyCompileError as e:
            pytest.fail(f"Syntax error in websocket.py: {e}")


# ── Security: admin protection ────────────────────────────────────────────────

class TestAdminProtection:
    """Every websocket command must require admin.

    `haca/get_data` returns the whole audit, security category included;
    `haca/explain_issue` spends an LLM call; `haca/mcp_status` hands out the
    MCP endpoint's configuration. The panel itself is admin-only, so there is
    no read-only tier to preserve — an unguarded command is simply a hole.
    """

    DESTRUCTIVE = [
        "handle_apply_fix",
        "handle_restore_backup",
        "handle_purge_recorder_orphans",
        "handle_apply_field_fix",
        "handle_chat",
        "handle_save_options",
        "handle_delete_history",
        "handle_ai_suggest_fix",
    ]

    def test_destructive_handlers_require_admin(self):
        """Every destructive handler must have @require_admin decorator."""
        missing = []
        for handler in self.DESTRUCTIVE:
            # Find the handler definition and check the 3 lines before it
            pattern = rf"@websocket_api\.require_admin\s+@websocket_api\.async_response\s+async def {handler}\("
            if not re.search(pattern, CONTENT, re.MULTILINE):
                missing.append(handler)
        assert not missing, f"Missing @require_admin on: {missing}"

    @staticmethod
    def _commands():
        """Yield (command, handler, decorator_block) for every ws command."""
        lines = CONTENT.split("\n")
        for idx, line in enumerate(lines):
            if not line.startswith("async def handle_"):
                continue
            back = idx - 1
            block = []
            while back >= 0 and lines[back].strip():
                block.insert(0, lines[back])
                back -= 1
            decorators = "\n".join(block)
            if "@websocket_api.websocket_command" not in decorators:
                continue
            match = re.search(r'"type"\)?:\s*"([^"]+)"', decorators)
            yield (
                match.group(1) if match else "?",
                line[len("async def "):].split("(")[0],
                decorators,
            )

    def test_every_command_requires_admin(self):
        """No websocket command may ship without @require_admin."""
        commands = list(self._commands())
        assert len(commands) >= 30, (
            f"Only {len(commands)} websocket commands parsed — the detector is "
            "out of step with websocket.py, not the other way round"
        )
        unguarded = [
            f"{cmd} ({handler})"
            for cmd, handler, decorators in commands
            if "@websocket_api.require_admin" not in decorators
        ]
        assert not unguarded, (
            f"{len(unguarded)} websocket command(s) callable by any logged-in user:\n"
            + "\n".join(unguarded)
        )


# ── Language allow-list (path traversal) ─────────────────────────────────────

class TestLanguageAllowList:
    """`language` comes from the browser and reaches a file path."""

    def test_get_translations_uses_allow_list(self):
        assert "def _safe_language(" in CONTENT, \
            "websocket.py must define the _safe_language() allow-list helper"
        assert 'language = _safe_language(msg.get("language")' in CONTENT, \
            "handle_get_translations must resolve `language` through _safe_language()"

    def test_no_raw_language_from_client(self):
        assert 'msg.get("language") or hass.config.language' not in CONTENT, (
            "the old unvalidated fallback chain is back: a language of "
            "'../../secrets' would escape the translations/ folder"
        )

    def test_allow_list_falls_back_to_english(self):
        helper = CONTENT[CONTENT.index("def _safe_language("):]
        helper = helper[:helper.index("\n\n\n")]
        assert 'return "en"' in helper, \
            "_safe_language must fall back to English for anything unknown"
        assert "_TS_CACHE" in helper, \
            "_safe_language should derive its allow-list from the shipped files"


# ── Chat: async_converse fallback chain ───────────────────────────────────────

class TestChatFallback:
    """handle_chat must use async_converse with fallback across all agents."""

    def test_uses_async_converse(self):
        assert "async_converse" in CONTENT, \
            "handle_chat must use homeassistant.components.conversation.async_converse"

    def test_no_haca_action_loop(self):
        """Old [HACA_ACTION:] agentic loop must be gone — now handled natively by HA LLM API."""
        assert "[HACA_ACTION:" not in CONTENT, \
            "[HACA_ACTION:] parsing loop must not exist in websocket.py (now handled by HA LLM API)"

    def test_fallback_across_agents(self):
        """Chat must iterate over multiple agents for fallback."""
        assert "_async_find_all_conversation_agents" in CONTENT, \
            "handle_chat must call _async_find_all_conversation_agents for fallback"

    def test_is_llm_error_reply_used(self):
        """Error replies from agents must be detected and skipped."""
        assert "_is_llm_error_reply" in CONTENT, \
            "_is_llm_error_reply must be used to detect and skip error responses"


# ── Field fix: apply_field_fix correctness ───────────────────────────────────

class TestApplyFieldFix:
    """handle_apply_field_fix must write atomically and match by entity_id."""

    def test_atomic_write(self):
        """YAML must be written atomically (tmp file + os.replace).

        The write itself lives in yaml_writer.write_back, which is what
        apply_field_fix reaches through async_write_and_reload.
        """
        assert "async_write_and_reload(" in CONTENT, \
            "apply_field_fix must write through yaml_writer.async_write_and_reload"
        assert "os.replace(tmp, target.path)" in YAML_WRITER_CONTENT, \
            "write_back must use atomic write (os.replace)"

    def test_roundtrip_write_preserves_comments(self):
        """The field fix must not flatten the user's file (ruamel round-trip)."""
        assert "preserve_quotes = True" in YAML_WRITER_CONTENT, \
            "write path must use ruamel round-trip, not yaml.safe_load/dump"
        assert "_yaml.dump(data" not in CONTENT, \
            "apply_field_fix must no longer re-dump the whole file with PyYAML"

    def test_backup_before_write(self):
        """A backup must be taken before the YAML is rewritten."""
        fn_start = CONTENT.find("async def handle_apply_field_fix(")
        body = CONTENT[fn_start:fn_start + 3000]
        assert "async_write_and_reload(" in body, \
            "apply_field_fix must write through async_write_and_reload"
        assert "write_back, target, hass.config.config_dir" in YAML_WRITER_CONTENT, \
            "async_write_checked must use the backup-taking form of write_back"
        # …and that form must be the one that snapshots. What it actually does
        # with the snapshot is pinned by test_yaml_writer.py.
        assert "create_backup(config_dir, target.path)" in YAML_WRITER_CONTENT, \
            "write_back must back the file up when given a config_dir"

    def test_uses_shared_domain_resolver(self):
        """Split configs: the entry may not live in <config>/automations.yaml."""
        assert 'hass.config.config_dir) / ("scripts.yaml"' not in CONTENT, \
            "apply_field_fix must not hardcode the flat YAML paths"
        assert "_find_entry_sync(" in CONTENT, \
            "apply_field_fix must locate the entry through the shared resolver"

    def test_supported_fields_only(self):
        """Only description and alias are supported fields."""
        assert '"description", "alias"' in CONTENT or \
               '("description", "alias")' in CONTENT, \
            "apply_field_fix must validate field is in (description, alias)"

    def test_entity_id_primary_match(self):
        """Match must use entity_id / id as primary key, not alias fallback."""
        # The first matching pass of the resolver compares the HA numeric id
        # to the entity_id slug; alias passes only run after it.
        resolver = CONTENT[CONTENT.index("def _find_entry_sync("):]
        resolver = resolver[:resolver.index("\n\n\n")]
        # Automation branch: the id pass must come before any alias pass.
        automation_passes = resolver[resolver.rindex("passes = ["):]
        by_id = automation_passes.index('e.get("id", "")).strip() == slug')
        by_alias = automation_passes.index('e.get("alias", "")')
        assert by_id < by_alias, \
            "apply_field_fix must match an automation by its numeric id first"


# ── MCP tools: atomic writes ─────────────────────────────────────────────────
# The snapshot each write takes first is exercised in test_mcp_backups.py.

class TestMcpAtomicWrites:
    """MCP tools write through the atomic helper."""

    def test_atomic_write_helper_exists(self):
        assert "def _atomic_write(" in MCP_CONTENT, \
            "_atomic_write helper function missing from mcp_server.py"

    def test_no_unsafe_write_text(self):
        """No direct write_text() on YAML files — must use _atomic_write."""
        # write_text() for non-YAML things (blueprints with open()) is OK
        # but auto_file.write_text and scripts_file.write_text must be gone
        assert "auto_file.write_text" not in MCP_CONTENT, \
            "auto_file.write_text found — must use _atomic_write"
        assert "scripts_file.write_text" not in MCP_CONTENT, \
            "scripts_file.write_text found — must use _atomic_write"


# ── Path traversal protection ─────────────────────────────────────────────────

class TestPathTraversal:
    """Config file tools must use realpath() to prevent traversal."""

    def test_realpath_used_in_get_config(self):
        assert "os.path.realpath" in MCP_CONTENT, \
            "os.path.realpath must be used to prevent path traversal"

    def test_no_startswith_only_check(self):
        """Raw startswith(config_root) without realpath is insufficient."""
        # Should not have the vulnerable pattern (without realpath)
        vulnerable = re.findall(
            r'fpath\.startswith\(config_root\)',
            MCP_CONTENT
        )
        assert not vulnerable, \
            "Vulnerable fpath.startswith(config_root) without realpath() found"
