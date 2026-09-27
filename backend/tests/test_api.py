"""End-to-end API flow in MOCK MODE on in-memory SQLite: log -> edit -> save -> audit."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from app import main
from app.config import settings
from app.db import init_db

SAMPLES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(type(settings), "GROQ_API_KEY", "")  # force mock mode
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    main.app.dependency_overrides[main.get_db] = _db
    monkeypatch.setitem(main.DB_STATUS, "ok", True)
    yield TestClient(main.app)  # no lifespan: tables already created above
    main.app.dependency_overrides.clear()


def chat(client, message="", form=None, overrides=None, file=None):
    data = {"message": message, "form": json.dumps(form or {}), "history": "[]",
            "user_overrides": json.dumps(overrides or {})}
    files = {"file": (file, (SAMPLES / file).read_bytes())} if file else None
    r = client.post("/api/ai/chat", data=data, files=files)
    assert r.status_code == 200, r.text
    return r.json()


def test_fields_endpoint(client):
    body = client.get("/api/fields").json()
    assert body["mock_mode"] is True and len(body["fields"]) > 30


def test_log_from_email_then_edit_save_and_audit(client):
    r = chat(client, file="deviation_email.txt")
    assert r["intent"] == "log" and r["mock_mode"]
    form = r["form"]
    assert form["batch_number"] == "MS-2609-017" and form["equipment_id"] == "R-201"
    assert form["deviation_magnitude"].startswith("+6 °C above upper limit 65 °C")
    assert form["assigned_investigator"] is None      # Tier C never invented
    assert form["rpn"] == form["severity_score"] * form["occurrence_score"] * form["detectability_score"]

    edits = ["change batch number to B-2026-114", "clear the equipment ID",
             "assign Dr. Priya Rao as investigator", "status to Open"]
    overrides, changes = r["user_overrides"], r["changes"]
    for msg in edits:
        r = chat(client, msg, form, overrides)
        assert r["intent"] == "edit" and r["changes"], msg
        form, overrides, changes = r["form"], r["user_overrides"], changes + r["changes"]
    assert form["batch_number"] == "B-2026-114" and form["equipment_id"] is None
    assert form["assigned_investigator"] == "Dr. Priya Rao" and form["status"] == "Open"

    r = chat(client, "severity should be Minor because excursion was brief", form, overrides)
    assert r["form"]["severity_classification"] == "Minor"
    assert r["user_overrides"]["severity_classification"]["reason"] == "excursion was brief"
    form, overrides = r["form"], r["user_overrides"]

    assert chat(client, "save", form, overrides)["action"] == "save"
    saved = client.post("/api/deviations", json={"form": form, "user_overrides": overrides, "changes": changes})
    assert saved.status_code == 201, saved.text
    dev_id = saved.json()["form"]["deviation_id"]
    assert saved.json()["form"]["severity_classification"] == "Minor"   # override survives server recompute

    audit = client.get(f"/api/deviations/{dev_id}/audit").json()
    by_field = {a["field"]: a for a in audit}
    assert by_field["batch_number"]["instruction"] == "change batch number to B-2026-114"
    assert by_field["batch_number"]["source"] == "User instruction"
    # The title quoted the old batch number, so the correction reached it too (and is attributed to the user);
    # fields the edit did not touch keep their original source.
    assert "B-2026-114" in form["title"] and by_field["title"]["source"] == "User instruction"
    untouched = [a for f, a in by_field.items() if f not in ("title", "description", "batch_number", "equipment_id")
                 and a["source"] == "AI-extracted"]
    assert untouched, "fields the edit did not touch should still be attributed to the source document"

    # Load back, edit, update -> only the changed field is audited.
    loaded = client.get(f"/api/deviations/{dev_id}").json()
    r = chat(client, "set quarantine reference to QR-2026-077", loaded["form"], loaded["user_overrides"])
    upd = client.put(f"/api/deviations/{dev_id}", json={"form": r["form"], "user_overrides": r["user_overrides"],
                                                         "changes": r["changes"]})
    assert upd.status_code == 200
    new_rows = client.get(f"/api/deviations/{dev_id}/audit").json()[len(audit):]
    assert [a["field"] for a in new_rows] == ["quarantine_reference"]


def test_pdf_upload_and_repeat_detection(client):
    r = chat(client, file="deviation_report.pdf")
    assert r["extraction_method"] == "PDF text layer (pypdf)"
    assert r["form"]["batch_number"] == "AC-2609-042"
    assert r["form"]["deviation_magnitude"].startswith("+0.7% w/w above upper limit 0.5% w/w")
    client.post("/api/deviations", json={"form": r["form"]})
    again = chat(client, file="deviation_report.pdf")
    assert again["form"]["repeat_deviation"] == "Yes"


def test_errors_are_helpful(client):
    assert client.post("/api/ai/chat", data={"message": ""}).status_code == 422
    assert client.get("/api/deviations/DEV-1999-0001").status_code == 404
    assert client.post("/api/deviations", json={"form": {}}).status_code == 422


# --------------------------------------------------------------------------- voice input
def test_transcribe_in_mock_mode_points_to_browser_fallback(client):
    r = client.post("/api/ai/transcribe", files={"audio": ("voice.webm", b"x" * 2048, "audio/webm")})
    assert r.status_code == 503 and "browser" in r.json()["detail"]


def test_transcribe_returns_text_for_review(client, monkeypatch):
    monkeypatch.setattr(type(settings), "GROQ_API_KEY", "test-key")
    monkeypatch.setattr(main, "transcribe", lambda audio, name: "change batch number to MS-2609-018")
    r = client.post("/api/ai/transcribe", files={"audio": ("voice.webm", b"x" * 2048, "audio/webm")})
    assert r.status_code == 200 and r.json()["text"] == "change batch number to MS-2609-018"


def test_transcribe_rejects_a_click_as_too_short():
    from app.ai.speech import SpeechError, transcribe

    with pytest.raises(SpeechError, match="too short"):
        transcribe(b"x" * 10, "voice.webm")


def test_voice_units_are_written_as_in_records():
    from app.ai.speech import normalize_units

    assert normalize_units("observed value to 72 degrees Celsius.") == "observed value to 72 °C."
    assert normalize_units("LOD is 1.2 percent") == "LOD is 1.2 %"
    assert normalize_units("range 60 to 65 °C") == "range 60 to 65 °C"


def test_silence_hallucinations_are_rejected():
    from app.ai.speech import is_hallucination

    assert is_hallucination("Thank you.")
    assert is_hallucination(" thanks for watching! ")
    assert is_hallucination("Change the batch to MS-2609-018", [{"no_speech_prob": 0.9}])
    assert not is_hallucination("Thank you, now set severity to 4")
    assert not is_hallucination("Change the batch to MS-2609-018", [{"no_speech_prob": 0.02}])
