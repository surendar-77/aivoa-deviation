"""Offline, rule-based stand-in for the LLM (MOCK MODE: no GROQ_API_KEY).

Why: the app must run end to end without a key (demos, CI, reviewers). It
mirrors the LLM functions' inputs/outputs so the graph code is identical in
both modes - only the "brain" is swapped.
"""
from __future__ import annotations

import re
from typing import Optional

from ..fields import TIER_A_KEYS
from .operations import resolve_field

# "Label: value" line labels -> Tier-A keys
LABELS = {
    "subject": "title", "title": "title",
    "date": "date_detected", "date of occurrence": "date_detected", "date detected": "date_detected",
    "reported by": "reported_by", "from": "reported_by", "reporter": "reported_by",
    "department": "department", "area": "area_location", "location": "area_location",
    "area / location": "area_location", "product": "product_name", "product name": "product_name",
    "batch no": "batch_number", "batch no.": "batch_number", "batch number": "batch_number", "batch": "batch_number",
    "stage": "manufacturing_stage", "equipment": "equipment_id", "equipment id": "equipment_id",
    "parameter": "process_parameter", "approved range": "approved_range", "specification": "approved_range",
    "spec": "approved_range", "observed": "observed_value", "observed value": "observed_value",
    "result": "observed_value", "description": "description", "description of deviation": "description",
    "action": "immediate_action", "immediate action": "immediate_action",
    "probable cause": "root_cause_hypothesis", "root cause": "root_cause_hypothesis",
}
_LABEL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ./]{1,30}?)\s*:\s*(.+)$")


def route(message: str, has_file: bool) -> str:
    m = message.strip().lower()
    if has_file:
        return "log"
    if re.match(r"^(please\s+)?(save|submit|store)\b", m):
        return "save"
    if re.search(r"\b(reset|start over|start again|start (a )?fresh|begin again|new deviation|new one|"
                 r"clear (the )?form|clear everything|discard|scrap|wipe)\b", m):
        return "reset"
    if re.match(r"^(please\s+)?(set|change|update|clear|remove|delete|assign|make|mark|correct)\b", m) \
            or re.search(r"\bshould be\b|\bis actually\b", m):
        return "edit"
    if len(message) > 200 or len(_LABEL_RE.findall(message)) >= 3 or \
            sum(bool(_LABEL_RE.match(line)) for line in message.splitlines()) >= 3:
        return "log"
    if m.endswith("?") or re.match(r"^(what|why|how|explain|which|who|when)\b", m):
        return "chat"
    if len(message) < 150 and any(resolve_field(op["field"]) for op in edit(message)):
        return "edit"  # e.g. "status to Open"
    if re.search(r"\b(assess|re-?assess|risk|rpn|severity)\b", m):
        return "assess"
    return "chat"


def extract(text: str) -> dict:
    """Label: value lines (+ continuation lines) and a few regexes for free-text emails."""
    out: dict[str, Optional[str]] = {k: None for k in TIER_A_KEYS}
    narrative = ("description", "immediate_action", "root_cause_hypothesis")
    current = None  # field that following lines belong to

    def put(key: str, value: str) -> None:
        if key == "reported_by":
            value = re.sub(r"\s*<[^>]+>", "", value)  # drop e-mail address
            if "," in value and not out["department"]:
                value, dept = [p.strip() for p in value.split(",", 1)]
                out["department"] = dept
        if not out.get(key):
            out[key] = value

    for line in text.splitlines():
        stripped = line.strip()
        m = _LABEL_RE.match(line)
        inline_key = LABELS.get(m.group(1).strip().lower()) if m else None
        heading_key = LABELS.get(stripped.lower().rstrip(":"))  # "Batch No." on its own line (PDF tables)
        if inline_key:                          # "Batch No: X"
            put(inline_key, m.group(2).strip())
            current = inline_key if inline_key in narrative else None
        elif heading_key:                       # label line; value on the next line(s)
            current = heading_key
        elif current and stripped:
            if out.get(current) and current in narrative:
                out[current] = f"{out[current]} {stripped}"
            else:
                put(current, stripped)
            if current not in narrative:
                current = None
        else:
            current = None

    # Free-text fallbacks (typical e-mail wording).
    def find(pattern: str) -> Optional[str]:
        mm = re.search(pattern, text, re.I)
        return mm.group(1).strip() if mm else None

    out["batch_number"] = out["batch_number"] or find(r"batch(?:\s+no\.?|\s+number)?\s*[:#]?\s*([A-Z]{1,4}-\d{2,6}(?:-\d{1,4})?)")
    out["equipment_id"] = out["equipment_id"] or find(r"\b(?:reactor|dryer|centrifuge|equipment)\s+([A-Z]{1,4}-\d{2,4})\b")
    out["approved_range"] = out["approved_range"] or find(r"approved range[^.\d]*(\d+(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s*°?\s?C?)")
    out["observed_value"] = out["observed_value"] or find(r"(?:rose|dropped|increased|decreased|fell) to\s+(\d+(?:\.\d+)?\s*°?\s?C?)")
    if out["approved_range"] and "°" in out["approved_range"] and not out["process_parameter"] and "temperature" in text.lower():
        out["process_parameter"] = "Temperature"
    for stage in ("crystallization", "drying", "reaction", "filtration", "centrifugation", "milling", "packaging"):
        if not out["manufacturing_stage"] and re.search(rf"\b{stage}\b", text, re.I):
            out["manufacturing_stage"] = stage
    low = text.lower()
    if "unplanned" in low:
        out["deviation_type"] = "Unplanned"
    if re.search(r"gmp impact[^.\n]*\byes\b", low):
        out["gmp_impact"] = "Yes"
    elif re.search(r"gmp impact[^.\n]*potential|may affect", low):
        out["gmp_impact"] = "Potential"
    if re.search(r"\b(on hold|quarantin)", low):
        out["batch_disposition"] = "Quarantined / On Hold"
    if out["approved_range"] and out["observed_value"]:
        out["category"] = "Process Parameter Excursion"
    if not out["description"]:
        body = text.split("\n\n", 1)[-1]
        out["description"] = " ".join(body.split())[:700] or None
    return out


def assess(form: dict) -> dict:
    """Simple heuristic S/O/D so the deterministic rules have something to work on."""
    gmp = form.get("gmp_impact")
    s = 4 if gmp == "Yes" else 3 if gmp == "Potential" or form.get("observed_value") else 2
    o = 3 if form.get("repeat_deviation") == "Yes" else 2
    text = f"{form.get('description') or ''} {form.get('immediate_action') or ''}".lower()
    d = 2 if re.search(r"alarm|in-process|detected|test", text) else 3
    param = form.get("process_parameter") or "the process parameter"
    return {
        "severity_score": s, "occurrence_score": o, "detectability_score": d,
        "severity_reasoning": f"[Mock] {param} was outside the approved range "
                              f"({form.get('approved_range') or 'n/a'}; observed {form.get('observed_value') or 'n/a'}) "
                              f"at the {form.get('manufacturing_stage') or 'stated'} stage with GMP impact '{gmp or 'unknown'}'.",
        "impact_assessment": f"[Mock] Potential impact on quality attributes of batch {form.get('batch_number') or 'n/a'}; "
                             "batch to remain on hold pending QA evaluation of in-process results.",
        "suggested_next_action": "Keep batch on hold and route to QA investigation.",
        "applicable_sop": "Deviation Management SOP (verify)",
    }


_EDIT_PATTERNS = [
    (re.compile(r"^(?:please\s+)?(?:clear|remove|delete|blank out)\s+(?P<field>.+?)\.?$", re.I), "clear"),
    (re.compile(r"^(?:please\s+)?assign\s+(?P<value>.+?)\s+as\s+(?:the\s+)?(?P<field>.+?)\.?$", re.I), "set"),
    (re.compile(r"^(?:please\s+)?(?:set|change|update|make|mark|correct)\s+(?P<field>.+?)\s+(?:to|as|=)\s+(?P<value>.+?)\.?$", re.I), "set"),
    (re.compile(r"^(?P<field>.+?)\s+(?:should be|is actually|should read|was actually|is|was|were|to|=)\s+(?P<value>.+?)\.?$", re.I), "set"),
]
# Casual lead-ins stripped before parsing: "ah sorry, the batch number is ..."
_FILLER = re.compile(r"^(?:(?:ah|oh|ok|okay|sorry|actually|please|hey|also|wait|hmm)[\s,!.]*)+", re.I)


def _split_clauses(message: str) -> list[str]:
    """Split on ';', newlines and 'and' - but only when 'and' starts a new field clause,
    so values such as "Quarantined and labelled" are kept intact."""
    parts = []
    for chunk in re.split(r"\s*(?:;|\n)\s*", message.strip()):
        pieces = re.split(r"\s*,?\s+and\s+(?:also\s+)?", chunk)
        current = pieces[0]
        for piece in pieces[1:]:
            head = re.match(r"^(?:the\s+)?(.+?)\s+(?:is|to|should be|=)\s+", piece, re.I)
            starts_clause = re.match(r"^(set|change|update|clear|remove|delete|assign)\b", piece, re.I)
            if starts_clause or (head and resolve_field(head.group(1))):
                parts.append(current)
                current = piece
            else:
                current = f"{current} and {piece}"
        parts.append(current)
    return [p for p in parts if p.strip()]


def edit(message: str) -> list[dict]:
    """'set X to Y' / 'clear X' / 'assign Y as X' / 'X is Y and Z is W' / 'X should be Y because Z'."""
    ops = []
    for part in _split_clauses(_FILLER.sub("", message.strip())):
        part = _FILLER.sub("", part.strip())
        reason = None
        m_reason = re.search(r"\s+because\s+(.+)$", part, re.I)
        if m_reason:
            reason, part = m_reason.group(1), part[:m_reason.start()]
        for pattern, action in _EDIT_PATTERNS:
            m = pattern.match(part.strip())
            if m:
                field = resolve_field(m.group("field")) or m.group("field")
                value = m.groupdict().get("value")
                if value:  # "R-305 not R-201" / "R-305, not R-201" -> "R-305"
                    value = re.sub(r"\s*,?\s+(?:and\s+)?not\s+.+$", "", value).strip() or value
                ops.append({"field": field, "action": action, "value": value, "reason": reason})
                break
    return ops
