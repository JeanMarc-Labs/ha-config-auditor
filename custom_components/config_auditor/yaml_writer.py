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
  order, quoting style and anchors survive the edit;
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
  calls :func:`write_back` on the one file that holds it.

:mod:`yaml_sources` stays the authority on *where* a domain's files are, and
keeps the plain-PyYAML readers the read-only audit paths use. This module is
the write side, and the only one.
"""
from __future__ import annotations

from datetime import datetime
import functools
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

# `<stem>_<YYYYmmdd_HHMMSS>[_<seq>].yaml` -- the name refactoring_assistant has
# always written, and the one its restore path parses back.
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


def roundtrip_yaml():
    """The configured ruamel instance every read and write in HACA shares.

    These settings are what produce a minimal diff: without them a rewritten
    file comes back re-indented from top to bottom and the user's ``git diff``
    is the whole file. Its scalar handling is what keeps a new string a string
    once Home Assistant reads the file back -- see
    :func:`_home_assistant_scalars`.
    """
    from ruamel.yaml import YAML

    yaml = YAML()  # default = round-trip
    yaml.Constructor, yaml.Representer = _home_assistant_scalars()
    yaml.preserve_quotes = True
    # Home Assistant's own 2-space indent, so an edited file still looks
    # hand-written next to the parts we did not touch.
    yaml.indent(mapping=2, sequence=4, offset=2)
    return yaml


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


def create_backup(config_dir: str, source: str) -> str:
    """Snapshot *source* into ``.haca_backups``, then prune that file's old ones.

    Named after the file it copies -- ``automations_<ts>.yaml`` on a flat
    install, ``<name>_<ts>.yaml`` for a file inside a merged folder -- which is
    what lets the panel's restore put it back where it came from.
    """
    src = os.path.abspath(source)
    if not os.path.isfile(src):
        raise FileNotFoundError(f"nothing to back up at {source}")

    backup_dir = os.path.join(config_dir, BACKUP_DIR)
    os.makedirs(backup_dir, exist_ok=True)

    stem = os.path.splitext(os.path.basename(src))[0]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # One-second timestamps collide: two operations in the same second produced
    # the same name and the second silently overwrote the first. A restore
    # takes a pre-restore snapshot, so that collision could destroy the very
    # backup being restored.
    backup = os.path.join(backup_dir, f"{stem}_{timestamp}.yaml")
    sequence = 2
    while os.path.exists(backup):
        backup = os.path.join(backup_dir, f"{stem}_{timestamp}_{sequence}.yaml")
        sequence += 1

    shutil.copy2(src, backup)
    prune_backups(config_dir, stem)
    return backup


def prune_backups(config_dir: str, stem: str | None = None) -> None:
    """Keep the newest :data:`BACKUP_KEEP` backups of each source file."""
    backup_dir = os.path.join(config_dir, BACKUP_DIR)
    try:
        names = os.listdir(backup_dir)
    except OSError:
        return

    by_stem: dict[str, list[str]] = {}
    for name in names:
        owner = backup_stem(name)
        if owner is None or (stem is not None and owner != stem):
            continue
        by_stem.setdefault(owner, []).append(name)

    for group in by_stem.values():
        # The timestamp is fixed-width, so the name sorts by age.
        for old in sorted(group, reverse=True)[BACKUP_KEEP:]:
            try:
                os.unlink(os.path.join(backup_dir, old))
            except OSError as exc:
                _LOGGER.warning("Could not delete old backup %s: %s", old, exc)


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
