"""Field registry: the SINGLE source of truth for every Log Deviation field.

Why: the form layout (frontend), DB columns (models.py), LLM extraction
prompt, edit validation and value normalisation are all generated from this
one list. Adding a field here adds it everywhere, so nothing drifts.

Three tiers (the core anti-hallucination design):
  A  "AI-extracted"  - facts the LLM may copy from the source document ONLY.
  B  "AI-computed"   - scores/judgements from the risk node or deterministic
                       Python rules. Never "read" from the document.
  C  "Human/System"  - accountability fields (IDs, investigator, notifications,
                       status). The AI must never invent them; only the system
                       or an explicit user instruction may set them.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

TIER_A, TIER_B, TIER_C = "A", "B", "C"
TIER_LABELS = {TIER_A: "AI-extracted", TIER_B: "AI-computed", TIER_C: "Human/System"}

# Numbered form sections (UI order). "Risk Assessment" is not a grid section: the
# frontend renders those fields inside the "AI copilot risk assessment" card.
SECTIONS = [
    "1. Event Details",
    "2. Product & Process",
    "3. Description & Actions",
    "4. Classification",
    "5. Administration",
]
RISK_SECTION = "Risk Assessment"

YES_NO = ["Yes", "No"]
YES_NO_TBE = ["Yes", "No", "To be evaluated"]
STATUS_OPTIONS = ["Draft", "Open", "Under Investigation", "Pending QA Approval", "Closed"]
SEVERITY_OPTIONS = ["Critical", "Major", "Minor"]


@dataclass
class FieldDef:
    key: str
    label: str
    tier: str
    section: str
    type: str = "text"  # text | textarea | date | select | score
    options: list[str] = field(default_factory=list)
    # Can a chat instruction set/clear this field? (False = system or rule only)
    chat_editable: bool = True
    # Changing this field changes the risk picture -> re-run assess_risk.
    risk_driving: bool = False
    # Short hint shown to the LLM and in the UI.
    help: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier_label"] = TIER_LABELS[self.tier]
        return d


EVENT, PROCESS, DESCRIPTION, CLASSIFICATION, ADMIN = SECTIONS
RISK = RISK_SECTION

FIELDS: list[FieldDef] = [
    # ---------------- 1. Event Details ----------------
    FieldDef("title", "Deviation Title", TIER_A, EVENT, "textarea", help="One-line summary of the event."),
    FieldDef("date_detected", "Date Detected", TIER_A, EVENT, "date"),
    FieldDef("reported_by", "Reported By", TIER_A, EVENT),
    FieldDef("department", "Department", TIER_A, EVENT),
    FieldDef("area_location", "Area / Location", TIER_A, EVENT),
    FieldDef("site", "Site", TIER_C, EVENT, help="Defaults from server config."),
    # ---------------- 2. Product & Process ----------------
    FieldDef("product_name", "Product Name", TIER_A, PROCESS),
    FieldDef("batch_number", "Batch / Lot Number", TIER_A, PROCESS),
    FieldDef("manufacturing_stage", "Manufacturing Stage", TIER_A, PROCESS, "select",
             ["Raw Material Dispensing", "Reaction", "Crystallization", "Filtration / Centrifugation",
              "Drying", "Milling / Sieving", "Blending", "Packaging", "Other"], risk_driving=True),
    FieldDef("equipment_id", "Equipment ID", TIER_A, PROCESS),
    FieldDef("process_parameter", "Process Parameter", TIER_A, PROCESS, risk_driving=True),
    FieldDef("approved_range", "Approved Range", TIER_A, PROCESS, risk_driving=True,
             help="e.g. 60-65 °C, NMT 0.5%, NLT 98%, 2.0 ± 0.2"),
    FieldDef("observed_value", "Observed Value", TIER_A, PROCESS, risk_driving=True),
    # ---------------- 3. Description & Actions ----------------
    FieldDef("description", "Deviation Description", TIER_A, DESCRIPTION, "textarea", risk_driving=True,
             help="Clean QMS narrative: what, where, when, how detected."),
    FieldDef("immediate_action", "Immediate Action / Containment", TIER_A, DESCRIPTION, "textarea"),
    FieldDef("root_cause_hypothesis", "Root Cause Hypothesis", TIER_A, DESCRIPTION, "textarea",
             help="Only if the source states a suspected cause."),
    FieldDef("batch_disposition", "Batch Disposition", TIER_A, DESCRIPTION, "select",
             ["Quarantined / On Hold", "Under Evaluation", "Released", "Reprocess / Rework", "Rejected"]),
    # ---------------- 4. Classification ----------------
    FieldDef("deviation_type", "Deviation Type", TIER_A, CLASSIFICATION, "select", ["Planned", "Unplanned"]),
    FieldDef("category", "Category", TIER_A, CLASSIFICATION, "select",
             ["Process Parameter Excursion", "Equipment Malfunction", "Material / Specification (OOS)",
              "Documentation", "Environmental Monitoring", "Utility Failure", "Cleaning", "Other"],
             risk_driving=True),
    FieldDef("gmp_impact", "GMP Impact", TIER_A, CLASSIFICATION, "select",
             ["Yes", "No", "Potential"], risk_driving=True),
    FieldDef("root_cause_category", "Root Cause Category", TIER_A, CLASSIFICATION, "select",
             ["Equipment", "Process", "Material", "Human Error", "Method / Procedure",
              "Environment", "Utility", "Under Investigation"]),
    # ---------------- 5. Administration (Human/System only) ----------------
    FieldDef("deviation_id", "Deviation ID", TIER_C, ADMIN, chat_editable=False,
             help="Auto-generated on save (DEV-YYYY-NNNN)."),
    FieldDef("status", "Status", TIER_C, ADMIN, "select", STATUS_OPTIONS),
    FieldDef("date_reported", "Date Reported", TIER_C, ADMIN, "date", chat_editable=False,
             help="System date when the deviation was logged."),
    FieldDef("assigned_investigator", "Assigned Investigator", TIER_C, ADMIN),
    FieldDef("ha_notification_required", "HA Notification Required", TIER_C, ADMIN, "select", YES_NO_TBE),
    FieldDef("customer_notification_required", "Customer Notification Required", TIER_C, ADMIN,
             "select", YES_NO_TBE),
    FieldDef("quarantine_reference", "Quarantine Reference", TIER_C, ADMIN),
    FieldDef("source_document", "Source Document", TIER_C, ADMIN, chat_editable=False),
    FieldDef("last_updated_by", "Last Updated By", TIER_C, ADMIN),
    # ---------------- Risk Assessment (Tier B, shown in the risk card) ----------------
    FieldDef("severity_score", "Severity (S)", TIER_B, RISK, "score"),
    FieldDef("occurrence_score", "Occurrence (O)", TIER_B, RISK, "score"),
    FieldDef("detectability_score", "Detectability (D)", TIER_B, RISK, "score"),
    FieldDef("rpn", "RPN (S×O×D)", TIER_B, RISK, chat_editable=False),
    FieldDef("severity_classification", "Severity (Suggested)", TIER_B, RISK, "select", SEVERITY_OPTIONS,
             help="Rule-derived from S and RPN unless explicitly overridden by the user."),
    FieldDef("severity_reasoning", "Initial Risk Assessment", TIER_B, RISK, "textarea"),
    FieldDef("impact_assessment", "Impact Assessment", TIER_B, RISK, "textarea"),
    FieldDef("suggested_next_action", "Suggested Next Action", TIER_B, RISK,
             help="e.g. Quarantine batch and route to QA investigation."),
    FieldDef("capa_required", "CAPA Required", TIER_B, RISK, "select", YES_NO),
    FieldDef("investigation_due_date", "Investigation Due Date", TIER_B, RISK, "date",
             chat_editable=False, help="Rule: date detected + 15/30/45 days (Critical/Major/Minor)."),
    FieldDef("deviation_magnitude", "Deviation Magnitude", TIER_B, RISK,
             chat_editable=False, help="Rule: observed value vs approved range."),
    FieldDef("repeat_deviation", "Repeat Deviation", TIER_B, RISK, "select", YES_NO,
             chat_editable=False, help="Rule: DB lookup of prior deviations."),
    FieldDef("related_deviation_id", "Related Deviation ID", TIER_B, RISK, chat_editable=False),
    FieldDef("applicable_sop", "Applicable SOP (verify)", TIER_B, RISK,
             help="AI suggestion only - must be verified by QA."),
]

FIELD_MAP: dict[str, FieldDef] = {f.key: f for f in FIELDS}
FIELD_KEYS = [f.key for f in FIELDS]
TIER_A_KEYS = [f.key for f in FIELDS if f.tier == TIER_A]
RISK_DRIVING_KEYS = {f.key for f in FIELDS if f.risk_driving}
SCORE_KEYS = ["severity_score", "occurrence_score", "detectability_score"]


def empty_form() -> dict[str, Any]:
    """A blank form: every registry key present, all values None."""
    return {k: None for k in FIELD_KEYS}


def registry_payload() -> dict:
    """What GET /api/fields returns - the frontend renders the form from this."""
    return {
        "sections": SECTIONS,
        "risk_section": RISK_SECTION,
        "tiers": TIER_LABELS,
        "fields": [f.to_dict() for f in FIELDS],
    }


# ---------------------------------------------------------------------------
# Value coercion / normalisation
# ---------------------------------------------------------------------------
class FieldValueError(ValueError):
    """Raised when a value cannot be normalised for a field (message is user-facing)."""


_DATE_FORMATS = [
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y",
    "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%d-%B-%Y", "%b %d %Y", "%B %d %Y",
    "%Y/%m/%d",
]


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _relative_date(text: str) -> Optional[date]:
    """'today', 'yesterday', 'day before yesterday', '3 days ago', 'last night', 'last Monday'."""
    t = text.lower().strip(" .")
    today = date.today()
    if t in ("today", "this morning", "tonight", "now"):
        return today
    if t in ("yesterday", "last night", "yesterday night", "yesterday morning"):
        return today - timedelta(days=1)
    if t == "day before yesterday":
        return today - timedelta(days=2)
    m = re.fullmatch(r"(\d{1,3}|a|one|two|three|four|five|six|seven) (day|days|week|weeks) ago", t)
    if m:
        n = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}.get(m.group(1))
        n = n or int(m.group(1))
        return today - timedelta(days=n * (7 if m.group(2).startswith("week") else 1))
    m = re.fullmatch(r"(?:last|on) (" + "|".join(_WEEKDAYS) + ")", t)
    if m:
        back = (today.weekday() - _WEEKDAYS.index(m.group(1))) % 7 or 7
        return today - timedelta(days=back)
    return None


def parse_date(value: Any) -> str:
    """Normalise many common date spellings to ISO YYYY-MM-DD.

    Why DD/MM first: Indian/EU pharma sites write day-first; ISO is always tried first.
    """
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    relative = _relative_date(text)
    if relative:
        return relative.isoformat()
    text = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", text)  # 12th -> 12
    text = re.sub(r"^[A-Za-z]{3,9},\s*", "", text)       # drop weekday "Monday, "
    text = " ".join(text.replace(",", " ").split())  # "Sep 14, 2026" -> "Sep 14 2026"
    # Take only the date part of a timestamp such as "2026-03-12 14:30" or ISO "T".
    candidates = [text, text.split("T")[0], " ".join(text.split()[:3]), text.split()[0] if text else ""]
    for cand in candidates:
        cand = cand.strip()
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(cand, fmt).date().isoformat()
            except ValueError:
                continue
    raise FieldValueError(f"'{value}' is not a recognisable date (use YYYY-MM-DD).")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


# Synonyms that map free text to a registry option (applied after exact/fuzzy match fails).
_SELECT_SYNONYMS = {
    "gmp_impact": {"possible": "Potential", "maybe": "Potential", "true": "Yes", "false": "No"},
    "batch_disposition": {"quarantine": "Quarantined / On Hold", "quarantined": "Quarantined / On Hold",
                          "hold": "Quarantined / On Hold", "onhold": "Quarantined / On Hold",
                          "rework": "Reprocess / Rework", "reprocess": "Reprocess / Rework",
                          "reject": "Rejected", "release": "Released"},
    "ha_notification_required": {"tbe": "To be evaluated", "tbd": "To be evaluated",
                                 "evaluate": "To be evaluated", "pending": "To be evaluated"},
    "customer_notification_required": {"tbe": "To be evaluated", "tbd": "To be evaluated",
                                       "evaluate": "To be evaluated", "pending": "To be evaluated"},
    "root_cause_category": {"unknown": "Under Investigation", "tbd": "Under Investigation",
                            "human": "Human Error", "procedure": "Method / Procedure",
                            "method": "Method / Procedure", "machine": "Equipment"},
    "manufacturing_stage": {"crystallisation": "Crystallization", "filtration": "Filtration / Centrifugation",
                            "centrifugation": "Filtration / Centrifugation", "milling": "Milling / Sieving",
                            "sieving": "Milling / Sieving", "dispensing": "Raw Material Dispensing",
                            "synthesis": "Reaction", "dryer": "Drying"},
    "category": {"processdeviation": "Process Parameter Excursion", "process": "Process Parameter Excursion",
                 "equipment": "Equipment Malfunction", "oos": "Material / Specification (OOS)",
                 "material": "Material / Specification (OOS)", "utility": "Utility Failure"},
    "status": {"investigation": "Under Investigation", "pendingqa": "Pending QA Approval",
               "qaapproval": "Pending QA Approval", "close": "Closed", "new": "Draft"},
}


def match_option(key: str, value: Any) -> str:
    """Map free text to one of the field's options (case/punctuation-insensitive)."""
    fdef = FIELD_MAP[key]
    raw = str(value).strip()
    n = _norm(raw)
    if isinstance(value, bool):
        n = "yes" if value else "no"
    for opt in fdef.options:                      # 1. exact (normalised)
        if _norm(opt) == n:
            return opt
    synonyms = _SELECT_SYNONYMS.get(key, {})      # 2. known synonyms
    if n in synonyms:
        return synonyms[n]
    for word, opt in synonyms.items():
        if word in n:
            return opt
    for opt in fdef.options:                      # 3. prefix / containment
        no = _norm(opt)
        if n and (no.startswith(n) or n.startswith(no) or no in n):
            return opt
    if fdef.options == YES_NO and n in {"y", "true", "required"}:
        return "Yes"
    if fdef.options == YES_NO and n in {"n", "false", "notrequired", "none"}:
        return "No"
    raise FieldValueError(
        f"'{raw}' is not a valid option for {fdef.label}. Allowed: {', '.join(fdef.options)}."
    )


# LLMs and OCR emit typographic look-alikes (non-breaking hyphen U+2011, narrow no-break space U+202F,
# minus sign U+2212). They look identical on screen but break exact matching of batch numbers /
# equipment IDs and the range parser in rules.py, so every value is normalised to plain ASCII forms.
_TYPOGRAPHY = str.maketrans({
    "‐": "-", "‑": "-", "‒": "-", "−": "-",
    " ": " ", " ": " ", " ": " ", " ": " ", "​": "",
})


def coerce_value(key: str, value: Any) -> Any:
    """Validate + normalise a value for a registry field. None/"" -> None (cleared).

    Raises FieldValueError (user-facing message) for unknown fields or bad values.
    """
    if key not in FIELD_MAP:
        raise FieldValueError(f"Unknown field '{key}'.")
    if value is None:
        return None
    fdef = FIELD_MAP[key]
    if isinstance(value, str):
        value = value.translate(_TYPOGRAPHY).strip()
        if value == "":
            return None
        # LLMs often write "null"/"N/A" instead of JSON null. ("none" is kept for
        # selects because it can legitimately mean "No".)
        if fdef.type != "select" and value.lower() in {"null", "none", "n/a", "na", "not stated", "unknown"}:
            return None
        if fdef.type == "select" and value.lower() in {"null", "n/a", "na", "not stated"}:
            return None
    if fdef.type == "date":
        iso = parse_date(value)
        if key == "date_detected" and iso > date.today().isoformat():
            raise FieldValueError(f"Date Detected cannot be in the future ({iso}).")
        return iso
    if fdef.type == "select":
        return match_option(key, value)
    if fdef.type == "score":
        try:
            num = int(round(float(str(value).split("/")[0])))
        except ValueError:
            raise FieldValueError(f"{fdef.label} must be a whole number from 1 to 5.") from None
        if not 1 <= num <= 5:
            raise FieldValueError(f"{fdef.label} must be between 1 and 5 (got {num}).")
        return num
    if key == "rpn":
        return int(value)
    return str(value).strip()


def coerce_form(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Coerce a whole dict leniently: bad values become None and a warning is returned.

    Used on LLM output, where one bad value must not discard the whole extraction.
    """
    out, warnings = {}, []
    for key, value in data.items():
        if key not in FIELD_MAP:
            continue
        try:
            out[key] = coerce_value(key, value)
        except FieldValueError as exc:
            out[key] = None
            warnings.append(str(exc))
    return out, warnings


def missing_fields(form: dict[str, Any]) -> list[str]:
    """Tier-A fields still empty - shown to the user as 'please provide'."""
    return [k for k in TIER_A_KEYS if form.get(k) in (None, "")]
