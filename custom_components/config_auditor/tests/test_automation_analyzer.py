"""Unit tests for AutomationAnalyzer helper methods.

We test pure/sync methods without requiring a running HA instance.
For async methods we use pytest-asyncio with the MockHass fixture.
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.tests.conftest import MockHass  # noqa


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_analyzer(hass=None):
    """Build an AutomationAnalyzer with mocked translation helper."""
    if hass is None:
        hass = MockHass()

    with patch("custom_components.config_auditor.automation_analyzer.TranslationHelper") as MockTH:
        MockTH.return_value.t = lambda key, **kw: key  # identity translator
        from custom_components.config_auditor.automation_analyzer import AutomationAnalyzer
        return AutomationAnalyzer(hass)


# ── _parse_delay_to_minutes ────────────────────────────────────────────────────

class TestParseDelayToMinutes:
    def setup_method(self):
        self.a = make_analyzer()

    def test_none_returns_none(self):
        assert self.a._parse_delay_to_minutes(None) is None

    def test_integer_seconds(self):
        assert self.a._parse_delay_to_minutes(60) == 1.0
        assert self.a._parse_delay_to_minutes(3600) == 60.0
        assert self.a._parse_delay_to_minutes(90) == 1.5

    def test_float_seconds(self):
        assert self.a._parse_delay_to_minutes(30.0) == 0.5

    def test_hhmmss_string(self):
        assert self.a._parse_delay_to_minutes("00:30:00") == 30.0
        assert self.a._parse_delay_to_minutes("01:00:00") == 60.0
        assert self.a._parse_delay_to_minutes("00:00:30") == 0.5
        assert self.a._parse_delay_to_minutes("02:15:00") == 135.0

    def test_mmss_string(self):
        assert self.a._parse_delay_to_minutes("30:00") == 30.0
        assert self.a._parse_delay_to_minutes("01:30") == 1.5

    def test_invalid_string_returns_none(self):
        assert self.a._parse_delay_to_minutes("not_a_delay") is None
        assert self.a._parse_delay_to_minutes("") is None

    def test_dict_with_minutes(self):
        result = self.a._parse_delay_to_minutes({"minutes": 5})
        assert result == 5

    def test_dict_with_hours(self):
        result = self.a._parse_delay_to_minutes({"hours": 1})
        assert result == 60

    def test_dict_with_seconds(self):
        result = self.a._parse_delay_to_minutes({"seconds": 120})
        assert result == 2.0

    def test_dict_mixed(self):
        result = self.a._parse_delay_to_minutes({"hours": 1, "minutes": 30})
        assert result == 90


# ── _normalize_config ──────────────────────────────────────────────────────────

class TestNormalizeConfig:
    def setup_method(self):
        self.a = make_analyzer()

    def test_empty_input(self):
        assert self.a._normalize_config(None) == ""
        assert self.a._normalize_config([]) == ""

    def test_key_order_irrelevant(self):
        c1 = {"b": 2, "a": 1}
        c2 = {"a": 1, "b": 2}
        assert self.a._normalize_config(c1) == self.a._normalize_config(c2)

    def test_list_order_preserved(self):
        """List order IS significant (action sequence matters)."""
        c1 = [{"service": "light.turn_on"}, {"service": "light.turn_off"}]
        c2 = [{"service": "light.turn_off"}, {"service": "light.turn_on"}]
        assert self.a._normalize_config(c1) != self.a._normalize_config(c2)

    def test_nested_structure(self):
        config = {"choose": [{"conditions": [], "sequence": [{"service": "notify.send"}]}]}
        result = self.a._normalize_config(config)
        assert "notify.send" in result


# ── _exact_fingerprint ─────────────────────────────────────────────────────────

class TestExactFingerprint:
    def setup_method(self):
        self.a = make_analyzer()

    def test_identical_configs_same_hash(self):
        t = [{"platform": "state", "entity_id": "light.x", "to": "on"}]
        act = [{"service": "light.turn_off", "target": {"entity_id": "light.x"}}]
        assert self.a._exact_fingerprint(t, act) == self.a._exact_fingerprint(t, act)

    def test_different_entity_ids_same_logic_same_hash(self):
        """Two automations with same logic but different entity IDs
        should have different exact fingerprints (entity_id IS kept in exact)."""
        # Note: _strip_meta removes id/alias but NOT entity_id
        t1 = [{"platform": "state", "entity_id": "light.room_a", "to": "on"}]
        t2 = [{"platform": "state", "entity_id": "light.room_b", "to": "on"}]
        act = [{"service": "light.turn_off"}]
        # entity_id is structural, so these fingerprints differ
        assert self.a._exact_fingerprint(t1, act) != self.a._exact_fingerprint(t2, act)

    def test_alias_stripped(self):
        """Alias differences should not affect fingerprint."""
        t1 = [{"platform": "state", "entity_id": "light.x", "alias": "v1"}]
        t2 = [{"platform": "state", "entity_id": "light.x", "alias": "v2"}]
        act = []
        assert self.a._exact_fingerprint(t1, act) == self.a._exact_fingerprint(t2, act)


# ── _jaccard_tokens ────────────────────────────────────────────────────────────

class TestJaccardTokens:
    def setup_method(self):
        self.a = make_analyzer()

    def _jaccard(self, a, b):
        sa = self.a._jaccard_tokens(a)
        sb = self.a._jaccard_tokens(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def test_identical_automations_similarity_1(self):
        config = {
            "triggers": [{"platform": "state", "entity_id": "light.x"}],
            "actions": [{"service": "light.turn_on"}],
        }
        assert self._jaccard(config, config) == 1.0

    def test_different_domains_low_similarity(self):
        config_light = {
            "triggers": [{"platform": "state", "entity_id": "light.x"}],
            "actions": [{"service": "light.turn_on"}],
        }
        config_climate = {
            "triggers": [{"platform": "numeric_state", "entity_id": "sensor.temp"}],
            "actions": [{"service": "climate.set_temperature"}],
        }
        sim = self._jaccard(config_light, config_climate)
        assert sim < 0.5

    def test_same_logic_different_entity_ids_high_similarity(self):
        """Same platform + service but different entity IDs → high Jaccard."""
        a = {
            "triggers": [{"platform": "state", "entity_id": "light.room_a", "to": "on"}],
            "actions": [{"service": "light.turn_off", "target": {"entity_id": "light.room_a"}}],
        }
        b = {
            "triggers": [{"platform": "state", "entity_id": "light.room_b", "to": "on"}],
            "actions": [{"service": "light.turn_off", "target": {"entity_id": "light.room_b"}}],
        }
        sim = self._jaccard(a, b)
        assert sim >= 0.80, f"Expected Jaccard >= 0.80, got {sim:.2f}"


# ── _detect_deprecated (AutomationOptimizer) ──────────────────────────────────

class TestDetectDeprecated:
    @pytest.fixture(autouse=True)
    def setup_optimizer(self, tmp_path):
        from custom_components.config_auditor.automation_optimizer import AutomationOptimizer
        (tmp_path / "automations.yaml").write_text("[]")
        hass = MockHass(config_dir=str(tmp_path))
        self.opt = AutomationOptimizer(hass)

    def test_is_state_detected(self):
        yaml_text = "condition: template\nvalue_template: '{{ is_state(\"light.x\", \"on\") }}'"
        patterns = self.opt._detect_deprecated(yaml_text)
        assert any("is_state" in p for p in patterns)

    def test_states_domain_detected(self):
        yaml_text = "value_template: '{{ states.light.salon.state }}'"
        patterns = self.opt._detect_deprecated(yaml_text)
        assert any("states.domain" in p for p in patterns)

    def test_clean_yaml_no_patterns(self):
        yaml_text = """
triggers:
  - platform: state
    entity_id: binary_sensor.motion
actions:
  - service: light.turn_on
"""
        patterns = self.opt._detect_deprecated(yaml_text)
        assert patterns == []

    def test_empty_yaml(self):
        assert self.opt._detect_deprecated("") == []
        assert self.opt._detect_deprecated(None) == []


# ── _get_unavailable_trigger_entities ─────────────────────────────────────────

class TestGetUnavailableTriggerEntities:
    def setup_method(self):
        self.hass = MockHass()
        self.a = make_analyzer(self.hass)

    def test_available_entity_not_returned(self):
        self.hass.add_state("binary_sensor.motion", "on")
        config = {"triggers": [{"platform": "state", "entity_id": "binary_sensor.motion"}]}
        result = self.a._get_unavailable_trigger_entities(config)
        assert "binary_sensor.motion" not in result

    def test_unavailable_entity_returned(self):
        self.hass.add_state("sensor.broken", "unavailable")
        config = {"triggers": [{"platform": "state", "entity_id": "sensor.broken"}]}
        result = self.a._get_unavailable_trigger_entities(config)
        assert "sensor.broken" in result

    def test_unknown_state_returned(self):
        self.hass.add_state("sensor.unknown", "unknown")
        config = {"triggers": [{"platform": "state", "entity_id": "sensor.unknown"}]}
        result = self.a._get_unavailable_trigger_entities(config)
        assert "sensor.unknown" in result

    def test_no_trigger_entities(self):
        config = {"triggers": [{"platform": "time", "at": "08:00:00"}]}
        result = self.a._get_unavailable_trigger_entities(config)
        assert result == set()

    def test_list_entity_ids(self):
        self.hass.add_state("light.a", "unavailable")
        self.hass.add_state("light.b", "on")
        config = {"triggers": [{"platform": "state", "entity_id": ["light.a", "light.b"]}]}
        result = self.a._get_unavailable_trigger_entities(config)
        assert "light.a" in result
        assert "light.b" not in result
