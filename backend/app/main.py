"""FastAPI application: field registry, AI chat, and deviation CRUD + audit.

Run: uvicorn app.main:app --reload --port 8000   (from the backend/ folder)
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import crud
from .ai.graph import run_agent
from .ai.speech import SpeechError, transcribe
from .config import settings
from .db import get_db, init_db
from .fields import registry_payload
from .reader import tesseract_available

log = logging.getLogger("aivoa")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
DB_STATUS = {"ok": False, "error": None}


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create tables on startup. If Postgres is down the AI still works; saving reports a clear error."""
    try:
        init_db()
        DB_STATUS.update(ok=True, error=None)
    except SQLAlchemyError as exc:
        DB_STATUS.update(ok=False, error=str(exc.__cause__ or exc)[:300])
        log.error("Database unavailable: %s", DB_STATUS["error"])
    yield


app = FastAPI(title="AIVOA Deviation Intake API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(_, exc: SQLAlchemyError):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=503, content={
        "detail": f"Database error - is PostgreSQL running and DATABASE_URL correct? ({str(exc.__cause__ or exc)[:200]})"})


# --------------------------------------------------------------------------- meta
@app.get("/api/health")
def health():
    return {"status": "ok", "mock_mode": settings.mock_mode, "model": settings.GROQ_MODEL,
            "speech_model": None if settings.mock_mode else settings.GROQ_WHISPER_MODEL,
            "database": DB_STATUS, "tesseract": tesseract_available()}


@app.get("/api/fields")
def get_fields():
    """The field registry - the frontend builds the whole form from this."""
    return {**registry_payload(), "mock_mode": settings.mock_mode,
            "model": None if settings.mock_mode else settings.GROQ_MODEL}


# --------------------------------------------------------------------------- AI
def _parse_json_field(raw: Optional[str], default: Any, name: str) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(422, f"'{name}' must be valid JSON.") from None


@app.post("/api/ai/chat")
async def ai_chat(
    message: str = Form(""),
    file: Optional[UploadFile] = File(None),
    form: Optional[str] = Form(None, description="Current form as JSON"),
    history: Optional[str] = Form(None, description="Chat history as JSON list of {role, content}"),
    user_overrides: Optional[str] = Form(None, description="JSON {field: {value, reason}}"),
    db: Session = Depends(get_db),
):
    """Multipart because a file may be attached; the form/history travel as JSON strings."""
    file_name = file_bytes = None
    if file is not None and file.filename:
        file_bytes = await file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "File too large (max 15 MB).")
        file_name = file.filename
    if not message.strip() and not file_bytes:
        raise HTTPException(422, "Send a message or attach a file.")
    return run_agent(
        message=message,
        form=_parse_json_field(form, {}, "form"),
        history=_parse_json_field(history, [], "history"),
        user_overrides=_parse_json_field(user_overrides, {}, "user_overrides"),
        file_name=file_name, file_bytes=file_bytes,
        db=db if DB_STATUS["ok"] else None,
    )


@app.post("/api/ai/transcribe")
async def ai_transcribe(audio: UploadFile = File(..., description="Short voice recording (webm/ogg/mp4/wav)")):
    """Voice input -> text. The text is returned to the chat box for review; it is NOT sent to the agent here."""
    if settings.mock_mode:
        raise HTTPException(503, "Voice transcription needs a GROQ_API_KEY. In mock mode the browser's speech recognition is used instead.")
    data = await audio.read()
    try:
        text = transcribe(data, audio.filename or "voice.webm")
    except SpeechError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"text": text, "model": settings.GROQ_WHISPER_MODEL}


# --------------------------------------------------------------------------- CRUD
class SaveRequest(BaseModel):
    form: dict
    user_overrides: dict = Field(default_factory=dict)
    changes: list[dict] = Field(default_factory=list, description="Chat change log since last save")
    saved_by: Optional[str] = None


@app.post("/api/deviations", status_code=201)
def create(req: SaveRequest, db: Session = Depends(get_db)):
    if not any(req.form.get(k) for k in ("title", "description", "batch_number")):
        raise HTTPException(422, "Nothing to save yet - log a deviation first.")
    return crud.create_deviation(db, req.form, req.user_overrides, req.changes, req.saved_by)


@app.get("/api/deviations")
def list_all(db: Session = Depends(get_db)):
    return crud.list_deviations(db)


@app.get("/api/deviations/{deviation_id}")
def get_one(deviation_id: str, db: Session = Depends(get_db)):
    dev = crud.get_deviation(db, deviation_id)
    if dev is None:
        raise HTTPException(404, f"Deviation {deviation_id} not found.")
    return dev


@app.put("/api/deviations/{deviation_id}")
def update(deviation_id: str, req: SaveRequest, db: Session = Depends(get_db)):
    dev = crud.update_deviation(db, deviation_id, req.form, req.user_overrides, req.changes, req.saved_by)
    if dev is None:
        raise HTTPException(404, f"Deviation {deviation_id} not found.")
    return dev


@app.delete("/api/deviations/{deviation_id}", status_code=204)
def remove(deviation_id: str, db: Session = Depends(get_db)):
    if not crud.delete_deviation(db, deviation_id):
        raise HTTPException(404, f"Deviation {deviation_id} not found.")


@app.get("/api/deviations/{deviation_id}/audit")
def audit(deviation_id: str, db: Session = Depends(get_db)):
    if crud.get_deviation(db, deviation_id) is None:
        raise HTTPException(404, f"Deviation {deviation_id} not found.")
    return crud.get_audit(db, deviation_id)
