"""Plain-language wording for Copilot replies (mirrors frontend/src/plainLanguage.js).

The field registry keeps its precise regulatory labels: they drive the AI prompts, field matching and
the audit trail. Only the sentences shown to the reviewer use these everyday words, with the industry
term kept in brackets where a QA specialist would look for it.
"""
from __future__ import annotations

from ..fields import FIELD_MAP

PLAIN_LABELS = {
    "title": "title",
    "date_detected": "date found",
    "reported_by": "reported by",
    "department": "department",
    "area_location": "area / location",
    "site": "site",
    "product_name": "product name",
    "batch_number": "batch number",
    "manufacturing_stage": "production step",
    "equipment_id": "machine / equipment ID",
    "process_parameter": "what was measured",
    "approved_range": "allowed range",
    "observed_value": "actual value",
    "description": "description of what happened",
    "immediate_action": "immediate action taken",
    "root_cause_hypothesis": "likely cause",
    "batch_disposition": "what happens to the batch",
    "deviation_type": "planned or unplanned",
    "category": "category",
    "gmp_impact": "effect on product quality (GMP impact)",
    "root_cause_category": "type of cause",
    "deviation_id": "record number",
    "status": "status",
    "date_reported": "date recorded",
    "assigned_investigator": "investigator",
    "ha_notification_required": "whether to tell the health authority",
    "customer_notification_required": "whether to tell the customer",
    "quarantine_reference": "hold / quarantine number",
    "source_document": "source",
    "last_updated_by": "last changed by",
    "severity_score": "severity score",
    "occurrence_score": "likelihood score",
    "detectability_score": "hard-to-detect score",
    "rpn": "risk score (RPN)",
    "severity_classification": "severity level",
    "severity_reasoning": "reason for the risk level",
    "impact_assessment": "possible impact",
    "suggested_next_action": "suggested next step",
    "capa_required": "corrective action (CAPA)",
    "investigation_due_date": "investigation deadline",
    "deviation_magnitude": "how far outside the limit",
    "repeat_deviation": "whether it happened before",
    "related_deviation_id": "earlier similar record",
    "applicable_sop": "related procedures (SOP)",
}


def label(key: str) -> str:
    """Plain label for a field, e.g. 'observed_value' -> 'actual value'."""
    return PLAIN_LABELS.get(key) or FIELD_MAP[key].label


def labels(keys) -> str:
    """'a, b and c' for a list of field keys."""
    names = [label(k) for k in keys]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def source_phrase(method: str) -> str:
    """How the report reached us, for 'I filled in 18 details from …'."""
    m = (method or "").lower()
    if "ocr" in m:
        return "the scanned document" if "pdf" in m else "the image"
    if "pdf" in m:
        return "the PDF"
    if "email" in m or "eml" in m:
        return "the email"
    if "chat" in m:
        return "your message"
    return "the document"


def risk_line(form: dict, overridden: bool) -> str:
    """'Risk: Major (severity 4 × likelihood 2 × hard to detect 2 = risk score 16).'"""
    text = (f"Risk: {form.get('severity_classification')} (severity {form.get('severity_score')} × likelihood "
            f"{form.get('occurrence_score')} × hard to detect {form.get('detectability_score')} = "
            f"risk score {form.get('rpn')})")
    return text + (", level set by a person" if overridden else "") + "."
