"""Deterministic Tier-B rules: RPN, classification, CAPA, due date, magnitude."""
import pytest

from app.rules import (apply_rules, capa_required, classify_severity, compute_rpn,
                       deviation_magnitude, investigation_due_date, parse_spec)


def test_rpn_requires_all_three_scores():
    assert compute_rpn(4, 3, 2) == 24
    assert compute_rpn(4, None, 2) is None


@pytest.mark.parametrize("s,rpn,expected", [
    (5, 5, "Critical"),     # S=5 alone escalates
    (2, 100, "Critical"),   # RPN threshold
    (3, 9, "Major"),
    (2, 40, "Major"),
    (2, 39, "Minor"),
    (1, 1, "Minor"),
])
def test_classification_thresholds(s, rpn, expected):
    assert classify_severity(s, rpn) == expected


def test_classification_none_without_scores():
    assert classify_severity(None, None) is None


def test_capa_rule():
    assert capa_required("Major", 10) == "Yes"
    assert capa_required("Minor", 60) == "Yes"
    assert capa_required("Minor", 59) == "No"


@pytest.mark.parametrize("cls,expected", [
    ("Critical", "2026-09-29"), ("Major", "2026-10-14"), ("Minor", "2026-10-29")])
def test_due_date(cls, expected):
    assert investigation_due_date("2026-09-14", cls) == expected


def test_due_date_missing_inputs():
    assert investigation_due_date(None, "Major") is None
    assert investigation_due_date("2026-09-14", None) is None


@pytest.mark.parametrize("spec,observed,expected", [
    ("60-65 °C", "71 °C", "+6 °C above upper limit 65 °C (9.2% over)"),
    ("60 to 65°C", "58°C", "-2 °C below lower limit 60 °C (3.3% under)"),
    ("60 – 65 °C", "62 °C", "Within approved range (60–65 °C)"),
    ("NMT 0.5%", "1.2%", "+0.7% above upper limit 0.5% (140.0% over)"),
    ("NMT 0.5% w/w", "1.2% w/w", "+0.7% w/w above upper limit 0.5% w/w (140.0% over)"),
    ("NLT 98%", "96.5%", "-1.5% below lower limit 98% (1.5% under)"),
    ("2.0 ± 0.2", "2.5", "+0.3 above upper limit 2.2 (13.6% over)"),
    ("2.0 +/- 0.2 bar", "1.7 bar", "-0.1 bar below lower limit 1.8 bar (5.6% under)"),
    ("900-1100 rpm", "750 rpm for 40 min", "-150 rpm below lower limit 900 rpm (16.7% under)"),
])
def test_magnitude(spec, observed, expected):
    assert deviation_magnitude(spec, observed) == expected


def test_magnitude_unparseable_returns_none():
    assert deviation_magnitude("as per BMR", "high") is None
    assert deviation_magnitude(None, "71 °C") is None
    assert parse_spec("complies") is None


def test_apply_rules_full_chain():
    form = {"severity_score": 4, "occurrence_score": 3, "detectability_score": 3,
            "date_detected": "2026-09-14", "approved_range": "60-65 °C", "observed_value": "71 °C",
            "equipment_id": "R-201"}
    out = apply_rules(form, {}, find_related=lambda f: "DEV-2026-0003")
    assert out["rpn"] == 36
    assert out["severity_classification"] == "Major"      # S=4 >= 3
    assert out["capa_required"] == "Yes"
    assert out["investigation_due_date"] == "2026-10-14"
    assert out["deviation_magnitude"].startswith("+6 °C above")
    assert out["repeat_deviation"] == "Yes" and out["related_deviation_id"] == "DEV-2026-0003"


def test_user_override_wins_over_rule():
    form = {"severity_score": 2, "occurrence_score": 2, "detectability_score": 2, "date_detected": "2026-09-14"}
    out = apply_rules(form, {"severity_classification": {"value": "Major", "reason": "quarantined"}})
    assert out["severity_classification"] == "Major"      # rule alone would say Minor
    assert out["capa_required"] == "Yes"                  # follows the overridden class
    assert out["investigation_due_date"] == "2026-10-14"


def test_apply_rules_does_not_mutate_input():
    form = {"severity_score": 5}
    apply_rules(form)
    assert "rpn" not in form
