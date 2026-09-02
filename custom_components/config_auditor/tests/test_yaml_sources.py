"""Tests for yaml_sources — where automation / script / scene entries live.

Covers the resolver behind the split-config fix: which files HA actually reads
for `automation:` / `script:` / `scene:`, and the path guard the blueprint
tools use.

    pytest custom_components/config_auditor/tests/test_yaml_sources.py -v
"""
from __future__ import annotations

import os

import pytest

from custom_components.config_auditor import yaml_sources
from custom_components.config_auditor.yaml_sources import (
    default_write_target,
    find_unloaded_yaml_files,
    is_split_config,
    is_within,
    iter_domain_files,
    load_list_domain,
    resolve_config_sources,
    resolve_packages_sources,
    scan_list_domain,
    scan_named_domain,
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
        # `.yml` is not matched: HA's !include_dir_* constructors glob *.yaml.
        assert _rel(cfg, iter_domain_files(cfg, "script", "scripts.yaml")) == [
            "ha_scripts/b.yaml", "ha_scripts/sub/c.yaml"
        ]
        assert _rel(cfg, find_unloaded_yaml_files(cfg, "script", "scripts.yaml")) == [
            "ha_scripts/a.yml"
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

# ═══════════════════════════════════════════════════════════════════════════
# find_unloaded_yaml_files — dead .yml, but not the ones an !include pulls in
# ═══════════════════════════════════════════════════════════════════════════

class TestFindUnloadedYamlFiles:
    def test_reports_a_dead_yml_in_a_merged_folder(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/live.yaml": "- id: a1\n",
            "automations/dead.yml": "- id: a2\n",
        })
        assert _rel(cfg, find_unloaded_yaml_files(cfg, "automation", "automations.yaml")) == [
            "automations/dead.yml"
        ]

    def test_ignores_a_yml_pulled_in_by_an_explicit_include(self, tmp_path):
        """`!include` takes a literal path and is not extension-restricted, so
        this file IS loaded. Telling the user to rename it breaks the include —
        and the renamed file is then swept up by the *.yaml glob as a top-level
        entry whose shape is wrong."""
        cfg = _build(tmp_path, {
            "configuration.yaml": "automation: !include_dir_merge_list automations/\n",
            "automations/main.yaml": "- !include fragments/notify.yml\n",
            "automations/fragments/notify.yml": "alias: Notify\n",
            "automations/orphan.yml": "- id: a2\n",
        })
        assert _rel(cfg, find_unloaded_yaml_files(cfg, "automation", "automations.yaml")) == [
            "automations/orphan.yml"
        ]

    def test_a_flat_include_of_a_yml_is_not_reported(self, tmp_path):
        """Only the !include_dir_* glob is *.yaml-only; a single file loads fine."""
        cfg = _build(tmp_path, {
            "configuration.yaml": "automation: !include automations.yml\n",
            "automations.yml": "- id: a1\n",
        })
        assert find_unloaded_yaml_files(cfg, "automation", "automations.yaml") == []


# ═══════════════════════════════════════════════════════════════════════════
# resolve_packages_sources — `packages:` lives under `homeassistant:`
# ═══════════════════════════════════════════════════════════════════════════

class TestResolvePackagesSources:
    def test_directory_form(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml":
                "homeassistant:\n  name: Home\n  packages: !include_dir_named packages/\n",
        })
        kinds = resolve_packages_sources(cfg)
        assert [k for k, _ in kinds] == ["dir"]
        assert _rel(cfg, [p for _, p in kinds]) == ["packages"]

    def test_custom_folder_is_followed(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml":
                "homeassistant:\n  packages: !include_dir_merge_named custom_pkgs/\n",
        })
        assert _rel(cfg, [p for _, p in resolve_packages_sources(cfg)]) == ["custom_pkgs"]

    def test_inline_mapping_of_includes(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": (
                "homeassistant:\n"
                "  packages:\n"
                "    heating: !include pkgs/heating.yaml\n"
                "    lights:  !include pkgs/lights.yaml\n"
                "automation: !include automations.yaml\n"
            ),
        })
        sources = resolve_packages_sources(cfg)
        assert [k for k, _ in sources] == ["file", "file"]
        assert _rel(cfg, [p for _, p in sources]) == ["pkgs/heating.yaml", "pkgs/lights.yaml"]

    def test_undeclared_packages_folder_is_not_a_source(self, tmp_path):
        """`packages:` has no default: a folder HA never loads must not be
        audited, or every entry in it is reported as live configuration."""
        cfg = _build(tmp_path, {
            "configuration.yaml": "homeassistant:\n  name: Home\n",
            "packages/stuff.yaml": "automation: []\n",
        })
        assert resolve_packages_sources(cfg) == []

    def test_a_top_level_packages_key_is_not_the_ha_one(self, tmp_path):
        cfg = _build(tmp_path, {
            "configuration.yaml": "packages: !include_dir_named packages/\n",
        })
        assert resolve_packages_sources(cfg) == []

# ═══════════════════════════════════════════════════════════════════════════
# The scan primitives — one pass, carrying what was searched and what was not
#
# The miss path used to re-parse the whole domain to work out which files it
# had had to skip; on a fifty-file split folder that was a second (and, for the
# "available entries" hint, a third) full pass. The scan now reports it.
# ═══════════════════════════════════════════════════════════════════════════

def _scannable(tmp_path) -> str:
    return _build(tmp_path, {
        "configuration.yaml":
            "automation: !include_dir_merge_list automations/\n"
            "script: !include_dir_merge_named ha_scripts/\n",
        "automations/a.yaml": "- id: a1\n  alias: One\n",
        "automations/tagged.yaml":
            "- id: a2\n  alias: Two\n  action:\n"
            "    - service: notify.x\n      data:\n        message: !secret msg\n",
        "automations/broken.yaml": "- id: [unclosed\n",
        "ha_scripts/s.yaml": "one:\n  alias: One\n",
        "ha_scripts/tagged.yaml": "two:\n  alias: !secret name\n",
    })


class TestScanPrimitives:
    def test_hit_names_the_holding_file(self, tmp_path):
        cfg = _scannable(tmp_path)
        scan = scan_list_domain(cfg, "automation", "automations.yaml",
                                lambda a: a.get("id") == "a1")
        assert scan.index == 0
        assert _rel(cfg, [scan.path]) == ["automations/a.yaml"]

    def test_miss_reports_files_and_skipped_from_the_same_pass(self, tmp_path):
        cfg = _scannable(tmp_path)
        scan = scan_list_domain(cfg, "automation", "automations.yaml",
                                lambda a: a.get("id") == "nope")
        assert scan.index == -1
        assert len(scan.files) == 3
        # `!secret` (a tag plain PyYAML refuses, on purpose, on a write path)
        # and a genuine syntax error
        assert _rel(cfg, scan.skipped) == [
            "automations/broken.yaml", "automations/tagged.yaml"
        ]

    def test_named_domain_miss_reports_skipped(self, tmp_path):
        cfg = _scannable(tmp_path)
        scan = scan_named_domain(cfg, "script", "scripts.yaml",
                                 lambda key, _entry: key == "nope")
        assert scan.key is None
        assert _rel(cfg, scan.skipped) == ["ha_scripts/tagged.yaml"]

    def test_load_list_domain_separates_parsed_from_skipped(self, tmp_path):
        cfg = _scannable(tmp_path)
        load = load_list_domain(cfg, "automation", "automations.yaml")
        assert len(load.loaded) == 1
        assert len(load.files) == 3
        assert len(load.skipped) == 2

    def test_a_miss_parses_each_file_once(self, tmp_path, monkeypatch):
        cfg = _scannable(tmp_path)
        parsed: list[str] = []
        original = yaml_sources.read_plain_yaml

        def _counting(path):
            parsed.append(path)
            return original(path)

        monkeypatch.setattr(yaml_sources, "read_plain_yaml", _counting)
        scan_list_domain(cfg, "automation", "automations.yaml",
                         lambda a: a.get("id") == "nope")
        assert len(parsed) == 3
