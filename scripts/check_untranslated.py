#!/usr/bin/env python3
"""Find strings that are still identical to their English original.

A key that carries the English text in, say, ru.json is almost always one that
was added and never translated: the project rule is that every key is
hand-translated in all 13 languages, never left to fall back to English. By
1.8.0 there were 1 989 of them across the 12 non-English files.

Some strings are the same in every language and always will be — a product name,
a format string with no words in it, a YAML key, a menu path in someone else's
software. Those live in EXPECTED_IDENTICAL below, each with the reason, so the
count means "still to translate" rather than "identical to English".

Usage::

    python scripts/check_untranslated.py           # report, exit 1 if any
    python scripts/check_untranslated.py --list    # report, always exit 0
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TRANSLATIONS = REPO_ROOT / "custom_components" / "config_auditor" / "translations"

# Below this length a match says nothing: "OK", "Wi-Fi", "{n}" and the like are
# the same everywhere. The audit that opened this work used the same threshold.
MIN_LENGTH = 12

# {dotted key: (languages it is legitimately identical in, why)}. "*" means all.
EXPECTED_IDENTICAL: dict[str, tuple[tuple[str, ...], str]] = {
    "config.step.user.title": (("*",), "the product name"),
    "issues.generic_high_issue.title": (("*",), "'HACA: {type} — {entity}' — no words in it"),
    "panel.diag_prompts.marker": (("*",), "the token the panel looks for in the AI answer"),
    "panel.issue_types.types.wait_template_vs_wait_for_trigger": (
        ("*",), "two YAML keys"),
    "panel.mcp.hint_vscode": (("*",), "a literal VS Code menu path and file name"),
    "panel.mcp.hint_cursor": (("*",), "a literal Cursor menu path and file name"),
    "panel.mcp.hint_windsurf": (("*",), "a literal Windsurf menu path and file name"),
    "panel.mcp.endpoint_label": (("it",), "Italian uses 'endpoint' as it stands"),
    "panel.config.llm_api_enabled": (("ja", "zh-Hans"), "the API's own name"),
    "panel.issue_types.types.device_id_in_trigger": (("nl",), "natural Dutch as it stands"),
    "panel.ai_explain.actions_label": (("fr",), "'actions' is the French word"),
    "panel.ai_explain.conditions_label": (("fr",), "'conditions' is the French word"),
    "panel.ai_explain.templates_label": (("fr",), "'templates' is what French uses here"),
    "panel.ai_explain.triggers_label": (("nl",), "'triggers' is the Dutch plural"),
    "panel.complexity.triggers_label": (("nl",), "'triggers' is the Dutch plural"),
    "panel.pagination.page_of": (("fr",), "'Page {page} / {total}' is already French"),
    "panel.tabs.config": (("fr",), "'Configuration' is already French"),
}


def leaves(node: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(leaves(value, path))
        elif isinstance(value, str):
            out[path] = value
    return out


def _load(lang: str) -> dict[str, str]:
    return leaves(json.loads((TRANSLATIONS / f"{lang}.json").read_bytes().decode("utf-8")))


def _expected(key: str, lang: str) -> bool:
    entry = EXPECTED_IDENTICAL.get(key)
    if entry is None:
        return False
    langs, _ = entry
    return "*" in langs or lang in langs


def find_untranslated() -> dict[str, list[str]]:
    """{language: [keys still carrying the English string]}, worst language first."""
    english = _load("en")
    languages = sorted(p.stem for p in TRANSLATIONS.glob("*.json") if p.stem != "en")
    out: dict[str, list[str]] = {}
    for lang in languages:
        other = _load(lang)
        stale = [
            key for key, value in english.items()
            if len(value) > MIN_LENGTH
            and other.get(key) == value
            and not _expected(key, lang)
        ]
        if stale:
            out[lang] = sorted(stale)
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true",
        help="report and exit 0 (for a translation pass, not for CI)",
    )
    args = parser.parse_args()

    stale = find_untranslated()
    total = sum(len(v) for v in stale.values())
    if not stale:
        print("Every language is fully translated.")
        return 0

    print(f"{total} string(s) still identical to English:\n")
    for lang, keys in stale.items():
        print(f"  {lang}: {len(keys)}")
        for key in keys:
            print(f"      {key}")
    return 0 if args.list else 1


if __name__ == "__main__":
    sys.exit(main())
