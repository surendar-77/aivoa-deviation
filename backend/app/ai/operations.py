"""Validate and apply edit operations ({field, action, value}) to the form.

Why a separate, deterministic step: the LLM only *proposes* operations. This
code decides what is allowed (registry rules), normalises values and records
human overrides - so a bad LLM output can never corrupt the form.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..fields import FIELD_MAP, FIELDS, SCORE_KEYS, TIER_B, FieldValueError, coerce_value
from .wording import label

# Tier-B fields a human may explicitly override; the override then survives AI re-assessment.
OVERRIDABLE = set(SCORE_KEYS) | {"severity_classification", "capa_required", "severity_reasoning",
                                 "impact_assessment", "applicable_sop", "suggested_next_action"}

# Everyday words -> field keys (used for LLM outputs that use labels, and by mock mode).
FIELD_SYNONYMS = {
    "investigator": "assigned_investigator", "assigned investigator": "assigned_investigator",
    "ha notification": "ha_notification_required", "health authority notification": "ha_notification_required",
    "regulatory notification": "ha_notification_required", "ha": "ha_notification_required",
    "customer notification": "customer_notification_required", "customer": "customer_notification_required",
    "batch": "batch_number", "batch no": "batch_number", "lot": "batch_number", "lot number": "batch_number",
    "equipment": "equipment_id", "equipment id": "equipment_id", "reactor": "equipment_id",
    "severity": "severity_classification", "classification": "severity_classification", "sev": "severity_classification",
    "severity class": "severity_classification", "s score": "severity_score", "s": "severity_score",
    "o score": "occurrence_score", "occurrence": "occurrence_score", "o": "occurrence_score",
    "d score": "detectability_score", "detectability": "detectability_score", "d": "detectability_score",
    "product": "product_name", "parameter": "process_parameter", "stage": "manufacturing_stage",
    "spec": "approved_range", "specification": "approved_range", "range": "approved_range",
    "observed": "observed_value", "result": "observed_value", "location": "area_location", "area": "area_location",
    "reporter": "reported_by", "date": "date_detected", "detection date": "date_detected",
    "root cause": "root_cause_hypothesis", "disposition": "batch_disposition", "sop": "applicable_sop",
    "quarantine": "quarantine_reference", "quarantine ref": "quarantine_reference", "capa": "capa_required",
    "type": "deviation_type", "gmp": "gmp_impact", "impact": "impact_assessment",
    "next action": "suggested_next_action", "immediate action": "immediate_action", "containment": "immediate_action", "action": "immediate_action",
    "updated by": "last_updated_by",
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def resolve_field(name: Optional[str]) -> Optional[str]:
    """Map 'Batch No.', 'batch_number', 'the investigator' ... to a registry key (or None)."""
    if not name:
        return None
    n = _norm(str(name).replace("_", " "))
    n = re.sub(r"^(the|a|an)\s+", "", n)
    for f in FIELDS:
        if n in (_norm(f.key.replace("_", " ")), _norm(f.label)):
            return f.key
    if n in FIELD_SYNONYMS:
        return FIELD_SYNONYMS[n]
    # Longest synonym/label contained in the phrase ("the reactor temperature range" -> approved_range).
    candidates = [(_norm(f.label), f.key) for f in FIELDS] + [(k, v) for k, v in FIELD_SYNONYMS.items() if len(k) > 2]
    hits = [(len(label), key) for label, key in candidates if re.search(rf"\b{re.escape(label)}\b", n)]
    return max(hits)[1] if hits else None


# Free-text fields written from the original report. When the user corrects an exact value (batch number,
# equipment ID, ...), the same text in these fields is corrected too, so the record never contradicts itself.
NARRATIVE_KEYS = ("title", "description")
# Only identifier-like facts are propagated. Select fields (status, GMP impact, planned/unplanned) are excluded:
# replacing every "Draft" or "Potential" in the narrative would corrupt it.
PROPAGATE_KEYS = {"batch_number", "equipment_id", "product_name", "observed_value", "approved_range",
                  "process_parameter", "reported_by", "area_location", "date_detected", "manufacturing_stage"}


def _propagate_correction(form: dict, sources: dict, key: str, old, new, instruction: str) -> None:
    if key not in PROPAGATE_KEYS or old in (None, "") or new in (None, "") or old == new:
        return
    old_s, new_s = str(old).strip(), str(new).strip()
    if len(old_s) < 3:  # too short to replace safely ("3" could match anywhere)
        return
    pattern = re.compile(rf"(?<![\w.-]){re.escape(old_s)}(?![\w-])")
    for field in NARRATIVE_KEYS:
        text = form.get(field)
        if isinstance(text, str) and pattern.search(text):
            form[field] = pattern.sub(new_s, text)
            sources[field] = ("User instruction", instruction)


def apply_operations(form: dict, overrides: dict, operations: list[dict], instruction: str
                     ) -> tuple[dict, dict, dict, list[str], list[str]]:
    """Apply validated operations.

    Returns (new_form, new_overrides, sources, applied_messages, rejected_messages).
    sources = {field: (source_label, instruction)} for the change log / audit trail.
    """
    form, overrides = dict(form), dict(overrides)
    sources: dict[str, tuple[str, str]] = {}
    applied, rejected = [], []

    for op in operations or []:
        raw_field = op.get("field")
        key = resolve_field(raw_field)
        action = str(op.get("action") or "set").lower()
        if key is None:
            rejected.append(f"There is no field called '{raw_field}' on this report.")
            continue
        fdef = FIELD_MAP[key]
        if not fdef.chat_editable:
            rejected.append(COMPUTED_HELP.get(fdef.key)
                            or f"The {label(fdef.key)} is filled in automatically, so it can't be changed directly.")
            continue

        if action in ("clear", "remove", "delete", "unset"):
            new_value = None
        else:
            try:
                new_value = coerce_value(key, op.get("value"))
            except FieldValueError as exc:
                rejected.append(str(exc))
                continue
            if new_value is None:
                rejected.append(f"Please give a value for the {label(fdef.key)}, e.g. 'set the {label(fdef.key)} to ...' "
                                f"or 'clear the {label(fdef.key)}'.")
                continue

        old_value = form.get(key)
        form[key] = new_value
        sources[key] = ("User instruction", instruction)
        _propagate_correction(form, sources, key, old_value, new_value, instruction)
        if fdef.tier == TIER_B and key in OVERRIDABLE:
            if new_value is None:
                overrides.pop(key, None)          # clearing an override hands control back to AI/rules
            else:
                reason = re.sub(r"^\s*(because|since|as|due to)\s+", "", str(op.get("reason") or instruction), flags=re.I)
                overrides[key] = {"value": new_value, "reason": reason}
        applied.append(f'updated the {label(fdef.key)} to "{new_value}"' if new_value is not None
                       else f"cleared the {label(fdef.key)}")
    return form, overrides, sources, applied, rejected


# Why calculated fields can't be typed in: said in plain words instead of "not a field".
COMPUTED_HELP = {
    "rpn": "The risk score (RPN) is calculated automatically as severity × likelihood × hard to detect, so it "
           "can't be set directly. If you disagree with the result, you can override the severity level and give a reason.",
    "capa_required": "Whether corrective action (CAPA) is needed is decided by fixed rules from the severity level "
                     "and risk score. You can override it with a reason, e.g. \"CAPA is not needed because …\".",
    "investigation_due_date": "The investigation deadline is set automatically from the severity level "
                              "(Critical 15, Major 30, Minor 45 days), so it can't be set directly.",
    "deviation_magnitude": "How far the value is outside the limit is calculated from the actual value and the "
                           "allowed range. Change one of those instead.",
    "repeat_deviation": "Whether it happened before is looked up automatically in earlier records.",
}
_COMPUTED_WORDS = [
    (re.compile(r"\b(rpn|risk (priority )?(number|score))\b"), "rpn"),
    (re.compile(r"\b(capa|corrective action)\b"), "capa_required"),
    (re.compile(r"\b(due date|deadline)\b"), "investigation_due_date"),
    (re.compile(r"\bmagnitude\b"), "deviation_magnitude"),
]


def computed_field_hint(instruction: str) -> str | None:
    """If an edit names a calculated field ("set rpn to 5"), explain why it can't be typed in."""
    text = instruction.lower()
    for pattern, key in _COMPUTED_WORDS:
        if pattern.search(text):
            return COMPUTED_HELP[key]
    return None


def confirmation(applied: list[str]) -> str:
    """'Got it. I have updated the Batch / Lot Number to "X" and the Observed Value to "Y" in the form.'"""
    if not applied:
        return ""
    # Drop a repeated verb: "updated A and updated B" -> "updated A and B".
    applied = [a.split(" ", 1)[1] if i and a.split(" ", 1)[0] == applied[i - 1].split(" ", 1)[0] else a
               for i, a in enumerate(applied)]
    joined =applied[0] if len(applied) == 1 else ", ".join(applied[:-1]) + " and " + applied[-1]
    return f"Got it. I have {joined} in the form."


def form_summary(form: dict[str, Any], only_filled: bool = True) -> str:
    """Compact 'key: value' listing for prompts."""
    lines = [f"{k}: {v}" for k, v in form.items() if k in FIELD_MAP and (v not in (None, "") or not only_filled)]
    return "\n".join(lines) or "(empty form)"


def editable_fields_spec() -> str:
    lines = []
    for f in FIELDS:
        if not f.chat_editable:
            continue
        s = f"- {f.key} ({f.label}, {f.type})"
        if f.options:
            s += f" options: {f.options}"
        if f.type == "score":
            s += " integer 1-5"
        lines.append(s)
    return "\n".join(lines)
