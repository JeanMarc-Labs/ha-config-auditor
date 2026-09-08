"""Both long analyzers must keep reporting where their time goes — audit 5-3.

The scan line names the stages of a scan; these two lines name the steps inside
the two stages that dominate it. Twice now that breakdown is what turned a
"move it to a thread" plan into an afternoon's algorithmic fix — the duplicate
scan, then the blueprint re-parse — so a step that quietly falls out of its
timer is a real loss, and one that nothing else would fail over.

The guards read the source rather than the log: a step outside a stage still
runs, still produces its findings, and only stops being measured.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

_PACKAGE = Path(__file__).parent.parent

# Each analyzer, and the steps whose cost has to stay visible by name.
_ANALYZERS = {
    "automation_analyzer.py": [
        ("_check_duplicate_automations", "duplicates"),
        ("_check_never_triggered", "never triggered"),
        ("_check_blueprint_issues", "blueprints"),
        ("_load_automation_configs", "read config"),
    ],
    "entity_analyzer.py": [
        ("_build_entity_references", "references"),
        ("_analyze_entity_states", "states"),
        ("_analyze_input_helpers", "input helpers"),
        ("_analyze_zombie_entities", "zombies"),
    ],
}


def _analyze_all(source_name: str) -> ast.AsyncFunctionDef:
    tree = ast.parse((_PACKAGE / source_name).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "analyze_all":
            return node
    raise AssertionError(f"no analyze_all in {source_name}")


def _stage_label(item: ast.withitem) -> str | None:
    call = item.context_expr
    if (isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr == "stage"
            and call.args
            and isinstance(call.args[0], ast.Constant)):
        return call.args[0].value
    return None


def _stages_around(analyze_all: ast.AsyncFunctionDef, called: str) -> list[str]:
    """Every stage label whose `with` block contains a call to `called`."""
    labels = []
    for node in ast.walk(analyze_all):
        if not isinstance(node, ast.With):
            continue
        names = {
            n.func.attr for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        if called not in names:
            continue
        labels += [label for label in map(_stage_label, node.items) if label]
    return labels


_CASES = [
    (source, method, label)
    for source, steps in _ANALYZERS.items()
    for method, label in steps
]


@pytest.mark.parametrize("source,method,label", _CASES,
                         ids=[f"{s.split('_')[0]}-{m}" for s, m, _ in _CASES])
def test_each_step_is_timed_under_its_own_name(source, method, label):
    assert label in _stages_around(_analyze_all(source), method), (
        f"{source}: {method}() must run inside steps.stage({label!r}) — "
        "outside one, its share of the analysis is invisible"
    )


@pytest.mark.parametrize("source", sorted(_ANALYZERS))
def test_no_await_escapes_a_stage(source):
    """The strong form of the guard above: a step added later cannot hide.

    Anything awaited outside a stage still counts towards the total, so its
    cost shows up as the unnamed remainder and the next person reading the
    line looks in the wrong place.
    """
    analyze_all = _analyze_all(source)

    timed: set[int] = set()
    for node in ast.walk(analyze_all):
        if isinstance(node, ast.With) and any(map(_stage_label, node.items)):
            timed.update(id(inner) for inner in ast.walk(node))

    escaped = [
        node.lineno for node in ast.walk(analyze_all)
        if isinstance(node, ast.Await) and id(node) not in timed
    ]
    assert not escaped, (
        f"{source}: await outside any timer stage at line(s) {escaped}"
    )


@pytest.mark.parametrize("source", sorted(_ANALYZERS))
def test_the_breakdown_is_logged_exactly_once(source):
    logged = [
        node for node in ast.walk(_analyze_all(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "log"
    ]
    assert len(logged) == 1, f"{source}: one analysis, one breakdown line"


@pytest.mark.parametrize("source", sorted(_ANALYZERS))
def test_the_breakdown_stays_quiet_on_a_fast_analysis(source):
    """A per-step line on INFO at every scan of every installation is noise;
    it is there for the analysis that was actually slow enough to be felt."""
    text = (_PACKAGE / source).read_text(encoding="utf-8")
    assert "quiet_below=self.SLOW_ANALYSIS_SECONDS" in text
    assert "SLOW_ANALYSIS_SECONDS = " in text
