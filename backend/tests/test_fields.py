"""Registry integrity and value coercion/normalisation."""
import pytest

from app.fields import (FIELDS, FIELD_MAP, RISK_SECTION, FieldValueError, SECTIONS, coerce_form, coerce_value,
                        empty_form, missing_fields, parse_date, registry_payload)


def test_registry_is_consistent():
    keys = [f.key for f in FIELDS]
    assert len(keys) == len(set(keys)), "duplicate field keys"
    for f in FIELDS:
        assert f.tier in "ABC" and f.section in SECTIONS + [RISK_SECTION]
        if f.type == "select":
            assert f.options, f"{f.key} has no options"


def test_tier_assignment_matches_design():
    assert FIELD_MAP["batch_number"].tier == "A"
    assert FIELD_MAP["rpn"].tier == "B" and not FIELD_MAP["rpn"].chat_editable
    assert FIELD_MAP["assigned_investigator"].tier == "C"
    assert not FIELD_MAP["deviation_id"].chat_editable


def test_payload_and_empty_form():
    payload = registry_payload()
    assert len(payload["fields"]) == len(FIELDS)
    assert payload["fields"][0]["tier_label"] in {"AI-extracted", "AI-computed", "Human/System"}
    assert set(empty_form()) == set(FIELD_MAP)


@pytest.mark.parametrize("raw", ["2026-09-14", "14/09/2026", "14-Sep-2026", "14 September 2026",
                                 "September 14, 2026", "14th September 2026", "2026-09-14T02:15:00",
                                 "14.09.2026", "Monday, 14 September 2026 09:42"])
def test_dates_normalise_to_iso(raw):
    assert parse_date(raw) == "2026-09-14"


def test_bad_date_raises():
    with pytest.raises(FieldValueError):
        coerce_value("date_detected", "next tuesday-ish")


@pytest.mark.parametrize("key,raw,expected", [
    ("gmp_impact", "potential", "Potential"),
    ("gmp_impact", "possible", "Potential"),
    ("deviation_type", "unplanned", "Unplanned"),
    ("status", "open", "Open"),
    ("status", "under investigation", "Under Investigation"),
    ("ha_notification_required", "to be evaluated", "To be evaluated"),
    ("ha_notification_required", "TBD", "To be evaluated"),
    ("batch_disposition", "quarantined", "Quarantined / On Hold"),
    ("manufacturing_stage", "crystallisation", "Crystallization"),
    ("manufacturing_stage", "Filtration / Centrifugation", "Filtration / Centrifugation"),
    ("severity_classification", "major", "Major"),
    ("capa_required", True, "Yes"),
    ("capa_required", "not required", "No"),
])
def test_select_normalisation(key, raw, expected):
    assert coerce_value(key, raw) == expected


def test_invalid_select_lists_allowed_options():
    with pytest.raises(FieldValueError, match="Allowed: Draft, Open"):
        coerce_value("status", "banana")


@pytest.mark.parametrize("raw,expected", [(4, 4), ("3", 3), ("5/5", 5), (2.0, 2)])
def test_scores(raw, expected):
    assert coerce_value("severity_score", raw) == expected


@pytest.mark.parametrize("raw", [0, 6, "high"])
def test_bad_scores(raw):
    with pytest.raises(FieldValueError):
        coerce_value("occurrence_score", raw)


def test_nullish_and_unknown():
    assert coerce_value("equipment_id", "  ") is None
    assert coerce_value("equipment_id", "N/A") is None
    assert coerce_value("equipment_id", " R-201 ") == "R-201"
    with pytest.raises(FieldValueError, match="Unknown field"):
        coerce_value("colour", "red")


def test_coerce_form_is_lenient():
    out, warnings = coerce_form({"date_detected": "garbage", "batch_number": "B-1", "bogus": 1})
    assert out == {"date_detected": None, "batch_number": "B-1"}
    assert len(warnings) == 1


def test_missing_fields_only_tier_a():
    form = empty_form()
    form["title"] = "x"
    missing = missing_fields(form)
    assert "title" not in missing and "batch_number" in missing
    assert "rpn" not in missing and "assigned_investigator" not in missing


def test_llm_typography_is_normalised():
    """U+2011 / U+202F from the LLM must not break IDs or the range parser."""
    from app.fields import coerce_value
    from app.rules import deviation_magnitude
    rng = coerce_value("approved_range", "60\u201165\u202f°C")
    assert rng == "60-65 °C"
    assert coerce_value("batch_number", "MS\u20112609\u2011017") == "MS-2609-017"
    assert deviation_magnitude(rng, coerce_value("observed_value", "71\u202f°C")).startswith("+6 °C above")
