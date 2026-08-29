"""Tests for yaml_sources — where automation / script / scene entries live.

Covers the resolver behind the split-config fix: which files HA actually reads
for `automation:` / `script:` / `scene:`, and the path guard the blueprint
tools use.

    pytest custom_components/config_auditor/tests/test_yaml_sources.py -v
"""
from __future__ import annotations

import os

import pytest

from custom_components.config_auditor.yaml_sources import (
    default_write_target,
    is_split_config,
    is_within,
    iter_domain_files,
    resolve_config_sources,
    walk_yaml_dir,
)


def _build(tmp_path, files: dict) -> str:
    """Write a fake config tree and return its directory."""
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return str(tmp_path)


def _rel(config_dir: str, files: list[str]) -> list[str]:
    return [os.path.relpath(f, config_dir).replace("\\", "/") for f in files]


# ═══════════════════════════════════════════════════════════════════════════
# resolve_config_sources / iter_domain_files
# ═══════════════════════════════════════════════════════════════════════════

class TestResolveSources:
    def test_flat_default_when_no_directive(self, tmp_path):
        """No `automation:` key at all → the historical flat file."""
        cfg = _build(tmp_path, {
            "configuration.yaml": "default_config:\n",
            "automations.yaml": "- id: a1\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations.yaml"
        ]
        assert is_split_config(cfg, "automation", "automations.yaml") is False

    def test_missing_file_yields_nothing(self, tmp_path):
        """A declared-but-absent flat file yields [] — same as the old early return."""
        cfg = _build(tmp_path, {"configuration.yaml": "default_config:\n"})
        assert iter_domain_files(cfg, "script", "scripts.yaml") == []

    def test_no_configuration_yaml_at_all(self, tmp_path):
        cfg = _build(tmp_path, {"automations.yaml": "- id: a1\n"})
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations.yaml"
        ]

    @pytest.mark.parametrize("tag", [
        "!include_dir_merge_list",
        "!include_dir_list",
        "!include_dir_merge_named",
        "!include_dir_named",
    ])
    def test_all_four_directory_forms(self, tmp_path, tag):
        """Not just !include_dir_merge_list — all four spellings resolve."""
        cfg = _build(tmp_path, {
            "configuration.yaml": f"automation: {tag} automations/\n",
            "automations/a.yaml": "- id: a1\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations/a.yaml"
        ]
        assert is_split_config(cfg, "automation", "automations.yaml") is True

    def test_split_folder_excludes_stale_root_file(self, tmp_path):
        """A stale automations.yaml HA no longer reads must not be audited."""
        cfg = _build(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/clima.yaml": "- id: a1\n",
            "automations.yaml": "- id: stale\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations/clima.yaml"
        ]

    def test_labelled_sections_are_all_returned(self, tmp_path):
        """`automation ui:` + `automation manual:` is a standard split layout."""
        cfg = _build(tmp_path, {
            "configuration.yaml": (
                "automation ui: !include automations.yaml\n"
                "automation manual: !include_dir_merge_list automations/\n"
            ),
            "automations.yaml": "- id: ui1\n",
            "automations/m.yaml": "- id: m1\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations.yaml", "automations/m.yaml"
        ]

    def test_recursive_sorted_and_skips_dotfiles(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": "script: !include_dir_merge_named ha_scripts/\n",
            "ha_scripts/b.yaml": "b:\n",
            "ha_scripts/a.yml": "a:\n",
            "ha_scripts/.swp.yaml": "x:\n",
            "ha_scripts/.hidden/deep.yaml": "h:\n",
            "ha_scripts/sub/c.yaml": "c:\n",
            "ha_scripts/notes.txt": "ignored",
        })
        assert _rel(cfg, iter_domain_files(cfg, "script", "scripts.yaml")) == [
            "ha_scripts/a.yml", "ha_scripts/b.yaml", "ha_scripts/sub/c.yaml"
        ]

    def test_quotes_trailing_slash_and_inline_comment(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml":
                "automation: !include_dir_merge_list 'automations/'  # split\n",
            "automations/a.yaml": "- id: a1\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations/a.yaml"
        ]

    def test_commented_out_directive_is_ignored(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": (
                "# automation: !include_dir_merge_list decoy/\n"
                "automation: !include_dir_merge_list automations/\n"
            ),
            "automations/a.yaml": "- id: a1\n",
            "decoy/bad.yaml": "- id: decoy\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations/a.yaml"
        ]

    def test_nested_key_is_not_a_top_level_directive(self, tmp_path):
        """`homeassistant:` → `automation:` is not a domain declaration."""
        cfg = _build(tmp_path, {
            "configuration.yaml": (
                "homeassistant:\n"
                "  packages: !include_dir_named packages/\n"
                "  automation: !include_dir_merge_list nope/\n"
            ),
            "automations.yaml": "- id: a1\n",
            "nope/a.yaml": "- id: nope\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "automation", "automations.yaml")) == [
            "automations.yaml"
        ]

    def test_tag_on_the_following_line(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": "script:\n  !include_dir_merge_named ha_scripts\n",
            "ha_scripts/s.yaml": "s:\n",
        })
        assert _rel(cfg, iter_domain_files(cfg, "script", "scripts.yaml")) == [
            "ha_scripts/s.yaml"
        ]

    def test_include_single_file(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": "scene: !include scenes/all.yaml\n",
            "scenes/all.yaml": "- id: s\n",
        })
        sources = resolve_config_sources(cfg, "scene", "scenes.yaml")
        assert [kind for kind, _ in sources] == ["file"]
        assert _rel(cfg, iter_domain_files(cfg, "scene", "scenes.yaml")) == [
            "scenes/all.yaml"
        ]

    def test_walk_yaml_dir_on_missing_directory(self, tmp_path):
        assert walk_yaml_dir(str(tmp_path / "nope")) == []


# ═══════════════════════════════════════════════════════════════════════════
# default_write_target
# ═══════════════════════════════════════════════════════════════════════════

class TestWriteTarget:
    def test_flat_install_keeps_its_file(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": "automation: !include automations.yaml\n",
            "automations.yaml": "- id: a1\n",
        })
        target = default_write_target(cfg, "automation", "automations.yaml", "haca_mcp.yaml")
        assert os.path.basename(target) == "automations.yaml"
        assert os.path.dirname(target) == cfg

    def test_split_install_writes_into_the_merged_folder(self, tmp_path):
        """Never the config root — HA does not read it in this layout."""
        cfg = _build(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/a.yaml": "- id: a1\n",
        })
        target = default_write_target(cfg, "automation", "automations.yaml", "haca_mcp.yaml")
        assert _rel(cfg, [target]) == ["automations/haca_mcp.yaml"]


# ═══════════════════════════════════════════════════════════════════════════
# is_within — the blueprint path guard
# ═══════════════════════════════════════════════════════════════════════════

class TestIsWithin:
    def test_accepts_a_real_child(self, tmp_path):
        base = tmp_path / "blueprints"
        (base / "automation").mkdir(parents=True)
        target = base / "automation" / "x.yaml"
        target.write_text("a", encoding="utf-8")
        assert is_within(str(target), str(base)) is True

    def test_rejects_dotdot_traversal(self, tmp_path):
        """The old startswith() guard accepted this: the joined string still
        began with the base directory even though the resolved path did not."""
        base = tmp_path / "blueprints"
        base.mkdir()
        (tmp_path / "secrets.yaml").write_text("api_key: x", encoding="utf-8")
        assert is_within(str(base / ".." / "secrets.yaml"), str(base)) is False

    def test_rejects_sibling_with_a_shared_prefix(self, tmp_path):
        base = tmp_path / "blueprints"
        base.mkdir()
        evil = tmp_path / "blueprints_evil"
        evil.mkdir()
        assert is_within(str(evil), str(base)) is False

    def test_rejects_absolute_path_outside(self, tmp_path):
        base = tmp_path / "blueprints"
        base.mkdir()
        secret = tmp_path / "secrets.yaml"
        secret.write_text("api_key: x", encoding="utf-8")
        assert is_within(str(secret), str(base)) is False
