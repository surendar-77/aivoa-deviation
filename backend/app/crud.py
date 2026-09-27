"""Database operations for deviations + their audit trail.

Why audit by server-side diff: the server compares the stored row with the
incoming form, so every real change gets exactly one audit row even if the
client's change log is incomplete. The client's change log is only used to
attach the *source* (AI-extracted / User instruction ...) and the chat
instruction that caused each change.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from .config import settings
from .fields import FIELD_KEYS, FIELD_MAP, TIER_LABELS, coerce_value
from .models import Deviation, DeviationAudit, deviation_to_dict, form_to_columns, DeviationSequence
from .rules import apply_rules

DEFAULT_USER = "QA Reviewer"


def next_deviation_id(db: Session, today: Optional[date] = None) -> str:
    """DEV-YYYY-NNNN, sequence restarting every calendar year and never reusing a number.

    The per-year counter row is locked (FOR UPDATE on PostgreSQL) so two saves cannot get the same
    number; taking the max with existing IDs keeps records created before the counter existed safe.
    """
    year = (today or date.today()).year
    prefix = f"DEV-{year}-"
    last_id = db.scalar(
        select(func.max(Deviation.deviation_id)).where(Deviation.deviation_id.like(f"{prefix}%")))
    existing = int(last_id.rsplit("-", 1)[1]) if last_id else 0
    counter = db.get(DeviationSequence, year, with_for_update=True)
    seq = max(counter.last_number if counter else 0, existing) + 1
    if counter is None:
        db.add(DeviationSequence(year=year, last_number=seq))
    else:
        counter.last_number = seq
    db.flush()
    return f"{prefix}{seq:04d}"


def find_related(db: Session, form: dict, exclude_id: Optional[str] = None) -> Optional[str]:
    """Most recent prior deviation on the same equipment, or same product + parameter.

    Why: a repeat deviation signals an ineffective CAPA and raises occurrence risk.
    """
    conds = []
    if form.get("equipment_id"):
        conds.append(func.lower(Deviation.equipment_id) == form["equipment_id"].lower())
    if form.get("product_name") and form.get("process_parameter"):
        conds.append(and_(func.lower(Deviation.product_name) == form["product_name"].lower(),
                          func.lower(Deviation.process_parameter) == form["process_parameter"].lower()))
    if not conds:
        return None
    q = select(Deviation.deviation_id).where(or_(*conds))
    current = exclude_id or form.get("deviation_id")
    if current:
        q = q.where(Deviation.deviation_id != current)
    return db.scalar(q.order_by(Deviation.created_at.desc()).limit(1))


def related_lookup(db: Session):
    """Adapter so rules.apply_rules() can call the DB without importing it."""
    return lambda form: find_related(db, form)


def _clean_form(form: dict[str, Any]) -> dict[str, Any]:
    """Keep only registry keys and re-validate values (never trust the client)."""
    out = {}
    for key in FIELD_KEYS:
        value = form.get(key)
        try:
            out[key] = coerce_value(key, value)
        except ValueError:
            out[key] = value if key == "rpn" else None
    return out


def _as_text(v: Any) -> Optional[str]:
    return None if v is None else str(v)


def _source_for(key: str, changes: list[dict]) -> tuple[str, Optional[str]]:
    """Latest client-reported source/instruction for a field, else a sensible default."""
    for ch in reversed(changes or []):
        if ch.get("field") == key:
            return ch.get("source") or "User instruction", ch.get("instruction")
    return TIER_LABELS[FIELD_MAP[key].tier], None


def _write_audit(db: Session, dev_id: str, old: dict, new: dict, changes: list[dict], user: str) -> int:
    count = 0
    for key in FIELD_KEYS:
        if _as_text(old.get(key)) == _as_text(new.get(key)):
            continue
        source, instruction = _source_for(key, changes)
        db.add(DeviationAudit(deviation_id=dev_id, field=key, old_value=_as_text(old.get(key)),
                              new_value=_as_text(new.get(key)), source=source,
                              instruction=instruction, changed_by=user))
        count += 1
    return count


def create_deviation(db: Session, form: dict, user_overrides: dict, changes: list[dict],
                     user: Optional[str] = None) -> dict:
    user = user or DEFAULT_USER
    new = _clean_form(form)
    new["deviation_id"] = next_deviation_id(db)
    new["site"] = new.get("site") or settings.DEFAULT_SITE
    new["date_reported"] = new.get("date_reported") or date.today().isoformat()
    new["status"] = new.get("status") or "Draft"
    new["last_updated_by"] = user
    new = apply_rules(new, user_overrides, related_lookup(db))  # final server-side recompute

    row = Deviation(**form_to_columns(new), user_overrides=user_overrides or {})
    db.add(row)
    db.flush()
    _write_audit(db, new["deviation_id"], {}, new, changes, user)
    db.commit()
    saved = get_deviation(db, new["deviation_id"])
    assert saved is not None  # just inserted
    return saved


def update_deviation(db: Session, deviation_id: str, form: dict, user_overrides: dict,
                     changes: list[dict], user: Optional[str] = None) -> Optional[dict]:
    user = user or DEFAULT_USER
    row = db.scalar(select(Deviation).where(Deviation.deviation_id == deviation_id))
    if row is None:
        return None
    old = deviation_to_dict(row)
    new = _clean_form(form)
    # System-owned identity fields can never be changed by an update.
    for key in ("deviation_id", "date_reported"):
        new[key] = old[key]
    new["site"] = new.get("site") or old["site"]
    new["last_updated_by"] = user
    new = apply_rules(new, user_overrides, lambda f: find_related(db, f, exclude_id=deviation_id))

    _write_audit(db, deviation_id, old, new, changes, user)
    for key, value in form_to_columns(new).items():
        setattr(row, key, value)
    row.user_overrides = user_overrides or {}
    db.commit()
    return get_deviation(db, deviation_id)


def get_deviation(db: Session, deviation_id: str) -> Optional[dict]:
    row = db.scalar(select(Deviation).where(Deviation.deviation_id == deviation_id))
    if row is None:
        return None
    return {"form": deviation_to_dict(row), "user_overrides": row.user_overrides or {},
            "created_at": row.created_at.isoformat(), "last_updated_at": row.last_updated_at.isoformat()}


def list_deviations(db: Session) -> list[dict]:
    rows = db.scalars(select(Deviation).order_by(Deviation.created_at.desc())).all()
    return [{"deviation_id": r.deviation_id, "title": r.title, "batch_number": r.batch_number,
             "product_name": r.product_name, "severity_classification": r.severity_classification,
             "rpn": r.rpn, "status": r.status,
             "date_detected": r.date_detected.isoformat() if r.date_detected else None,
             "last_updated_at": r.last_updated_at.isoformat()} for r in rows]


def delete_deviation(db: Session, deviation_id: str) -> bool:
    row = db.scalar(select(Deviation).where(Deviation.deviation_id == deviation_id))
    if row is None:
        return False
    db.execute(delete(DeviationAudit).where(DeviationAudit.deviation_id == deviation_id))
    db.delete(row)
    db.commit()
    return True


def get_audit(db: Session, deviation_id: str) -> list[dict]:
    rows = db.scalars(select(DeviationAudit).where(DeviationAudit.deviation_id == deviation_id)
                      .order_by(DeviationAudit.changed_at, DeviationAudit.id)).all()
    return [r.to_dict() for r in rows]
