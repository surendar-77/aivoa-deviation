"""Deterministic Tier-B rules (plain Python, NOT the LLM).

Why: anything that must be reproducible and auditable in a GMP system
(RPN arithmetic, classification thresholds, due dates, magnitude of the
excursion, repeat detection) is computed by code. The LLM only proposes the
S/O/D judgement scores; everything derived from them is deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable, Optional

# Days allowed to close the investigation, by classification.
DUE_DAYS = {"Critical": 15, "Major": 30, "Minor": 45}

# Fields a user may explicitly override; rules must then keep the user's value.
OVERRIDABLE_RULE_FIELDS = {"severity_classification", "capa_required"}


# ---------------------------------------------------------------------------
# RPN + classification
# ---------------------------------------------------------------------------
def compute_rpn(s: Optional[int], o: Optional[int], d: Optional[int]) -> Optional[int]:
    """Risk Priority Number = S x O x D (FMEA). None until all three scores exist."""
    if not all(isinstance(x, int) for x in (s, o, d)):
        return None
    return s * o * d


def classify_severity(s: Optional[int], rpn: Optional[int]) -> Optional[str]:
    """Critical if S>=5 or RPN>=100; Major if S>=3 or RPN>=40; else Minor.

    Why S alone can escalate: a single catastrophic-severity event (S=5) is
    Critical even if it is rare and easy to detect (low RPN).
    """
    if s is None and rpn is None:
        return None
    s, rpn = s or 0, rpn or 0
    if s >= 5 or rpn >= 100:
        return "Critical"
    if s >= 3 or rpn >= 40:
        return "Major"
    return "Minor"


def capa_required(classification: Optional[str], rpn: Optional[int]) -> Optional[str]:
    """CAPA is mandatory for Critical/Major, or any event with RPN >= 60."""
    if classification is None and rpn is None:
        return None
    return "Yes" if classification in ("Critical", "Major") or (rpn or 0) >= 60 else "No"


def investigation_due_date(start: Optional[str], classification: Optional[str]) -> Optional[str]:
    """date_detected + 15/30/45 days for Critical/Major/Minor (ISO string in/out)."""
    if not start or classification not in DUE_DAYS:
        return None
    try:
        d = date.fromisoformat(start)
    except ValueError:
        return None
    return (d + timedelta(days=DUE_DAYS[classification])).isoformat()


# ---------------------------------------------------------------------------
# Deviation magnitude: parse the approved range and compare the observed value
# ---------------------------------------------------------------------------
_NUM = r"[-+]?\d+(?:\.\d+)?"
# One capture group; the lookahead stops "h" matching the start of "high" etc.
_UNIT = r"(?:(°\s?[CF]|deg\s?[CF]|%\s?w/w|%|ppm|ppb|mbar|bar|kg/cm2|rpm|kg|mg|g|mL|ml|L|hrs?|min|h|mm)(?![A-Za-z]))?"


@dataclass
class Spec:
    low: Optional[float]
    high: Optional[float]
    unit: str

    def describe(self) -> str:
        u = _fmt_unit(self.unit)
        if self.low is not None and self.high is not None:
            return f"{_fmt(self.low)}–{_fmt(self.high)}{u}"
        if self.high is not None:
            return f"NMT {_fmt(self.high)}{u}"
        return f"NLT {_fmt(self.low)}{u}"


def _fmt(x: float) -> str:
    """6.0 -> '6', 0.30000001 -> '0.3' (human-friendly numbers)."""
    return f"{round(x, 4):g}"


def _clean_unit(u: Optional[str]) -> str:
    if not u:
        return ""
    u = u.replace(" ", "")
    u = re.sub(r"^deg", "°", u, flags=re.I)
    if u.startswith("%") and len(u) > 1:  # "%w/w" -> "% w/w"
        u = "% " + u[1:]
    return u


def _fmt_unit(u: str) -> str:
    """'%' hugs the number (0.5%); other units get a space (65 °C)."""
    if not u:
        return ""
    return u if u.startswith("%") else f" {u}"


def parse_spec(approved_range: Optional[str]) -> Optional[Spec]:
    """Parse '60-65 °C', '60 to 65°C', 'NMT 0.5%', '≤0.5%', 'NLT 98%', '2.0 ± 0.2'."""
    if not approved_range:
        return None
    t = approved_range.strip().replace("–", "-").replace("—", "-").replace("+/-", "±")

    m = re.search(rf"({_NUM})\s*{_UNIT}\s*±\s*({_NUM})\s*{_UNIT}", t, re.I)
    if m:  # target ± tolerance
        target, tol = float(m.group(1)), abs(float(m.group(3)))
        return Spec(target - tol, target + tol, _clean_unit(m.group(2) or m.group(4)))

    m = re.search(rf"({_NUM})\s*{_UNIT}\s*(?:-|to)\s*({_NUM})\s*{_UNIT}", t, re.I)
    if m:  # low - high
        lo, hi = float(m.group(1)), float(m.group(3))
        return Spec(min(lo, hi), max(lo, hi), _clean_unit(m.group(4) or m.group(2)))

    m = re.search(rf"(?:NMT|not\s+more\s+than|max(?:imum)?\.?|<=|≤|<|upto|up\s+to)\s*({_NUM})\s*{_UNIT}", t, re.I)
    if m:  # upper limit only
        return Spec(None, float(m.group(1)), _clean_unit(m.group(2)))

    m = re.search(rf"(?:NLT|not\s+less\s+than|min(?:imum)?\.?|>=|≥|>)\s*({_NUM})\s*{_UNIT}", t, re.I)
    if m:  # lower limit only
        return Spec(float(m.group(1)), None, _clean_unit(m.group(2)))
    return None


def parse_observed(observed: Optional[str]) -> Optional[tuple[float, str]]:
    """First number (and unit) in the observed value text, e.g. '71 °C' -> (71.0, '°C')."""
    if not observed:
        return None
    m = re.search(rf"({_NUM})\s*{_UNIT}", observed.replace("–", "-"), re.I)
    if not m:
        return None
    return float(m.group(1)), _clean_unit(m.group(2))


def deviation_magnitude(approved_range: Optional[str], observed_value: Optional[str]) -> Optional[str]:
    """Human-readable excursion size, e.g. '+6 °C above upper limit 65 °C (9.2% over)'."""
    spec, obs = parse_spec(approved_range), parse_observed(observed_value)
    if spec is None or obs is None:
        return None
    value, obs_unit = obs
    unit = _fmt_unit(spec.unit or obs_unit)

    if spec.high is not None and value > spec.high:
        diff = value - spec.high
        pct = f" ({diff / abs(spec.high) * 100:.1f}% over)" if spec.high else ""
        return f"+{_fmt(diff)}{unit} above upper limit {_fmt(spec.high)}{unit}{pct}"
    if spec.low is not None and value < spec.low:
        diff = spec.low - value
        pct = f" ({diff / abs(spec.low) * 100:.1f}% under)" if spec.low else ""
        return f"-{_fmt(diff)}{unit} below lower limit {_fmt(spec.low)}{unit}{pct}"
    return f"Within approved range ({spec.describe()})"


# ---------------------------------------------------------------------------
# Orchestrator used by the LangGraph apply_rules node
# ---------------------------------------------------------------------------
RelatedLookup = Callable[[dict], Optional[str]]


def apply_rules(form: dict[str, Any], user_overrides: dict | None = None,
                find_related: RelatedLookup | None = None) -> dict[str, Any]:
    """Return a copy of the form with every rule-derived Tier-B field recomputed.

    user_overrides: {field: {"value": ..., "reason": ...}} - an explicit human
    decision always wins over the rule (and is recorded in the audit trail).
    find_related: injected DB lookup, so these rules stay pure and unit-testable.
    """
    overrides = user_overrides or {}
    f = dict(form)

    f["rpn"] = compute_rpn(f.get("severity_score"), f.get("occurrence_score"), f.get("detectability_score"))

    if "severity_classification" in overrides:
        f["severity_classification"] = overrides["severity_classification"]["value"]
    else:
        f["severity_classification"] = classify_severity(f.get("severity_score"), f["rpn"])

    if "capa_required" in overrides:
        f["capa_required"] = overrides["capa_required"]["value"]
    else:
        f["capa_required"] = capa_required(f["severity_classification"], f["rpn"])

    # Due date clock starts at detection; fall back to the report date if unknown.
    f["investigation_due_date"] = investigation_due_date(
        f.get("date_detected") or f.get("date_reported"), f["severity_classification"])

    f["deviation_magnitude"] = deviation_magnitude(f.get("approved_range"), f.get("observed_value"))

    if find_related is not None:
        related = find_related(f)
        f["related_deviation_id"] = related
        f["repeat_deviation"] = "Yes" if related else "No"
    return f
