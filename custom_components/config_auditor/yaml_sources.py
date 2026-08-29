"""Single source of truth for where automation / script / scene entries live.

Home Assistant lets a top-level domain key in ``configuration.yaml`` point at a
flat file (``automation: !include automations.yaml``), at a folder
(``script: !include_dir_merge_named ha_scripts/``), or at several of those at
once via labelled sections::

    automation ui:     !include automations.yaml
    automation manual: !include_dir_merge_list automations/

Every consumer used to reinvent or skip that resolution: the audit loaders
looked at ``<config>/scripts.yaml`` and nothing else, and the MCP write tools
hardcoded the flat paths — writing to a file HA no longer reads and reporting
success. This module resolves it once, so the audit engine and the MCP tools
always agree on which files hold a domain's entries.

Imported by ``automation_analyzer``, ``automation_optimizer`` and ``mcp_server``.
"""
from __future__ import annotations

import logging
import os

_LOGGER = logging.getLogger(__name__)

# !include_dir_merge_list / !include_dir_list   -> each file holds a LIST of entries
# !include_dir_merge_named / !include_dir_named -> each file holds a NAMED mapping
_DIR_TAGS = (
    "!include_dir_merge_list",
    "!include_dir_list",
    "!include_dir_merge_named",
    "!include_dir_named",
)
_FILE_TAG = "!include"

# ("file", path) -> a single YAML file; ("dir", path) -> a folder of YAML files
Source = tuple[str, str]


def _clean_value(raw: str) -> str:
    """Strip an inline comment and surrounding whitespace from a scalar value."""
    value = raw.strip()
    if " #" in value:
        value = value.split(" #", 1)[0].strip()
    return value


def _as_source(value: str, config_dir: str) -> Source | None:
    """Turn an ``!include*`` scalar into a (kind, absolute path) pair."""
    for tag in _DIR_TAGS:
        if value.startswith(tag):
            folder = value[len(tag):].strip().strip("'\"").rstrip("/")
            if not folder:
                return None
            return ("dir", os.path.normpath(os.path.join(config_dir, folder)))
    if value.startswith(_FILE_TAG + " "):
        target = value[len(_FILE_TAG):].strip().strip("'\"")
        if not target:
            return None
        return ("file", os.path.normpath(os.path.join(config_dir, target)))
    return None


def resolve_config_sources(
    config_dir: str, key: str, default_filename: str
) -> list[Source]:
    """Return every source declared for a top-level ``configuration.yaml`` key.

    Labelled sections (``automation ui:`` / ``automation manual:``) are all
    returned, in declaration order — that layout is what keeps the UI editor
    working alongside a split folder, so honouring only the first directive
    would still miss half the entries.

    ``configuration.yaml`` is read as raw text on purpose: only the directive
    line per key is needed, and a full YAML parse would pull in HA's loader and
    execute every ``!include`` as a side effect. Falls back to
    ``[("file", <config_dir>/<default_filename>)]`` when the file is missing or
    the key carries no include directive, which reproduces the historical
    "look at the flat file" behaviour.
    """
    default: list[Source] = [("file", os.path.join(config_dir, default_filename))]
    try:
        with open(os.path.join(config_dir, "configuration.yaml"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return default

    sources: list[Source] = []
    for index, line in enumerate(lines):
        # Top-level, non-comment keys only: anything indented belongs to a
        # nested mapping, not to a domain declaration.
        if not line[:1].strip() or line.lstrip().startswith("#"):
            continue
        head, sep, rest = line.partition(":")
        if not sep:
            continue
        head = head.rstrip()
        if head != key and not head.startswith(key + " "):
            continue

        value = _clean_value(rest)
        if not value:
            # `automation:` with the tag on the next, indented line.
            for follow in lines[index + 1:]:
                if not follow.strip() or follow.lstrip().startswith("#"):
                    continue
                if not follow[:1].strip():
                    value = _clean_value(follow)
                break

        source = _as_source(value, config_dir)
        if source is not None:
            sources.append(source)

    return sources or default


def resolve_config_source(
    config_dir: str, key: str, default_filename: str
) -> Source:
    """First source declared for a key — for callers that must pick one file."""
    return resolve_config_sources(config_dir, key, default_filename)[0]


def walk_yaml_dir(directory: str) -> list[str]:
    """Every ``*.yaml`` / ``*.yml`` under a folder, the way HA merges them.

    Recursive and sorted, symlinks not followed, dotfiles and dot-directories
    skipped (HA's own ``_find_files`` rules), so an editor's ``.swp`` or a
    symlink loop can neither pollute nor wedge the scan.
    """
    if not os.path.isdir(directory):
        return []
    found: list[str] = []
    for root, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.startswith(".") or not name.endswith((".yaml", ".yml")):
                continue
            found.append(os.path.join(root, name))
    return found


def iter_domain_files(
    config_dir: str, key: str, default_filename: str
) -> list[str]:
    """Ordered list of existing YAML files that hold this domain's entries.

    - flat file: kept when it exists, dropped when it does not (matches the old
      ``if not exists: return`` semantics — flat installs see no change).
    - split dir: every YAML file under the folder, per :func:`walk_yaml_dir`.
    """
    found: list[str] = []
    seen: set[str] = set()

    for kind, source in resolve_config_sources(config_dir, key, default_filename):
        candidates = [source] if kind == "file" else walk_yaml_dir(source)
        for path in candidates:
            if kind == "file" and not os.path.isfile(path):
                continue
            marker = os.path.normcase(os.path.abspath(path))
            if marker in seen:
                continue
            seen.add(marker)
            found.append(path)
    return found


def is_split_config(config_dir: str, key: str, default_filename: str) -> bool:
    """True when the domain is served by anything other than the flat default."""
    sources = resolve_config_sources(config_dir, key, default_filename)
    default = os.path.normcase(
        os.path.abspath(os.path.join(config_dir, default_filename))
    )
    return not (
        len(sources) == 1
        and sources[0][0] == "file"
        and os.path.normcase(os.path.abspath(sources[0][1])) == default
    )


def default_write_target(
    config_dir: str, key: str, default_filename: str, split_filename: str
) -> str:
    """Where a newly created entry should be written.

    Flat installs keep their single file. Split installs get a dedicated file
    inside the first folder HA merges, rather than the config root (which HA no
    longer reads) or an existing user file (which would silently gain entries
    the user never put there).
    """
    for kind, source in resolve_config_sources(config_dir, key, default_filename):
        if kind == "dir":
            return os.path.join(source, split_filename)
        if kind == "file":
            return source
    return os.path.join(config_dir, default_filename)


def is_within(path: str, base: str) -> bool:
    """True when ``path`` really resolves inside ``base``.

    ``abspath`` + ``startswith`` is not enough on either count: it accepts
    ``/config/blueprints_evil`` for a ``/config/blueprints`` base, and it
    accepts a relative ``../../secrets.yaml`` whose joined form still starts
    with the base but whose resolved form does not. Symlinks are resolved too.
    """
    try:
        resolved = os.path.realpath(path)
        root = os.path.realpath(base)
        return resolved == root or os.path.commonpath([resolved, root]) == root
    except (OSError, ValueError):
        return False


def load_yaml_ha(path: str):
    """Parse a YAML file with HA's loader so !input / !secret / !include resolve.

    Returns HA node objects (``Input``, ...) for blueprint bodies: safe to *read*
    for plain metadata, NOT safe to ``json.dumps()`` or ``yaml.dump()``.
    """
    from homeassistant.util.yaml import load_yaml

    return load_yaml(path)


def parse_yaml_ha(text: str):
    """``parse_yaml()`` variant of :func:`load_yaml_ha` for in-memory strings."""
    from homeassistant.util.yaml import parse_yaml

    return parse_yaml(text)


def load_yaml_any(path: str):
    """Read a config YAML file for INSPECTION, tolerating HA-specific tags.

    Uses HA's loader so a split file carrying a nested ``!include`` is audited
    instead of being skipped; falls back to PyYAML when HA's loader is
    unavailable (unit tests, tooling). Parse errors propagate — the caller
    decides whether to log and continue.

    Read-only on purpose. ``!secret`` still raises here (HA's loader only
    resolves secrets when handed a secrets cache), which is the behaviour we
    want: a resolved secret must never be re-dumped into a config file in
    clear text. Anything that rewrites a file parses it with plain
    ``yaml.safe_load`` instead, so a file carrying HA tags is skipped rather
    than rewritten with its tags expanded.
    """
    try:
        return load_yaml_ha(path)
    except ImportError:
        import yaml

        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh)


def parse_yaml_any(text: str):
    """:func:`load_yaml_any` for in-memory strings."""
    try:
        return parse_yaml_ha(text)
    except ImportError:
        import yaml

        return yaml.safe_load(text)
