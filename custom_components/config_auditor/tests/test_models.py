"""Tests for models.py — AuditIssue, ComplexityScore, BatteryEntry."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from custom_components.config_auditor.models import (
    AuditIssue, ComplexityScore, BatteryEntry,
)


class TestAuditIssue:
    def test_minimal_construction(self):
        issue = AuditIssue(
            entity_id="automation.test",
            type="no_alias",
            severity="low",
            message="Missing alias",
            recommendation="Add an alias",
        )
        assert issue.entity_id == "automation.test"
        assert issue.fix_available is False  # default
        assert issue.location == ""          # default

    def test_to_dict_minimal(self):
        issue = AuditIssue("automation.x", "t", "high", "msg", "rec")
        d = issue.to_dict()
        assert d["entity_id"] == "automation.x"
        assert d["severity"] == "high"
        assert "location" not in d  # empty strings are omitted

    def test_to_dict_with_location(self):
        issue = AuditIssue("automation.x", "t", "medium", "m", "r", location="trigger[0]")
        d = issue.to_dict()
        assert d["location"] == "trigger[0]"

    def test_to_dict_with_extra(self):
        issue = AuditIssue(
            "automation.x", "duplicate", "medium", "m", "r",
            extra={"duplicate_ids": ["automation.y"], "similarity_pct": 87},
        )
        d = issue.to_dict()
        assert d["duplicate_ids"] == ["automation.y"]
        assert d["similarity_pct"] == 87

    def test_from_dict_roundtrip(self):
        original = {
            "entity_id": "automation.x",
            "type": "ghost_automation",
            "severity": "high",
            "message": "Ghost",
            "recommendation": "Check triggers",
            "fix_available": False,
            "last_triggered_days_ago": 120,
        }
        issue = AuditIssue.from_dict(original)
        assert issue.entity_id == "automation.x"
        assert issue.extra["last_triggered_days_ago"] == 120

        # Roundtrip through to_dict
        d = issue.to_dict()
        assert d["last_triggered_days_ago"] == 120

    def test_from_dict_missing_fields(self):
        """from_dict should handle missing keys gracefully."""
        issue = AuditIssue.from_dict({"entity_id": "automation.x"})
        assert issue.severity == "low"
        assert issue.type == "unknown"
        assert issue.message == ""


class TestComplexityScore:
    def test_to_dict(self):
        row = ComplexityScore(
            entity_id="automation.complex",
            alias="My Complex Automation",
            score=45,
            triggers=3,
            conditions=5,
            actions=20,
            templates=8,
        )
        d = row.to_dict()
        assert d["score"] == 45
        assert d["actions"] == 20

    def test_default_zeros(self):
        row = ComplexityScore("automation.x", "X", 10)
        assert row.triggers == 0
        assert row.templates == 0


class TestBatteryEntry:
    def test_to_dict_ok_battery(self):
        b = BatteryEntry(
            entity_id="sensor.phone_battery",
            friendly_name="Phone",
            level=85.0,
        )
        d = b.to_dict()
        assert d["level"] == 85.0
        assert d["severity"] is None

    def test_to_dict_critical_battery(self):
        b = BatteryEntry("sensor.x", "X", 3.0, severity="high")
        d = b.to_dict()
        assert d["severity"] == "high"

    def test_default_unit(self):
        b = BatteryEntry("sensor.x", "X", 50.0)
        assert b.unit == "%"
