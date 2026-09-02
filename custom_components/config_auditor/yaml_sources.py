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
import re
from typing import NamedTuple

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

# HA's `*.yaml` glob runs through fnmatch/normcase: on a case-insensitive
# filesystem (macOS, Windows) it matches `Foo.YAML`, on a case-sensitive one
# (the containers and HAOS images almost everyone runs) it does not. The
# extension test has to follow the filesystem to stay identical to HA —
# lowercasing unconditionally would audit files HA skips, which is the exact
# bug this module was written to close.
_CASE_INSENSITIVE_FS = os.path.normcase("A") == "a"

# `!include some/where/fragment.yml` — a literal path, never a template, and
# `!include_dir_*` cannot match (`_` is not `\s`). Used to tell a `.yml` that is
# genuinely dead from one a sibling file pulls in explicitly.
_INCLUDE_RE = re.compile(r"!include\s+\S*?([\w.\-]+\.ya?ml)\b")
_INCLUDE_READ_LIMIT = 1_000_000


def _has_ext(name: str, *extensions: str) -> bool:
    """True when *name* carries one of *extensions*, the way HA's glob sees it."""
    return (name.lower() if _CASE_INSENSITIVE_FS else name).endswith(extensions)


def _is_dead_extension(name: str) -> bool:
    """True for a YAML-looking file HA's ``*.yaml`` glob will not pick up.

    ``.yml`` everywhere, plus every case variant of ``.yaml`` on a
    case-sensitive filesystem: ``Config.YAML`` is loaded on macOS and skipped on
    the Linux containers, and only the second case is dead configuration.
    """
    lowered = name.lower()
    if not lowered.endswith((".yaml", ".yml")):
        return False
    if _CASE_INSENSITIVE_FS:
        return lowered.endswith(".yml")
    return not name.endswith(".yaml")


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
    """Every ``*.yaml`` under a folder, the way HA merges them.

    Recursive and sorted, symlinks not followed, dotfiles, dot-directories and
    ``__pycache__`` skipped — HA's own ``_find_files`` rules, so an editor's
    ``.swp`` or a symlink loop can neither pollute nor wedge the scan.

    ``.yml`` is deliberately NOT matched: the four ``!include_dir_*``
    constructors all glob ``*.yaml``, so a ``.yml`` file sitting in a merged
    folder is never loaded by Home Assistant. Auditing it produced findings on
    entries that do not exist — the inverse of the blind spot this module was
    written to close. :func:`find_unloaded_yaml_files` reports those files as
    an issue instead of silently scanning them.
    """
    if not os.path.isdir(directory):
        return []
    found: list[str] = []
    for root, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs if not d.startswith(".") and d != "__pycache__"
        )
        for name in sorted(files):
            if name.startswith(".") or not _has_ext(name, ".yaml"):
                continue
            found.append(os.path.join(root, name))
    return found


def resolve_packages_sources(config_dir: str) -> list[Source]:
    """Sources declared by ``homeassistant: packages:`` — nothing by default.

    ``packages:`` differs from the domain keys on two counts, and both were
    getting in the way of a correct audit: it is nested one level under
    ``homeassistant:``, so :func:`resolve_config_sources` (top level only, by
    design) cannot see it, and it has **no default location** — a ``packages/``
    folder that is not declared is not loaded by Home Assistant, so auditing
    one produced findings on entries that do not exist.

    Both spellings are returned: ``packages: !include_dir_named pkgs/`` gives a
    directory source, an inline mapping gives one source per ``!include``d
    value. An empty list means HA loads no packages at all.
    """
    try:
        with open(os.path.join(config_dir, "configuration.yaml"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []

    sources: list[Source] = []
    in_ha_block = False
    mapping_indent: int | None = None

    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if indent == 0:
            in_ha_block = line.partition(":")[0].rstrip() == "homeassistant"
            mapping_indent = None
            continue
        if not in_ha_block:
            continue

        if mapping_indent is not None:
            if indent > mapping_indent:
                # `pack_name: !include packages/pack.yaml` inside the mapping.
                source = _as_source(_clean_value(line.partition(":")[2]), config_dir)
                if source is not None:
                    sources.append(source)
                continue
            mapping_indent = None  # dedented out of the packages mapping

        head, sep, rest = line.partition(":")
        if not sep or head.strip() != "packages":
            continue
        value = _clean_value(rest)
        if value:
            source = _as_source(value, config_dir)
            if source is not None:
                sources.append(source)
        else:
            mapping_indent = indent

    return sources


def find_unloaded_in_sources(sources: list[Source]) -> list[str]:
    """``.yml`` files sitting in a merged folder that nothing pulls in.

    Only directory sources are walked: ``automation: !include foo.yml`` is a
    single file and loads fine, it is the ``!include_dir_*`` glob that is
    ``*.yaml``-only.

    A ``.yml`` named by an explicit ``!include`` from a sibling file **is**
    loaded — ``!include`` takes a literal path and is not extension-restricted
    — so the walk collects the ``!include`` targets at the same time and drops
    those candidates. Without that pass the check told the user to rename a
    file that is in use, and the rename breaks the config twice over: the old
    name 404s, and the renamed file is then swept up by the ``*.yaml`` glob as
    a top-level entry whose shape is wrong. Matching is on the basename, so two
    same-named ``.yml`` in different folders suppress each other — the right
    trade for a compliance hint, whose cost of a false positive is a user
    breaking a working config.
    """
    candidates: list[str] = []
    included: set[str] = set()

    for kind, source in sources:
        if kind != "dir" or not os.path.isdir(source):
            continue
        for root, dirs, files in os.walk(source, followlinks=False):
            dirs[:] = sorted(
                d for d in dirs if not d.startswith(".") and d != "__pycache__"
            )
            for name in sorted(files):
                if name.startswith(".") or not name.lower().endswith((".yaml", ".yml")):
                    continue
                path = os.path.join(root, name)
                if _is_dead_extension(name):
                    candidates.append(path)
                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        text = fh.read(_INCLUDE_READ_LIMIT)
                except (OSError, UnicodeDecodeError):
                    continue
                included.update(_INCLUDE_RE.findall(text))

    found: list[str] = []
    seen: set[str] = set()
    for path in candidates:
        if os.path.basename(path) in included:
            continue
        marker = os.path.normcase(os.path.abspath(path))
        if marker in seen:
            continue
        seen.add(marker)
        found.append(path)
    return found


def find_unloaded_yaml_files(
    config_dir: str, key: str, default_filename: str
) -> list[str]:
    """:func:`find_unloaded_in_sources` for a top-level domain key."""
    return find_unloaded_in_sources(
        resolve_config_sources(config_dir, key, default_filename)
    )


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


class ListScan(NamedTuple):
    """One pass over a list-shaped domain (automation, scene).

    ``files`` and ``skipped`` come from the same walk as the match, so the miss
    path can name what it searched and what it had to pass over without
    re-parsing the domain — which is exactly what it used to do, twice, on a
    folder that had just failed to yield a match.
    """

    path: str | None
    documents: list
    index: int
    files: list[str]
    skipped: list[str]


class NamedScan(NamedTuple):
    """One pass over a mapping-shaped domain (script). See :class:`ListScan`."""

    path: str | None
    mapping: dict
    key: str | None
    files: list[str]
    skipped: list[str]


class DomainLoad(NamedTuple):
    """Every parsed file of a list-shaped domain, plus what could not be read."""

    loaded: list[tuple[str, list]]
    files: list[str]
    skipped: list[str]


def read_plain_yaml(path: str):
    """Parse one config file with plain PyYAML, for the read-modify-write paths.

    Deliberately NOT HA's loader: these paths dump the parsed data back to
    disk, and HA's loader expands ``!secret`` / ``!include``, which would
    inline a secret in clear text or flatten an include into the file. A file
    carrying HA tags fails to parse here and is skipped — the caller reports
    "not found" instead of rewriting it wrongly. Use :func:`load_yaml_any` for
    read-only inspection.
    """
    import yaml

    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def scan_list_domain(
    config_dir: str, key: str, default_filename: str, match
) -> ListScan:
    """Find an entry in a list-shaped domain (automation, scene).

    Scans every file the domain key resolves to — a split config keeps its
    entries in several files — and returns the ``(path, documents, index)`` of
    the first match, with ``index`` at ``-1`` on a miss. Writes must go back to
    that one file.
    """
    files = iter_domain_files(config_dir, key, default_filename)
    skipped: list[str] = []
    for path in files:
        try:
            data = read_plain_yaml(path) or []
        except Exception:  # noqa: BLE001 — HA tags or a syntax error
            skipped.append(path)
            continue
        if not isinstance(data, list):
            continue
        for index, item in enumerate(data):
            if isinstance(item, dict) and match(item):
                return ListScan(path, data, index, files, skipped)
    return ListScan(None, [], -1, files, skipped)


def scan_named_domain(
    config_dir: str, key: str, default_filename: str, match
) -> NamedScan:
    """Find an entry in a mapping-shaped domain (script).

    Returns the ``(path, mapping, key_of_match)`` of the file that holds it,
    with ``key`` at ``None`` on a miss.
    """
    files = iter_domain_files(config_dir, key, default_filename)
    skipped: list[str] = []
    for path in files:
        try:
            data = read_plain_yaml(path) or {}
        except Exception:  # noqa: BLE001
            skipped.append(path)
            continue
        if not isinstance(data, dict):
            continue
        for entry_key, entry in data.items():
            if isinstance(entry, dict) and match(entry_key, entry):
                return NamedScan(path, data, entry_key, files, skipped)
    return NamedScan(None, {}, None, files, skipped)


def load_list_domain(config_dir: str, key: str, default_filename: str) -> DomainLoad:
    """Every ``(path, documents)`` pair for a list-shaped domain.

    For callers that need several matching passes in priority order across the
    whole config (exact id, then registry unique_id, then alias) rather than a
    first-match-wins scan.
    """
    files = iter_domain_files(config_dir, key, default_filename)
    loaded: list[tuple[str, list]] = []
    skipped: list[str] = []
    for path in files:
        try:
            data = read_plain_yaml(path) or []
        except Exception:  # noqa: BLE001
            skipped.append(path)
            continue
        if isinstance(data, list):
            loaded.append((path, data))
    return DomainLoad(loaded, files, skipped)


def write_yaml_documents(path: str, documents, sort_keys: bool = False) -> None:
    """Dump a parsed domain file back to disk, preserving key order by default."""
    import yaml

    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(
            documents, fh, allow_unicode=True,
            default_flow_style=False, sort_keys=sort_keys,
        )


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


def _tag_tolerant_loader():
    """A ``SafeLoader`` that renders every ``!tag`` as an opaque placeholder.

    ``!secret db_password`` comes back as the *string* ``"!secret db_password"``:
    the tag is preserved for a human reader, the secret itself is never looked
    up, so the value cannot leak into a report, an LLM prompt or a rewritten
    file. Same treatment for ``!include``, ``!input``, ``!env_var`` and any
    custom tag — an unresolved reference instead of a lost file.
    """
    import yaml

    class _TagTolerantLoader(yaml.SafeLoader):
        pass

    def _placeholder(loader, tag_suffix, node):
        if isinstance(node, yaml.ScalarNode):
            value = loader.construct_scalar(node)
        elif isinstance(node, yaml.SequenceNode):
            value = " ".join(str(v) for v in loader.construct_sequence(node))
        else:
            value = ""
        tag = f"!{tag_suffix}"
        return f"{tag} {value}".strip()

    _TagTolerantLoader.add_multi_constructor("!", _placeholder)
    return _TagTolerantLoader


def load_yaml_any(path: str):
    """Read a config YAML file for INSPECTION, tolerating HA-specific tags.

    Uses HA's loader first, so a split file carrying a nested ``!include`` is
    audited with the include expanded. HA's loader refuses ``!secret`` outside
    a secrets cache, and used to take the whole file down with it: every caller
    catches the exception and moves on, so a single ``!secret`` line made an
    entire scripts file invisible to the audit — fifty scripts, zero issues,
    silently. Such a file is re-read with :func:`_tag_tolerant_loader`, which
    keeps the entries and turns the tags into placeholder strings.

    Read-only on purpose, and safe to re-dump *as inspected*: no secret is ever
    resolved, on either path. Anything that rewrites a config file still parses
    it with plain ``yaml.safe_load`` (see ``_read_plain_yaml``), so a file
    carrying HA tags is skipped rather than rewritten with a placeholder in
    place of its tag. Genuine parse errors still propagate — the caller decides
    whether to log and continue.
    """
    import yaml

    try:
        return load_yaml_ha(path)
    except ImportError:
        original: Exception | None = None  # HA absent (unit tests, tooling)
    except Exception as exc:
        original = exc

    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.load(fh, Loader=_tag_tolerant_loader())
    except Exception:
        if original is not None:
            raise original from None
        raise


def parse_yaml_any(text: str):
    """:func:`load_yaml_any` for in-memory strings."""
    import yaml

    try:
        return parse_yaml_ha(text)
    except ImportError:
        original: Exception | None = None
    except Exception as exc:
        original = exc

    try:
        return yaml.load(text, Loader=_tag_tolerant_loader())
    except Exception:
        if original is not None:
            raise original from None
        raise
