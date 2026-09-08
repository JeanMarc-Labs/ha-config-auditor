"""Tests for duplicate-automation detection — audit 5-3, step 1.

`_check_duplicate_automations` was a Jaccard comparison of every pair of
automations against every other, in a synchronous method sitting in the 358
consecutive lines that the 5-3 loop probe measured as a 12.6 s freeze. It was
replaced by an indexed scan.

The rewrite is only worth anything if it returns *exactly* what the pairwise
scan returned, so the reference implementation is kept here, verbatim, and the
two are compared on randomised configurations. The rest of the file pins the
places where an index can silently lose a pair: the similarity threshold
itself, the size bound, the rare-token prefix, and the float arithmetic behind
both of them.
"""
from __future__ import annotations

import ast
import random
import sys
from fractions import Fraction
from math import ceil
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer

_SOURCE = Path(__file__).parent.parent / "automation_analyzer.py"


# ── Helpers ────────────────────────────────────────────────────────────────────

class _Translator:
    """The wording is not what these tests are about, but the values handed to
    it are: a message naming the wrong count, or a recommendation listing the
    wrong automations, has to fail here rather than in the panel."""

    def t(self, key, **kwargs):
        if not kwargs:
            return key
        return f"{key} " + " ".join(f"{k}={v}" for k, v in sorted(kwargs.items()))


def analyzer(configs: dict, ignored=()) -> AutomationAnalyzer:
    """An analyzer holding these configs and nothing else.

    `_check_duplicate_automations` reads four attributes and no hass at all,
    so building it this way keeps the test about the algorithm.
    """
    a = AutomationAnalyzer.__new__(AutomationAnalyzer)
    a._automation_configs = configs
    a._ignored_entity_ids = set(ignored)
    a._translator = _Translator()
    a.issues = []
    return a


def pairs_of(token_sets: dict[str, frozenset]) -> list[tuple[str, str, float]]:
    """Run the pair finder alone, on token sets written by hand."""
    a = analyzer({})
    return a._probable_duplicate_pairs(list(token_sets), token_sets)


def reference_probable_pairs(
    candidates: list[str], token_sets: dict[str, frozenset]
) -> list[tuple[str, str, float]]:
    """The pairwise scan the rewrite replaced, kept as the oracle.

    Do not optimise this. Its whole value is being the obvious, slow answer.
    """
    found = []
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            a, b = candidates[i], candidates[j]
            set_a = token_sets.get(a, frozenset())
            set_b = token_sets.get(b, frozenset())
            if not set_a or not set_b:
                continue
            union = len(set_a | set_b)
            if union == 0:
                continue
            similarity = len(set_a & set_b) / union
            if similarity >= 0.80:
                found.append((a, b, similarity))
    return found


# ── Random configurations, compared against the pairwise scan ─────────────────

DOMAINS = ["light", "switch", "climate", "cover", "media_player", "fan", "lock"]
PLATFORMS = ["state", "numeric_state", "time", "sun", "template", "device", "event"]
SERVICES = ["light.turn_on", "light.turn_off", "switch.turn_on", "notify.mobile_app",
            "climate.set_temperature", "cover.close_cover", "script.turn_on"]


def random_configs(n: int, seed: int) -> dict:
    """Automations varied enough to produce matches, near-matches and neither."""
    rng = random.Random(seed)
    configs = {}
    for i in range(n):
        domain = rng.choice(DOMAINS)
        config = {
            "id": f"auto_{i}",
            "alias": f"Automation {i}",
            "trigger": [{"platform": rng.choice(PLATFORMS),
                         "entity_id": f"binary_sensor.motion_{i}",
                         "to": rng.choice(["on", "off", "home"])}],
            "condition": ([{"condition": "state", "entity_id": "sun.sun",
                            "state": "below_horizon"}] if rng.random() < 0.6 else []),
            "action": [{"service": rng.choice(SERVICES),
                        "target": {"entity_id": f"{domain}.device_{i}"},
                        "data": {"brightness": rng.randint(1, 255)}}],
            "mode": rng.choice(["single", "restart", "queued"]),
        }
        if rng.random() < 0.4:
            config["action"].append({"delay": {"minutes": rng.randint(1, 10)}})
        if rng.random() < 0.10:
            config["use_blueprint"] = {"path": "someone/thing.yaml", "input": {}}
        if rng.random() < 0.08:                    # nothing to tokenise at all
            config["trigger"], config["condition"], config["action"] = [], [], []
        configs[f"automation.a_{i}"] = config
    return configs


class TestAgainstThePairwiseScan:
    """The rewrite has one contract: be the pairwise scan, faster."""

    @pytest.mark.parametrize("seed", range(25))
    def test_same_pairs_as_comparing_everything_to_everything(self, seed):
        configs = random_configs(random.Random(seed).randint(0, 40), seed)
        a = analyzer(configs)

        token_sets = {}
        for entity_id, config in configs.items():
            if config.get("use_blueprint"):
                continue
            tokens = a._jaccard_tokens(config)
            if tokens:
                token_sets[entity_id] = tokens
        candidates = list(token_sets)

        assert (a._probable_duplicate_pairs(candidates, token_sets)
                == reference_probable_pairs(candidates, token_sets)), (
            "the indexed scan must return the same pairs, in the same order, "
            "with the same similarities as comparing every pair"
        )

    @pytest.mark.parametrize("seed", range(10))
    def test_the_issues_carry_what_the_pairwise_scan_found(self, seed):
        """The pairs are the same; what changed is that they are reported one
        automation at a time. The panel renders the list in order, so the order
        of the automations is part of the output too."""
        configs = random_configs(30, seed)
        ignored = {e for i, e in enumerate(configs) if i % 7 == 0}

        produced = analyzer(configs, ignored)
        produced._check_duplicate_automations()

        oracle = analyzer(configs, ignored)
        token_sets = {}
        for entity_id, config in configs.items():
            if oracle._is_ignored(entity_id) or config.get("use_blueprint"):
                continue
            tokens = oracle._jaccard_tokens(config)
            if tokens:
                token_sets[entity_id] = tokens
        exact_flagged = {
            issue["entity_id"] for issue in produced.issues
            if issue["type"] == "duplicate_automation"
        }
        candidates = [e for e in token_sets if e not in exact_flagged]

        resembles: dict[str, list[str]] = {}
        closest: dict[str, int] = {}
        for a, b, similarity in reference_probable_pairs(candidates, token_sets):
            for one, other in ((a, b), (b, a)):
                resembles.setdefault(one, []).append(other)
                closest[one] = max(closest.get(one, 0), round(similarity * 100))

        expected = [
            (entity_id,
             sorted(resembles[entity_id], key=candidates.index),
             closest[entity_id])
            for entity_id in candidates if entity_id in resembles
        ]
        reported = [
            (issue["entity_id"], issue["duplicate_ids"], issue["similarity_pct"])
            for issue in produced.issues
            if issue["type"] == "probable_duplicate_automation"
        ]
        assert reported == expected


# ── The threshold, and the arithmetic the shortcuts rest on ───────────────────

class TestTheThreshold:

    def test_a_pair_exactly_on_the_threshold_is_reported(self):
        """8 of 10 tokens shared is 0.80 exactly — the boundary the size bound
        and the prefix length are both computed from, and where a float that
        rounds the wrong way loses a real duplicate."""
        common = {f"k:c{i}" for i in range(8)}
        sets = {
            "automation.a": frozenset(common | {"k:a1"}),
            "automation.b": frozenset(common | {"k:b1"}),
        }
        assert pairs_of(sets) == [("automation.a", "automation.b", 0.8)]

    def test_just_below_the_threshold_is_not_reported(self):
        common = {f"k:c{i}" for i in range(8)}
        sets = {
            "automation.a": frozenset(common | {"k:a1", "k:a2"}),
            "automation.b": frozenset(common | {"k:b1", "k:b2"}),
        }
        assert pairs_of(sets) == []

    def test_the_threshold_is_the_one_the_check_advertises(self):
        assert AutomationAnalyzer.SIMILARITY_THRESHOLD == 0.80

    @pytest.mark.parametrize("size", range(1, 120))
    def test_the_prefix_is_exactly_as_long_as_the_arithmetic_asks(self, size):
        """The prefix is the one shortcut that can lose a pair silently, and
        binary floating point is how it would happen: 0.80 × 15 is
        12.000000000000002, so a plain ceil() reads 13 where the arithmetic
        says 12 and the prefix comes out a token short. Comparing against the
        exact rational catches that at every size, instead of hoping a random
        configuration walks into one."""
        exact = size - ceil(Fraction(4, 5) * size) + 1
        assert analyzer({})._prefix_length(size) == exact, (
            f"prefix of {size} rarest tokens is off; a short prefix drops "
            "real duplicates without failing anything else"
        )

    def test_the_exact_ratio_still_matches_the_threshold(self):
        """The test above hard-codes 4/5 as the threshold in exact arithmetic."""
        assert Fraction(4, 5) == Fraction(
            AutomationAnalyzer.SIMILARITY_THRESHOLD
        ).limit_denominator(1000)

    @pytest.mark.parametrize("seed", range(40))
    def test_clusters_of_near_duplicates_match_the_pairwise_scan(self, seed):
        """Token sets built to straddle the threshold, which is where an index
        that prunes one token too eagerly starts losing pairs."""
        rng = random.Random(seed)
        pool = [f"k:t{i}" for i in range(40)]
        sets = {}
        for group in range(12):
            base = set(rng.sample(pool, rng.randint(8, 20)))
            for variant_no in range(rng.randint(1, 3)):
                variant = set(base)
                for _ in range(rng.randint(0, 3)):
                    if variant and rng.random() < 0.5:
                        variant.discard(rng.choice(sorted(variant)))
                    else:
                        variant.add(rng.choice(pool))
                if variant:
                    sets[f"automation.g{group}v{variant_no}"] = frozenset(variant)
        assert pairs_of(sets) == reference_probable_pairs(list(sets), sets)

    def test_sets_of_different_sizes_still_pair_at_the_bound(self):
        """4 tokens of 5 against 4 of 4 is 0.80: the smaller set is exactly
        threshold × the larger, the tightest case the size bound may keep."""
        common = {f"k:c{i}" for i in range(4)}
        sets = {
            "automation.small": frozenset(common),
            "automation.large": frozenset(common | {"k:extra"}),
        }
        assert pairs_of(sets) == [("automation.small", "automation.large", 0.8)]

    def test_a_partner_too_large_to_qualify_is_dropped(self):
        sets = {
            "automation.small": frozenset({"k:a", "k:b"}),
            "automation.large": frozenset({"k:a", "k:b", "k:c", "k:d", "k:e"}),
        }
        assert pairs_of(sets) == []


class TestIdenticalSignatures:

    def test_identical_token_sets_pair_at_a_hundred_percent(self):
        same = frozenset({"k:trigger", "k:service", "platform:sun"})
        sets = {"automation.a": same, "automation.b": same, "automation.c": same}
        assert pairs_of(sets) == [
            ("automation.a", "automation.b", 1.0),
            ("automation.a", "automation.c", 1.0),
            ("automation.b", "automation.c", 1.0),
        ]

    def test_a_group_of_identical_sets_still_matches_a_neighbour(self):
        """Collapsing identical sets must not hide them from a third set that
        is merely similar: every member of the group has to pair with it."""
        common = {f"k:c{i}" for i in range(8)}
        same = frozenset(common | {"k:x"})
        sets = {
            "automation.a": same,
            "automation.b": same,
            "automation.c": frozenset(common | {"k:y"}),
        }
        assert pairs_of(sets) == [
            ("automation.a", "automation.b", 1.0),
            ("automation.a", "automation.c", 0.8),
            ("automation.b", "automation.c", 0.8),
        ]


class TestWhatIsLeftOut:

    def _configs(self):
        shape = {
            "trigger": [{"platform": "sun", "event": "sunset"}],
            "action": [{"service": "light.turn_on"}],
        }
        return {
            "automation.one":     dict(shape, alias="One"),
            "automation.two":     dict(shape, alias="Two"),
            "automation.ignored": dict(shape, alias="Ignored"),
        }

    def _probable(self, a):
        return [i for i in a.issues if i["type"] == "probable_duplicate_automation"]

    @staticmethod
    def _mentions(issues, entity_id):
        return any(issue["entity_id"] == entity_id
                   or entity_id in issue.get("duplicate_ids", [])
                   for issue in issues)

    def test_an_ignored_automation_is_never_paired(self):
        a = analyzer(self._configs(), ignored={"automation.ignored"})
        a._check_duplicate_automations()
        assert not self._mentions(a.issues, "automation.ignored")

    def test_a_blueprint_automation_is_never_paired(self):
        configs = self._configs()
        configs["automation.two"]["use_blueprint"] = {"path": "x/y.yaml"}
        a = analyzer(configs)
        a._check_duplicate_automations()
        assert not self._mentions(a.issues, "automation.two"), (
            "blueprint automations share a structure by design and are excluded"
        )

    def test_an_automation_with_no_tokens_is_never_paired(self):
        configs = {
            "automation.empty_a": {"alias": "A", "trigger": [], "action": []},
            "automation.empty_b": {"alias": "B", "trigger": [], "action": []},
        }
        a = analyzer(configs)
        a._check_duplicate_automations()
        assert self._probable(a) == []

    def test_an_exact_duplicate_is_not_reported_a_second_time_as_probable(self):
        a = analyzer(self._configs())
        a._check_duplicate_automations()
        assert {i["type"] for i in a.issues} == {"duplicate_automation"}, (
            "identical automations are the HIGH finding; reporting them again "
            "as MEDIUM would double every exact duplicate in the panel"
        )

    def test_nothing_at_all_is_reported_for_a_single_automation(self):
        a = analyzer({"automation.only": {
            "trigger": [{"platform": "sun"}], "action": [{"service": "light.turn_on"}]}})
        a._check_duplicate_automations()
        assert a.issues == []


# ── One finding per automation, not one per pair ──────────────────────────────

class TestOneIssuePerAutomation:
    """Similar automations come in groups, and inside a group every member
    matches every other one. Reporting each pair from both ends made that
    quadratic: ten automations alike produced ninety findings that said the
    same thing nine times over, and a hundred produced 9 900. Strategy A never
    did this — it always reported one issue naming the others."""

    def _house(self, rooms):
        """One "motion turns this light on" automation per room: same shape
        everywhere, different entities, so nothing is an *exact* duplicate."""
        return {f"automation.light_{room}": {
            "id": f"l_{room}",
            "alias": f"Light {room}",
            "trigger": [{"platform": "state",
                         "entity_id": f"binary_sensor.motion_{room}", "to": "on"}],
            "action": [{"service": "light.turn_on",
                        "target": {"entity_id": f"light.{room}"}}],
        } for room in rooms}

    def _run(self, rooms):
        a = analyzer(self._house(rooms))
        a._check_duplicate_automations()
        return a.issues

    def test_ten_alike_automations_produce_ten_findings(self):
        issues = self._run([f"room{i}" for i in range(10)])
        assert len(issues) == 10, (
            f"one finding per automation, not one per pair — got {len(issues)}"
        )

    @pytest.mark.parametrize("count", [2, 5, 10, 25])
    def test_the_finding_count_follows_the_automation_count(self, count):
        """The point of the change: linear, not quadratic."""
        assert len(self._run([f"room{i}" for i in range(count)])) == count

    def test_each_finding_names_every_other_automation_once(self):
        issues = self._run([f"room{i}" for i in range(6)])
        for issue in issues:
            assert issue["entity_id"] not in issue["duplicate_ids"]
            assert len(issue["duplicate_ids"]) == 5
            assert len(set(issue["duplicate_ids"])) == 5, "no automation twice"

    def test_the_recommendation_names_at_most_three(self):
        """Same cap strategy A uses; the full list stays in duplicate_ids."""
        first = self._run([f"room{i}" for i in range(8)])[0]
        named = [alias for alias in (f"Light room{i}" for i in range(8))
                 if alias in first["recommendation"]]
        assert len(named) == 3, f"recommendation names {len(named)} automations"
        assert len(first["duplicate_ids"]) == 7, "the full list is not truncated"

    def test_the_message_counts_every_match(self):
        """Seven others, not six and not the pair count."""
        first = self._run([f"room{i}" for i in range(8)])[0]
        assert "count=7" in first["message"], first["message"]

    def test_the_percentage_reported_is_the_closest_match(self):
        """One number has to stand for several partners, and the closest is
        what decides whether the automation is worth opening. Kitchen and hall
        are the same automation on different entities (100%); the porch adds a
        `for:` to its trigger, which is one token out of seven (86%)."""
        configs = self._house(["kitchen", "hall"])
        configs["automation.light_porch"] = {
            "alias": "Light porch",
            "trigger": [{"platform": "state", "entity_id": "binary_sensor.motion_porch",
                         "to": "on", "for": "00:01:00"}],
            "action": [{"service": "light.turn_on",
                        "target": {"entity_id": "light.porch"}}],
        }
        a = analyzer(configs)
        a._check_duplicate_automations()
        reported = {i["entity_id"]: i for i in a.issues}

        assert reported["automation.light_kitchen"]["similarity_pct"] == 100, (
            "the identical one is the closest match, not the average of the two"
        )
        assert reported["automation.light_porch"]["similarity_pct"] == 86
        assert set(reported["automation.light_kitchen"]["duplicate_ids"]) == {
            "automation.light_hall", "automation.light_porch",
        }

    def test_an_automation_matching_nothing_is_not_reported(self):
        configs = self._house(["kitchen"])
        configs["automation.other"] = {
            "alias": "Other",
            "trigger": [{"platform": "time", "at": "07:00:00"}],
            "action": [{"service": "notify.mobile_app"}],
        }
        a = analyzer(configs)
        a._check_duplicate_automations()
        assert a.issues == []

    def test_a_pair_still_reports_both_ends(self):
        """Grouping must not turn a two-automation match into one finding: the
        user has to see it from whichever of the two they are looking at."""
        issues = self._run(["kitchen", "hall"])
        assert [i["entity_id"] for i in issues] == [
            "automation.light_kitchen", "automation.light_hall",
        ]
        assert issues[0]["duplicate_ids"] == ["automation.light_hall"]
        assert issues[1]["duplicate_ids"] == ["automation.light_kitchen"]


# ── The step timings 5-3 step 1 was measured with ─────────────────────────────

def _analyze_all_ast():
    tree = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "analyze_all":
            return node
    raise AssertionError("analyze_all not found in automation_analyzer.py")


class TestTheStepTimings:
    """Which of this analyzer's steps holds the loop is the question 5-3 step 2
    is answered from. A step that slips out of a stage stops being measured
    without anything failing, so the source is checked, not the log."""

    def _stage_labels_around(self, call_name: str) -> list[str]:
        labels = []
        for node in ast.walk(_analyze_all_ast()):
            if not isinstance(node, ast.With):
                continue
            calls = [
                n.func.attr for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            ]
            if call_name not in calls:
                continue
            for item in node.items:
                call = item.context_expr
                if (isinstance(call, ast.Call)
                        and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "stage"
                        and call.args
                        and isinstance(call.args[0], ast.Constant)):
                    labels.append(call.args[0].value)
        return labels

    @pytest.mark.parametrize("method,label", [
        ("_check_duplicate_automations", "duplicates"),
        ("_check_never_triggered", "never triggered"),
        ("_check_blueprint_issues", "blueprints"),
    ])
    def test_each_check_is_timed_under_its_own_name(self, method, label):
        assert label in self._stage_labels_around(method), (
            f"{method}() must run inside timer.stage({label!r}) — without it "
            "its share of the analysis is invisible"
        )

    def test_the_breakdown_is_logged_once(self):
        logged = [
            node for node in ast.walk(_analyze_all_ast())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "log"
        ]
        assert len(logged) == 1, "one analysis, one breakdown line"

    def test_the_breakdown_stays_quiet_on_a_fast_analysis(self):
        assert AutomationAnalyzer.SLOW_ANALYSIS_SECONDS > 0, (
            "a per-step line on INFO at every scan of every installation is "
            "noise; it is there for the analysis that was actually slow"
        )
