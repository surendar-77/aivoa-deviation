"""Repository: ID sequence, audit rows per change, repeat-deviation lookup (in-memory SQLite)."""
import pytest
from sqlalchemy.orm import sessionmaker

from app import crud
from app.db import init_db, make_engine


@pytest.fixture()
def db():
    engine = make_engine("sqlite://")
    init_db(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    yield session
    session.close()


FORM = {"title": "Temp excursion", "date_detected": "2026-09-14", "equipment_id": "R-201",
        "product_name": "Metoprolol Succinate", "process_parameter": "Reactor temperature",
        "approved_range": "60-65 °C", "observed_value": "71 °C",
        "severity_score": 4, "occurrence_score": 2, "detectability_score": 3}


def test_create_assigns_id_and_system_fields(db):
    saved = crud.create_deviation(db, FORM, {}, [])
    f = saved["form"]
    assert f["deviation_id"].startswith("DEV-") and f["deviation_id"].endswith("-0001")
    assert f["status"] == "Draft" and f["site"] and f["date_reported"]
    assert f["rpn"] == 24 and f["severity_classification"] == "Major"
    assert f["repeat_deviation"] == "No"


def test_sequence_and_repeat_detection(db):
    first = crud.create_deviation(db, FORM, {}, [])["form"]["deviation_id"]
    second = crud.create_deviation(db, {**FORM, "batch_number": "X2"}, {}, [])["form"]
    assert second["deviation_id"].endswith("-0002")
    assert second["repeat_deviation"] == "Yes" and second["related_deviation_id"] == first


def test_audit_rows_one_per_change_with_source(db):
    dev = crud.create_deviation(db, FORM, {}, [])["form"]
    n_create = len(crud.get_audit(db, dev["deviation_id"]))
    assert n_create >= 10  # every populated field audited on creation

    changes = [{"field": "equipment_id", "old": "R-201", "new": "R-202",
                "source": "User instruction", "instruction": "change equipment to R-202"}]
    crud.update_deviation(db, dev["deviation_id"], {**dev, "equipment_id": "R-202", "status": "Open"}, {}, changes)
    audit = crud.get_audit(db, dev["deviation_id"])[n_create:]
    by_field = {a["field"]: a for a in audit}
    assert set(by_field) == {"equipment_id", "status"}
    assert by_field["equipment_id"]["instruction"] == "change equipment to R-202"
    assert by_field["equipment_id"]["old_value"] == "R-201"


def test_update_cannot_change_identity(db):
    dev = crud.create_deviation(db, FORM, {}, [])["form"]
    upd = crud.update_deviation(db, dev["deviation_id"],
                                {**dev, "deviation_id": "HACK", "date_reported": "2000-01-01"}, {}, [])
    assert upd["form"]["deviation_id"] == dev["deviation_id"]
    assert upd["form"]["date_reported"] == dev["date_reported"]


def test_delete_and_list(db):
    dev = crud.create_deviation(db, FORM, {}, [])["form"]
    assert len(crud.list_deviations(db)) == 1
    assert crud.delete_deviation(db, dev["deviation_id"]) is True
    assert crud.list_deviations(db) == [] and crud.get_audit(db, dev["deviation_id"]) == []


def test_record_numbers_are_never_reused_after_delete(db):
    first = crud.create_deviation(db, FORM, {}, [])["form"]["deviation_id"]
    second = crud.create_deviation(db, FORM, {}, [])["form"]["deviation_id"]
    assert crud.delete_deviation(db, second)
    third = crud.create_deviation(db, FORM, {}, [])["form"]["deviation_id"]
    assert first.endswith("-0001") and second.endswith("-0002")
    assert third.endswith("-0003"), f"deleted number was reused: {third}"
