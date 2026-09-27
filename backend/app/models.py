"""ORM tables. The `deviations` columns are GENERATED from the field registry.

Why: fields.py is the single source of truth - adding a field there adds the
DB column automatically, so the form, the AI and the table never disagree.
"""
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .fields import FIELDS, FieldDef


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _column_for(f: FieldDef):
    """Registry field type -> SQL column type."""
    if f.key == "deviation_id":
        return mapped_column(String(20), unique=True, index=True, nullable=False)
    if f.type == "date":
        return mapped_column(Date, nullable=True)
    if f.type == "score" or f.key == "rpn":
        return mapped_column(Integer, nullable=True)
    if f.type == "textarea":
        return mapped_column(Text, nullable=True)
    return mapped_column(String(255), nullable=True)


_deviation_attrs = {
    "__tablename__": "deviations",
    "__doc__": "One row per logged deviation (all registry fields + metadata).",
    "id": mapped_column(Integer, primary_key=True, autoincrement=True),
    # Explicit human decisions that override AI/rule values, e.g.
    # {"severity_classification": {"value": "Major", "reason": "..."}}
    "user_overrides": mapped_column(JSON, nullable=False, default=dict),
    "created_at": mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False),
    "last_updated_at": mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False),
    **{f.key: _column_for(f) for f in FIELDS},
}
# Typed as Any: the columns are created at runtime from the registry, so static checkers cannot see them.
Deviation: Any = type("Deviation", (Base,), _deviation_attrs)


def deviation_to_dict(row) -> dict:
    """ORM row -> JSON-safe dict (dates as ISO strings)."""
    out = {}
    for f in FIELDS:
        v = getattr(row, f.key)
        out[f.key] = v.isoformat() if isinstance(v, date) else v
    return out


def form_to_columns(form: dict) -> dict:
    """Form dict (ISO date strings) -> column values (date objects)."""
    cols = {}
    for f in FIELDS:
        if f.key not in form:
            continue
        v = form[f.key]
        if f.type == "date" and isinstance(v, str) and v:
            v = date.fromisoformat(v)
        cols[f.key] = v
    return cols


class DeviationAudit(Base):
    """Audit trail (21 CFR Part 11 style): one row per field change, who/what/why/when."""

    __tablename__ = "deviation_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deviation_id: Mapped[str] = mapped_column(
        String(20), ForeignKey("deviations.deviation_id", ondelete="CASCADE"), index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(40))          # AI-extracted | AI-computed | User instruction | System
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)  # chat message that caused it
    changed_by: Mapped[str] = mapped_column(String(100))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "deviation_id": self.deviation_id, "field": self.field,
            "old_value": self.old_value, "new_value": self.new_value, "source": self.source,
            "instruction": self.instruction, "changed_by": self.changed_by,
            "changed_at": self.changed_at.isoformat() if self.changed_at else None,
        }


class DeviationSequence(Base):
    """Last record number issued per year. Numbers only go up and are never reused, even after a
    deviation is deleted (a reused ID would make old references and printouts ambiguous)."""

    __tablename__ = "deviation_sequence"

    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, default=0)
