"""The one way HACA rewrites a Home Assistant YAML config file.

Four different strategies used to coexist here, with four behaviours on the
user's comments: ``recorder_yaml_editor`` round-tripped through ruamel and kept
them, ``websocket.apply_field_fix`` did too since 1.8.0, while
``refactoring_assistant``, ``automation_optimizer`` and the MCP write tools read
with ``yaml.safe_load`` and dumped the whole file back with ``yaml.dump`` --
which silently deleted every comment and blank line in a file the user
maintains by hand, not just around the entry being edited.

Everything that edits an existing config file now goes through this module:

* :func:`read_for_edit` parses in **ruamel round-trip** mode, so comments, key
  order, quoting style and anchors survive the edit, and the file is written
  back in its own layout -- Home Assistant's editor style or the docs style;
* it refuses a file carrying an unresolved Home Assistant tag (``!secret``,
  ``!include``, ``!input``) -- rewriting one would inline a secret in clear
  text or flatten an include, so the caller reports "not found" instead;
* :func:`write_back` snapshots the file into ``.haca_backups`` and writes
  **atomically** (sibling temp file + ``os.replace``), so a crash mid-write
  cannot leave Home Assistant with half a config;
* the shared ruamel instance quotes a new string Home Assistant would read back
  as something else (``off`` as ``False``, ``22:00:00`` as a number), and
  leaves the bare ones already in the file exactly as they are;
* the domain scanners locate an entry across every file a domain key resolves
  to -- a split config keeps its entries in several files -- and hand back the
  matched node *still attached to its document*, so the caller mutates it and
  calls :func:`write_back` on the one file that holds it;
* :func:`async_write_checked` checks an automation, script or scene the way
  Home Assistant's own editor does before writing it -- a reload that
  disables an invalid entry still succeeds, so the check has to come first --
  and :func:`async_write_and_reload` adds the reload, putting the file back
  if it fails.

:mod:`yaml_sources` stays the authority on *where* a domain's files are, and
keeps the plain-PyYAML readers the read-only audit paths use. This module is
the write side, and the only one.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import functools
import io
import logging
import os
import re
import shutil
from typing import Any, Callable, NamedTuple

from .const import BACKUP_DIR
from .yaml_sources import iter_domain_files

_LOGGER = logging.getLogger(__name__)

# Backups kept per source file. Per *file*, not per directory: on a split
# config `kitchen.yaml`'s edits used to evict `bedroom.yaml`'s snapshots, and
# now that the MCP tools take snapshots too, one chatty agent session would
# otherwise wipe every backup the panel offers to restore.
BACKUP_KEEP = 10

# Every snapshot sits in a folder of its own source file, at that file's path
# under the config dir: `.haca_backups/files/automations/kitchen.yaml/
# 20260923_101500.yaml` is a copy of `automations/kitchen.yaml`. The folder is
# where a restore writes, so two files of one name -- a script file and an
# automation file both called `lights.yaml` on a split config, two blueprints
# in different folders -- can neither be restored into each other nor evict
# each other's snapshots.
FILE_SNAPSHOT_DIR = "files"

# `<YYYYmmdd_HHMMSS>[_<seq>].yaml` -- a snapshot inside its file's folder.
_SNAPSHOT_NAME_RE = re.compile(r"^(?P<ts>\d{8}_\d{6})(?:_(?P<seq>\d+))?\.yaml$")

# `<stem>_<YYYYmmdd_HHMMSS>[_<seq>].yaml` at the top of .haca_backups: the
# flat layout written up to 1.8.0. Only the stem says where such a backup came
# from, so its restore still looks the stem up among the automation files, as
# it always did. Nothing writes this layout any more.
_BACKUP_NAME_RE = re.compile(
    r"^(?P<stem>.+)_(?P<ts>\d{8}_\d{6})(?:_(?P<seq>\d+))?\.yaml$"
)

# Never `.yaml`: a temp file inside `automations/` must not be picked up by
# Home Assistant's `*.yaml` glob, nor reported as dead config by our own audit.
_TMP_SUFFIX = ".haca-tmp"


class UnsafeToEdit(Exception):
    """This file must not be rewritten -- the caller skips it and says so.

    Raised for an unresolved HA tag, a root shape the domain does not expect, a
    syntax error, or a duplicate key (ruamel refuses those, where ``safe_load``
    silently kept the last one and a rewrite would have dropped the other).
    """


class EditTarget(NamedTuple):
    """One config file, parsed and open for editing."""

    path: str
    yaml: Any       # the ruamel instance that parsed `document` -- reuse it to dump
    document: Any   # file root: a list for automations/scenes, a mapping for scripts


class DomainEdit(NamedTuple):
    """Every editable file of one domain, plus the ones passed over."""

    targets: list[EditTarget]
    files: list[str]
    skipped: list[str]


class EditScan(NamedTuple):
    """Where one entry lives, with its file already open for editing.

    ``entry`` is the matched node *inside* ``document``: mutate it in place,
    then hand ``target`` to :func:`write_back`.
    """

    target: EditTarget | None
    entry: Any
    index: int          # list-shaped domains; -1 on a miss
    key: str | None     # mapping-shaped domains; None otherwise
    files: list[str]
    skipped: list[str]

    @property
    def found(self) -> bool:
        return self.target is not None

    # Passthroughs so a call site reads the same whether it holds the scan or
    # the target -- `match.yaml.dump(...)`, `write_back(match.target)`.
    @property
    def path(self) -> str | None:
        return self.target.path if self.target else None

    @property
    def yaml(self) -> Any:
        return self.target.yaml if self.target else None

    @property
    def document(self) -> Any:
        return self.target.document if self.target else None


_MISS = EditScan(None, None, -1, None, [], [])


# -- Reading -----------------------------------------------------------------


def contains_ha_tag(node: Any) -> bool:
    """True when a round-trip tree still carries a Home Assistant tag.

    ruamel keeps unknown tags (``!secret``, ``!include``, ``!input``) as nodes
    with a ``tag`` attribute. It can dump them back faithfully, but the entry we
    are about to edit may well *be* the include, and a ``!secret`` we rewrite is
    a secret we may inline -- so every write path treats a tagged file the way
    ``yaml.safe_load`` already did: it skips it, and the caller says the entry
    has to be edited by hand.
    """
    tag = getattr(node, "tag", None)
    if tag is not None:
        value = getattr(tag, "value", tag)
        if isinstance(value, str) and value.startswith("!"):
            return True
    if isinstance(node, dict):
        return any(contains_ha_tag(v) for v in node.values())
    if isinstance(node, (list, tuple)):
        return any(contains_ha_tag(v) for v in node)
    return False


_YAML_STR = "tag:yaml.org,2002:str"


@functools.lru_cache(maxsize=None)
def _home_assistant_scalars():
    """``(Constructor, Representer)`` that write a string back as HA will read it.

    ruamel writes YAML 1.2; Home Assistant reads with PyYAML, which is YAML 1.1.
    ruamel quotes a string that would read back as a number or a date, but where
    the two specs disagree it leaves the string bare and HA converts it: ``off``
    comes back ``False``, ``22:00:00`` comes back ``79200`` (base 60). A trigger
    ``to: off`` is then rejected and the automation disabled; ``hvac_mode: off``
    passes validation and the call silently does nothing.

    The question "would HA misread this?" goes to PyYAML's own resolver, the one
    HA's loader uses, rather than to a list of words -- a list had already
    missed the times.

    * The **representer** single-quotes such a string, the way HA's own dumper
      does. It only sees exact ``str``: a new value, from an MCP call or the
      panel -- JSON tells ``"off"`` apart from ``false``, so it is a string.
    * The **constructor** turns such a string already bare in the file into a
      ``PlainScalarString``, which is written back bare. An untouched
      ``flag: off`` keeps its bytes and the ``False`` HA has always read there;
      quoting it would hand a template the truthy string ``"off"``.
    """
    from ruamel.yaml.constructor import RoundTripConstructor
    from ruamel.yaml.representer import RoundTripRepresenter
    from ruamel.yaml.scalarstring import PlainScalarString
    import yaml as pyyaml

    resolver = pyyaml.resolver.Resolver()

    def misread(value: str) -> bool:
        return resolver.resolve(pyyaml.ScalarNode, value, (True, False)) != _YAML_STR

    class Constructor(RoundTripConstructor):
        def construct_yaml_str(self, node):
            value = super().construct_yaml_str(node)
            # Quoted scalars come back as ScalarString subclasses
            # (preserve_quotes), `!!str` as a TaggedScalar: only a bare one is
            # an exact str.
            if type(value) is str and misread(value):
                return PlainScalarString(value)
            return value

    Constructor.add_constructor(_YAML_STR, Constructor.construct_yaml_str)

    class Representer(RoundTripRepresenter):
        pass

    def represent_str(representer, data):
        if misread(data):
            return representer.represent_scalar(_YAML_STR, data, style="'")
        return representer.represent_str(data)

    # Dispatch is on the exact type, so the ScalarString subclasses -- the
    # pinned PlainScalarString included -- keep their own representers.
    Representer.add_representer(str, represent_str)
    return Constructor, Representer


class _Layout(NamedTuple):
    """How a file indents its blocks and wraps its long values."""

    mapping: int  # a nested mapping, from its key
    offset: int   # a block sequence's dash, from its key
    width: int    # where a long value is wrapped


# For a file with nothing to measure -- a new one, or one without a nested
# list -- the layout of Home Assistant's docs, which HACA has always written.
_DEFAULT_LAYOUT = _Layout(mapping=2, offset=2, width=80)

# PyYAML breaks a long value at the first space past column 80, so a file with
# a space further right was not wrapped by a dumper: its long lines are the
# user's own, and stay long.
_WRAPPED_BY_A_DUMPER = 81
_NO_WRAP = 4096

# A key opening a block (`triggers:`), and any key -- quoted, flow and tagged
# keys are left out, which only makes the vote smaller.
_BLOCK_KEY_RE = re.compile(r"^[^\s#'\"{\[&*!|>%@`][^#]*:$")
_KEY_RE = re.compile(r"^[^\s#'\"{\[&*!|>%@`-][^#]*?:(\s|$)")

# Document markers and directives: always at column 0, and never content.
_NOT_CONTENT = ("---", "...", "%")


def _measure_layout(text: str) -> _Layout:
    """How *text* lays out its blocks, measured where a key opens one.

    Home Assistant's editor writes a list flush with its key (``triggers:``
    then ``- trigger:``); its docs, and most hand-written files, indent it by
    two. The most common spacing wins, so one entry pasted in the other style
    does not flip the whole file.
    """
    offsets: Counter[int] = Counter()
    mappings: Counter[int] = Counter()
    opener: int | None = None  # column of the key that opened a block just above
    long_lines = False
    for line in text.splitlines():
        content = line.strip()
        if not content or content.startswith("#"):
            continue
        long_lines = long_lines or " " in line[_WRAPPED_BY_A_DUMPER:]
        lead = len(line) - len(line.lstrip(" "))
        if opener is not None:
            if (content == "-" or content.startswith("- ")) and lead >= opener:
                offsets[lead - opener] += 1
            elif lead > opener and _KEY_RE.match(content):
                mappings[lead - opener] += 1
        # In `- - key:` the key sits after every dash on the line.
        body, column = content, lead
        while body.startswith("- "):
            rest = body[2:].lstrip(" ")
            column += len(body) - len(rest)
            body = rest
        opener = column if _BLOCK_KEY_RE.match(body.split(" #")[0].rstrip()) else None
    return _Layout(
        mappings.most_common(1)[0][0] if mappings else _DEFAULT_LAYOUT.mapping,
        offsets.most_common(1)[0][0] if offsets else _DEFAULT_LAYOUT.offset,
        _NO_WRAP if long_lines else _DEFAULT_LAYOUT.width,
    )


def _starts_with_a_list(text: str) -> bool:
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#") and not line.startswith(_NOT_CONTENT):
            return line.startswith("- ") or line.rstrip() == "-"
    return False


def _indent_lines(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(
        line if not line.strip() or line.startswith(_NOT_CONTENT) else pad + line
        for line in text.splitlines(keepends=True)
    )


def _dedent_lines(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "".join(
        line[spaces:] if line.startswith(pad) else line
        for line in text.splitlines(keepends=True)
    )


@functools.lru_cache(maxsize=None)
def _layout_keeping_yaml():
    """The ruamel ``YAML`` class HACA reads and writes with.

    It writes a file back laid out the way it was, so the diff of an edit is
    the lines that changed. A stock round-trip instance gets three things wrong:

    * **Indentation is one setting per instance**, not per file, so a file
      in Home Assistant's editor style (lists flush with their key) came back
      in the docs style, or the other way round. :meth:`load` measures the
      file and sets it (:func:`_measure_layout`).
    * **The dash offset applies at the root too**: a root list came back
      indented by two. The dump removes that indent. The load first adds it,
      because ruamel puts a comment back at its original column: shifting only
      the output would move every comment two columns left.
    * **A long plain value is wrapped differently from PyYAML**, which Home
      Assistant writes its files with: ruamel moves a word that would cross
      the width to the next line, PyYAML lets it cross and breaks after. A
      plain value is written by PyYAML's own code, run on ruamel's emitter --
      the attributes it reads have the same names in both, ruamel being a
      fork of it -- and libyaml, the C dumper HA uses when it can, wraps it
      the same way. Quoted values already wrap like libyaml. A file with long
      lines of its own is not wrapped at all.
    """
    from ruamel.yaml import YAML
    from ruamel.yaml.emitter import Emitter
    import yaml as pyyaml

    constructor, representer = _home_assistant_scalars()

    class HomeAssistantEmitter(Emitter):
        def write_plain(self, text, split=True):
            # A root-level scalar is ruamel's own business.
            if self.root_context:
                return super().write_plain(text, split)
            return pyyaml.emitter.Emitter.write_plain(self, text, split)

    class LayoutKeepingYaml(YAML):
        def __init__(self):
            super().__init__()  # round-trip
            self.Constructor = constructor
            self.Representer = representer
            self.Emitter = HomeAssistantEmitter
            self.preserve_quotes = True
            self._use(_DEFAULT_LAYOUT)

        def _use(self, layout: _Layout) -> None:
            self.file_layout = layout
            self.indent(
                mapping=layout.mapping,
                sequence=layout.offset + 2,
                offset=layout.offset,
            )

        def load(self, stream):
            text = stream if isinstance(stream, str) else stream.read()
            text = text.lstrip("﻿")
            self._use(_measure_layout(text))
            if self.file_layout.offset and _starts_with_a_list(text):
                text = _indent_lines(text, self.file_layout.offset)
            return super().load(text)

        def dump(self, data, stream=None, *, transform=None):
            shift = self.file_layout.offset if isinstance(data, list) else 0
            # The root indent is removed after wrapping: widen by as much.
            self.width = self.file_layout.width + shift
            if shift:
                then = transform

                def transform(output):
                    output = _dedent_lines(output, shift)
                    return then(output) if then else output

            return super().dump(data, stream, transform=transform)

    return LayoutKeepingYaml


def roundtrip_yaml():
    """The configured ruamel instance every read and write in HACA shares.

    It writes a file back the way Home Assistant will read it
    (:func:`_home_assistant_scalars`) and the way the file was laid out
    (:func:`_layout_keeping_yaml`). Use one instance per file: loading a file
    sets the instance to that file's layout.
    """
    return _layout_keeping_yaml()()


def read_for_edit(path: str, shape: type | None = None) -> EditTarget:
    """Parse a config file for editing, or refuse it.

    *shape* -- ``list`` or ``dict`` -- is the root the domain expects; a file of
    the wrong shape is refused rather than replaced with something else.

    Raises :class:`UnsafeToEdit` for anything that must not be rewritten, so a
    caller scanning several files can skip this one and keep going. Genuine
    parse errors are wrapped in it too: the caller's answer is the same.
    """
    yaml = roundtrip_yaml()
    try:
        with open(path, encoding="utf-8") as fh:
            data = yaml.load(fh)
    except Exception as exc:  # noqa: BLE001 -- syntax error, duplicate key, unreadable
        raise UnsafeToEdit(f"{path}: {exc}") from exc

    if data is None:
        raise UnsafeToEdit(f"{path}: parsed as empty")
    if contains_ha_tag(data):
        raise UnsafeToEdit(f"{path}: carries a Home Assistant tag")
    if shape is not None and not isinstance(data, shape):
        raise UnsafeToEdit(f"{path}: root is not a {shape.__name__}")
    return EditTarget(path, yaml, data)


def open_or_create(path: str, shape: type) -> EditTarget:
    """:func:`read_for_edit`, but an absent or blank file starts a new document.

    The create tools append to whichever file the domain key resolves to, and
    on a fresh install that file does not exist yet. A file that exists and has
    content but cannot be rewritten still raises :class:`UnsafeToEdit` — a
    create must never replace a file it was unable to read.
    """
    try:
        return read_for_edit(path, shape)
    except UnsafeToEdit:
        try:
            with open(path, encoding="utf-8") as fh:
                blank = not fh.read().strip()
        except OSError:
            blank = not os.path.exists(path)
        if not blank:
            raise
    return EditTarget(path, roundtrip_yaml(), shape())


# -- Writing -----------------------------------------------------------------


def parse_backup_name(name: str) -> tuple[str, str] | None:
    """``(source stem, timestamp)`` of a HACA backup name, or None.

    Keeps the listing, the restore and the pruning off unrelated files a user
    may have dropped into ``.haca_backups``. The timestamp comes back as its
    raw ``YYYYmmdd_HHMMSS`` text: it is the creation time the listing shows,
    which ``st_mtime`` would misreport after a copy or a restore.
    """
    match = _BACKUP_NAME_RE.match(name)
    return (match.group("stem"), match.group("ts")) if match else None


def backup_stem(name: str) -> str | None:
    """The source stem behind a HACA backup name, or None for anything else."""
    parsed = parse_backup_name(name)
    return parsed[0] if parsed else None


class BackupFile(NamedTuple):
    """One snapshot in ``.haca_backups``, in either layout."""

    path: str
    # The file a restore writes, relative to the config dir with "/" -- None
    # for a flat backup from 1.8.0 or earlier, which only carries a stem.
    source: str | None
    stem: str
    timestamp: str  # raw YYYYmmdd_HHMMSS
    sequence: int   # 1, then 2, 3... for later snapshots within one second


def _age(timestamp: str, sequence: str | None) -> tuple[str, int]:
    """Sort key, oldest first. The sequence compares as a number: by name,
    `_10` sorted before `_2`, and pruning deleted the wrong one."""
    return timestamp, int(sequence or 1)


def _config_relative(config_dir: str, source: str) -> str:
    """*source*'s path under the config dir; ValueError when it is not under it.

    Tried as written first, then with links resolved: a file linked in from
    elsewhere keeps the place Home Assistant reads it from, and a config dir
    that is itself a link still matches a caller that resolved its path.
    """
    for resolve in (os.path.abspath, os.path.realpath):
        root, path = resolve(config_dir), resolve(source)
        try:
            if path != root and os.path.commonpath([root, path]) == root:
                return os.path.relpath(path, root)
        except ValueError:  # another drive, on Windows
            continue
    raise ValueError(f"{source} is outside the config directory {config_dir}")


def create_backup(config_dir: str, source: str) -> str:
    """Snapshot *source* into its own folder under ``.haca_backups/files``.

    Keeps the newest :data:`BACKUP_KEEP` of that one file and returns the
    copy's path. Raises when there is no such file, or when it lies outside
    the config dir.
    """
    if not os.path.isfile(source):
        raise FileNotFoundError(f"nothing to back up at {source}")
    folder = os.path.join(
        os.path.abspath(config_dir), BACKUP_DIR, FILE_SNAPSHOT_DIR,
        _config_relative(config_dir, source),
    )
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # One-second timestamps collide, so a later snapshot in the same second is
    # numbered after the highest one still there -- not into the first free
    # name: pruning frees the oldest names first, and a snapshot that took one
    # sorted as the oldest and was deleted the moment it was written.
    sequence = 1 + max(
        (
            int(match["seq"] or 1)
            for match in map(_SNAPSHOT_NAME_RE.match, os.listdir(folder))
            if match and match["ts"] == timestamp
        ),
        default=0,
    )
    while True:
        name = f"{timestamp}.yaml" if sequence == 1 else f"{timestamp}_{sequence}.yaml"
        backup = os.path.join(folder, name)
        if not os.path.exists(backup):
            break
        sequence += 1

    shutil.copy2(source, backup)
    _prune_folder(folder)
    return backup


def snapshot_file(config_dir: str, source: str) -> str | None:
    """:func:`create_backup`, or None when *source* does not exist yet.

    For a write that may create its file: a new file has nothing to lose. A
    snapshot that cannot be taken still raises -- the caller must not write
    without one.
    """
    if not os.path.isfile(source):
        return None
    return create_backup(config_dir, source)


def backup_source(config_dir: str, backup: str) -> str | None:
    """The file a snapshot restores to, or None when *backup* is not one.

    Only the per-file layout answers: a flat backup from 1.8.0 or earlier
    carries a stem, not a path. A folder that would restore into a hidden
    directory, or a file other than YAML, is refused as well: HACA never
    snapshots one, so it did not make that folder.
    """
    root = os.path.realpath(os.path.join(config_dir, BACKUP_DIR, FILE_SNAPSHOT_DIR))
    path = os.path.realpath(backup)
    if not _SNAPSHOT_NAME_RE.match(os.path.basename(path)):
        return None
    try:
        if os.path.commonpath([root, path]) != root:
            return None
    except ValueError:
        return None
    rel = os.path.relpath(os.path.dirname(path), root)
    parts = rel.replace(os.sep, "/").split("/")
    if rel == os.curdir or any(p.startswith(".") for p in parts):
        return None
    if os.path.splitext(parts[-1])[1].lower() not in (".yaml", ".yml"):
        return None
    return os.path.join(os.path.abspath(config_dir), rel)


def list_backup_files(config_dir: str) -> list[BackupFile]:
    """Every snapshot in ``.haca_backups``, both layouts, newest first.

    Anything else a user may have dropped in there -- the recorder editor's
    ``configuration.yaml.<ts>.bak`` included -- is left out.
    """
    base = os.path.join(config_dir, BACKUP_DIR)
    found: list[BackupFile] = []
    try:
        names = os.listdir(base)
    except OSError:
        return found
    for name in names:
        match = _BACKUP_NAME_RE.match(name)
        path = os.path.join(base, name)
        if match and os.path.isfile(path):
            found.append(BackupFile(
                path, None, match["stem"], match["ts"], int(match["seq"] or 1),
            ))
    config_root = os.path.abspath(config_dir)
    for folder, dirs, files in os.walk(os.path.join(base, FILE_SNAPSHOT_DIR)):
        dirs.sort()
        for name in files:
            match = _SNAPSHOT_NAME_RE.match(name)
            path = os.path.join(folder, name)
            source = backup_source(config_dir, path) if match else None
            if source is None:
                continue
            found.append(BackupFile(
                path,
                os.path.relpath(source, config_root).replace(os.sep, "/"),
                os.path.splitext(os.path.basename(source))[0],
                match["ts"],
                int(match["seq"] or 1),
            ))
    found.sort(key=lambda b: (b.timestamp, b.sequence), reverse=True)
    return found


def prune_backups(config_dir: str) -> None:
    """Keep the newest :data:`BACKUP_KEEP` snapshots of each source file.

    A flat backup from 1.8.0 or earlier counts against its stem, as it did.
    """
    groups: dict[tuple[str, str], list[BackupFile]] = {}
    for backup in list_backup_files(config_dir):
        key = ("file", backup.source) if backup.source else ("stem", backup.stem)
        groups.setdefault(key, []).append(backup)
    for group in groups.values():
        for old in group[BACKUP_KEEP:]:  # newest first already
            _unlink_backup(old.path)


def _prune_folder(folder: str) -> None:
    """:func:`prune_backups` for the one file whose folder this is."""
    try:
        names = [n for n in os.listdir(folder) if _SNAPSHOT_NAME_RE.match(n)]
    except OSError:
        return
    names.sort(key=lambda n: _age(*_SNAPSHOT_NAME_RE.match(n).group("ts", "seq")),
               reverse=True)
    for old in names[BACKUP_KEEP:]:
        _unlink_backup(os.path.join(folder, old))


def _unlink_backup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError as exc:
        _LOGGER.warning("Could not delete old backup %s: %s", path, exc)


def restore_snapshot(config_dir: str, backup: str, destination: str) -> str | None:
    """Put *backup* back over *destination*, atomically.

    Snapshots the file it replaces first and returns that snapshot's path
    (None when *destination* no longer exists, a deleted blueprint say). The
    backup is read before that snapshot is taken: taking it prunes, and the
    backup being restored may be the oldest one kept.
    """
    with open(backup, "rb") as fh:
        content = fh.read()
    replaced = snapshot_file(config_dir, destination)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    tmp = f"{destination}{_TMP_SUFFIX}"
    try:
        with open(tmp, "wb") as fh:
            fh.write(content)
        _copy_mode(destination, tmp)
        os.replace(tmp, destination)
    except Exception:
        _discard(tmp)
        raise
    return replaced


def atomic_write(path: str, content: str, encoding: str = "utf-8") -> None:
    """Replace a file's whole content in one step.

    The write goes to a sibling temp file and is then renamed over the target,
    so a concurrent reader -- Home Assistant reloading, in practice -- sees
    either the old file or the new one, never a truncated state.
    ``os.replace`` is atomic on POSIX and on Windows within a volume.

    For content HACA produces itself (a rendered blueprint, an export). An edit
    of a file the user maintains goes through :func:`write_back` instead, which
    keeps the comments the dump would drop.
    """
    tmp = f"{path}{_TMP_SUFFIX}"
    try:
        with open(tmp, "w", encoding=encoding) as fh:
            fh.write(content)
        _copy_mode(path, tmp)
        os.replace(tmp, path)
    except Exception:
        _discard(tmp)
        raise


def write_back(target: EditTarget, config_dir: str | None = None) -> str | None:
    """Dump a round-trip tree back over its file, atomically.

    Takes a backup first when *config_dir* is given, and returns its path; pass
    ``None`` only when the caller has already snapshotted the file. A file
    :func:`open_or_create` is about to bring into existence has nothing to
    snapshot, and comes back with no backup path rather than an error.
    """
    backup = (
        create_backup(config_dir, target.path)
        if config_dir and os.path.isfile(target.path)
        else None
    )

    tmp = f"{target.path}{_TMP_SUFFIX}"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            target.yaml.dump(target.document, fh)
        _copy_mode(target.path, tmp)
        os.replace(tmp, target.path)
    except Exception:
        _discard(tmp)
        raise
    return backup


def _copy_mode(source: str, tmp: str) -> None:
    """Carry the target's permission bits onto the replacement, best effort.

    ``os.replace`` swaps inodes, so without this a rewritten file comes back
    with the umask default instead of whatever the user had set on it.
    """
    try:
        shutil.copymode(source, tmp)
    except OSError:
        pass


def _discard(tmp: str) -> None:
    try:
        os.unlink(tmp)
    except OSError:
        pass


# -- Writing an entry Home Assistant reloads ----------------------------------


class RejectedByHomeAssistant(Exception):
    """Home Assistant would not load this entry, so it was not written."""


def _as_home_assistant_reads(yaml: Any, entry: Any) -> Any:
    """*entry* dumped the way it will be written, then read by HA's own loader."""
    from homeassistant.util.yaml.loader import parse_yaml

    buffer = io.StringIO()
    yaml.dump(entry, buffer)
    return parse_yaml(buffer.getvalue())


async def async_validation_error(
    hass: Any, domain: str, yaml: Any, entry: Any, key: str | None
) -> str | None:
    """What Home Assistant's own editor says about *entry*, or None if it accepts it.

    The editor runs these validators before it saves an automation, a script or
    a scene, and the reload runs the same ones -- but where the editor refuses,
    the reload keeps going: it disables the entry, logs, and succeeds. The entry
    is checked as HA will read it back from the file, not as HACA holds it, so a
    value the YAML round trip would turn into something else is caught too.

    Only a validation error counts. A validator that cannot run -- an older
    Home Assistant without it, or one that fails outright -- leaves the write
    to the reload and its rollback, as before.
    """
    # Home Assistant before voluptuous: it installs the `voluptuous` its
    # validators raise from, and a `vol.Invalid` taken elsewhere misses them.
    from homeassistant.exceptions import HomeAssistantError
    import voluptuous as vol

    try:
        config = await hass.async_add_executor_job(_as_home_assistant_reads, yaml, entry)
        if domain == "automation":
            from homeassistant.components.automation.config import (
                async_validate_config_item,
            )

            await async_validate_config_item(hass, str(key or ""), config)
        elif domain == "script":
            from homeassistant.components.script.config import (
                async_validate_config_item,
            )

            await async_validate_config_item(hass, str(key or ""), config)
        elif domain == "scene":
            from homeassistant.components.scene import PLATFORM_SCHEMA

            PLATFORM_SCHEMA(config)
    except (vol.Invalid, HomeAssistantError) as err:
        return str(err)
    except Exception as err:  # noqa: BLE001 -- see the docstring
        _LOGGER.debug("Could not validate the %s before writing it: %s", domain, err)
    return None


async def async_write_checked(
    hass: Any,
    target: EditTarget,
    domain: str,
    *,
    entry: Any = None,
    key: str | None = None,
) -> str | None:
    """Round-trip write, once Home Assistant's own editor would accept *entry*.

    *entry* -- the automation, script or scene being created or updated, with
    its *key* (automation id, script id) -- is checked the way the editor
    checks it before it saves, and one it would reject raises
    :class:`RejectedByHomeAssistant` with nothing written. A removal passes no
    entry: removing cannot make an entry invalid, and must work on a broken one.

    The tree goes back through :func:`write_back`, so the comments and
    formatting around the entry survive, and a snapshot lands in
    ``.haca_backups`` first. Called directly by the panel's fixes that leave
    the reload to the user: Home Assistant would disable a rejected entry at
    that reload, long after the fix reported success.

    Returns the backup path, or None when this call created the file.
    """
    if entry is not None:
        await async_check_entry(hass, domain, target.yaml, entry, key)

    return await hass.async_add_executor_job(
        write_back, target, hass.config.config_dir
    )


async def async_check_entry(
    hass: Any, domain: str, yaml: Any, entry: Any, key: str | None
) -> None:
    """Raise :class:`RejectedByHomeAssistant` if HA's own editor would refuse *entry*.

    The check alone, for a caller writing several entries at once: each one is
    checked before any is written.
    """
    error = await async_validation_error(hass, domain, yaml, entry, key)
    if error is not None:
        raise RejectedByHomeAssistant(
            f"Home Assistant rejects this {domain}, so nothing was written: {error}"
        )


async def async_write_and_reload(
    hass: Any,
    target: EditTarget,
    domain: str,
    *,
    entry: Any = None,
    key: str | None = None,
    context: Any = None,
) -> str | None:
    """Validate, round-trip write, reload -- rolling the file back if the reload fails.

    For every path that edits a file the user maintains and reloads it: the
    MCP write tools and the panel's zombie-entity fix. The write is
    :func:`async_write_checked`, and the snapshot it takes is what the rollback
    restores — the same snapshot the panel offers to restore by hand.

    The rollback alone cannot catch an invalid entry: the reload succeeds and
    Home Assistant disables it. That is what the check before the write is for.
    Both reloads run under *context*, so Home Assistant's logbook names who
    asked.

    Returns the backup path, or None when this call created the file.
    """
    backup = await async_write_checked(hass, target, domain, entry=entry, key=key)
    try:
        await hass.services.async_call(
            domain, "reload", blocking=True, context=context
        )
    except Exception as reload_exc:
        name = os.path.basename(target.path)
        if backup is None:
            # The file did not exist before this call, so there is no earlier
            # state to put back. It is left on disk for the user to inspect —
            # deleting it would throw away what they asked to create.
            raise RuntimeError(
                f"Reload failed after creating {name}, which was left in place "
                f"for inspection. Error: {reload_exc}"
            ) from reload_exc

        def _rollback() -> None:
            with open(backup, encoding="utf-8") as fh:
                atomic_write(target.path, fh.read())

        await hass.async_add_executor_job(_rollback)
        try:
            await hass.services.async_call(
                domain, "reload", blocking=True, context=context
            )
        except Exception:
            pass  # Best-effort rollback reload
        raise RuntimeError(
            f"Reload failed after writing {name} — file restored to original. "
            f"Error: {reload_exc}"
        ) from reload_exc
    return backup


# -- Locating an entry, with its file open for editing -----------------------


def open_domain_for_edit(
    config_dir: str, key: str, default_filename: str, shape: type
) -> DomainEdit:
    """Open every file a domain key resolves to, in round-trip mode.

    Files that must not be rewritten land in ``skipped`` rather than raising,
    so one unreadable file never hides the entries in the others -- the caller
    passes that list to :func:`yaml_sources.skipped_note`.
    """
    files = iter_domain_files(config_dir, key, default_filename)
    targets: list[EditTarget] = []
    skipped: list[str] = []
    for path in files:
        try:
            targets.append(read_for_edit(path, shape))
        except UnsafeToEdit as exc:
            _LOGGER.debug("Not editable, skipped: %s", exc)
            skipped.append(path)
    return DomainEdit(targets, files, skipped)


def scan_list_domain_for_edit(
    config_dir: str, key: str, default_filename: str, match: Callable[[Any], bool]
) -> EditScan:
    """Find an entry in a list-shaped domain (automation, scene), for editing."""
    domain = open_domain_for_edit(config_dir, key, default_filename, list)
    for target in domain.targets:
        for index, item in enumerate(target.document):
            if isinstance(item, dict) and match(item):
                return EditScan(target, item, index, None, domain.files, domain.skipped)
    return _MISS._replace(files=domain.files, skipped=domain.skipped)


def scan_named_domain_for_edit(
    config_dir: str,
    key: str,
    default_filename: str,
    match: Callable[[str, Any], bool],
) -> EditScan:
    """Find an entry in a mapping-shaped domain (script), for editing."""
    domain = open_domain_for_edit(config_dir, key, default_filename, dict)
    for target in domain.targets:
        for entry_key, entry in target.document.items():
            if isinstance(entry, dict) and match(entry_key, entry):
                return EditScan(
                    target, entry, -1, entry_key, domain.files, domain.skipped
                )
    return _MISS._replace(files=domain.files, skipped=domain.skipped)


def scan_in_passes(domain: DomainEdit, entries: Callable[[Any], list], passes) -> EditScan:
    """Run several match predicates in priority order across *all* files.

    First-match-wins per file would let an alias that collides in a later file
    beat the exact ``id`` in an earlier one, so each predicate is tried against
    every file before the next predicate is.

    *entries* turns one document into ``(key, index, mapping)`` triples, which
    is the only thing that differs between a list-shaped and a mapping-shaped
    domain.
    """
    for matches in passes:
        for target in domain.targets:
            for entry_key, index, entry in entries(target.document):
                if matches(entry_key, entry):
                    return EditScan(
                        target, entry, index, entry_key,
                        domain.files, domain.skipped,
                    )
    return _MISS._replace(files=domain.files, skipped=domain.skipped)


def list_entries(document) -> list[tuple[None, int, Any]]:
    """``(None, index, mapping)`` for each mapping of a list-shaped document."""
    return [
        (None, index, item)
        for index, item in enumerate(document)
        if isinstance(item, dict)
    ]


def named_entries(document) -> list[tuple[str, int, Any]]:
    """``(key, -1, mapping)`` for each mapping of a mapping-shaped document."""
    return [(k, -1, v) for k, v in document.items() if isinstance(v, dict)]
