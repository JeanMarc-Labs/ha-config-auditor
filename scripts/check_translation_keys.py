#!/usr/bin/env python3
"""Find translation keys that nothing references any more.

The panel reads its strings through ``t('config.foo')``, which resolves to
``panel.config.foo`` in the language files. Keys accumulate: a feature is
dropped, its strings stay behind in all 13 files. This walks the ``panel``
subtree of ``en.json`` and reports every key that appears in no source file.

Only the ``panel`` subtree is scanned. Root-level sections are Home Assistant's
own (``config`` for the config flow, ``issues`` for Repairs, ``entity`` for
entity names) plus the server-side sections read by ``_ts()``; a key there can
be referenced by Core itself, so absence from our sources proves nothing.

A key counts as referenced when any of three traces appears in the sources: its
full dotted path, its last segment as a bare word, or its parent path. The
third rule is what covers keys assembled at runtime — ``compliance.js`` writes
``t(`diag_prompts.proposed.${proposedKey}`)``, so the parent
``diag_prompts.proposed`` is the only literal trace those keys leave. The three
together make the report deliberately conservative: anything it flags has no
literal trace at all.

Usage::

    python scripts/check_translation_keys.py            # report, exit 1 if any
    python scripts/check_translation_keys.py --list     # report, always exit 0
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = REPO_ROOT / "custom_components" / "config_auditor"
TRANSLATIONS = INTEGRATION / "translations"

# Directories under the integration that hold no code referencing a panel key.
SKIP_DIRS = {"tests", "translations", "fonts", "data", "brand", "__pycache__"}


def iter_keys(node: dict, prefix: str = "") -> list[str]:
    """Return every leaf path in ``node``, dotted, relative to ``prefix``."""
    out: list[str] = []
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.extend(iter_keys(value, path))
        else:
            out.append(path)
    return out


def source_files() -> list[Path]:
    """Every file that can plausibly name a translation key."""
    # The panel sources, plus the two standalone Lovelace cards that live
    # beside the built bundle. haca-panel*.js is that bundle — skipping it
    # keeps the corpus from counting src/ twice.
    files = [
        p for p in (INTEGRATION / "www").rglob("*.js")
        if not p.name.startswith("haca-panel.")
    ]
    for py in INTEGRATION.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py.relative_to(INTEGRATION).parts):
            continue
        files.append(py)
    return sorted(files)


def find_dead_keys() -> tuple[list[str], int, int]:
    """Return (dead keys, total panel keys, files scanned)."""
    en = json.loads((TRANSLATIONS / "en.json").read_text(encoding="utf-8"))
    keys = iter_keys(en.get("panel", {}))

    files = source_files()
    corpus = "\n".join(p.read_text(encoding="utf-8") for p in files)
    # Two passes over the 4 MB corpus, rather than re-scanning it once per key:
    # every dotted path (quoted or not, so a template literal counts) and every
    # bare identifier.
    dotted = set(re.findall(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", corpus))
    words = set(re.findall(r"[A-Za-z_]\w*", corpus))

    dead = []
    for key in keys:
        parent, _, segment = key.rpartition(".")
        if key in dotted or segment in words or (parent and parent in dotted):
            continue
        dead.append(key)
    return sorted(dead), len(keys), len(files)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list", action="store_true",
        help="report and exit 0 (for the one-off cleanup, not for CI)",
    )
    args = parser.parse_args()

    dead, total, scanned = find_dead_keys()
    print(f"{total} panel keys in en.json, {scanned} source files scanned")
    if not dead:
        print("No dead keys.")
        return 0

    print(f"\n{len(dead)} key(s) referenced nowhere "
          f"(~{len(dead) * 13} strings across the 13 language files):\n")
    for key in dead:
        print(f"  panel.{key}")
    return 0 if args.list else 1


if __name__ == "__main__":
    sys.exit(main())
