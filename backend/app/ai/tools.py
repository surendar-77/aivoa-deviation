"""The three AI tools named in the assessment, defined with LangChain's @tool.

Why @tool: each tool gets a name, a description and a typed argument schema, so
it is self-documenting, can be invoked (and unit-tested) on its own, and could be
bound to an LLM for tool-calling. In graph.py each tool is wrapped as a LangGraph
node; the router decides which tool runs.

Every tool is a PURE function: inputs in, result dict out (no graph state, no DB).
Errors are returned as {"error": "..."} so the graph can show them in chat.
"""
from __future__ import annotations

import base64
from datetime import date
from typing import Optional

from langchain_core.tools import tool

from .wording import source_phrase
from ..config import settings
from ..fields import TIER_A_KEYS, TIER_LABELS, coerce_form, empty_form
from ..reader import DocumentReadError, read_document
from . import mock, prompts
from .llm import LLMError, call_json
from .operations import computed_field_hint, apply_operations, confirmation, editable_fields_spec, form_summary


@tool
def pdf_extraction_tool(file_name: str, file_b64: str) -> dict:
    """Read an uploaded deviation document (PDF, JPEG/PNG, EML or TXT) and return clean text.

    PDF: text layer first, OCR fallback for scans. Images: Tesseract OCR after
    grayscale/upscale/autocontrast. EML: subject/from/date/body.
    Returns {"text", "method"} or {"error"}.
    """
    try:
        text, method = read_document(file_name, base64.b64decode(file_b64))
    except DocumentReadError as exc:
        return {"error": str(exc)}
    return {"text": text, "method": method}


@tool
def log_interaction_tool(text: str, method: str = "chat message", file_name: Optional[str] = None) -> dict:
    """Extract Tier-A deviation facts from text and log them into a NEW Log Deviation form.

    Only facts stated in the text are kept (null otherwise); Tier-C system fields
    (site, date reported, status, source document) are set by code, never by the AI.
    Returns {"form", "sources", "reply", "warnings"} or {"error"}.
    """
    if settings.mock_mode:
        raw = mock.extract(text)
    else:
        try:
            data = call_json(prompts.EXTRACT_SYSTEM, prompts.EXTRACT_USER.format(method=method, text=text[:12000]))
        except LLMError as exc:
            return {"error": str(exc)}
        raw = data.get("fields", data)
    # Keep ONLY Tier-A keys: even if the model returns an investigator or a score, it is dropped.
    extracted, warnings = coerce_form({k: v for k, v in raw.items() if k in TIER_A_KEYS})

    form = empty_form()
    form.update({k: v for k, v in extracted.items() if v is not None})
    system = {"site": settings.DEFAULT_SITE, "date_reported": date.today().isoformat(),
              "status": "Draft", "source_document": file_name or "chat message"}
    form.update(system)

    filled = [k for k in TIER_A_KEYS if form.get(k) is not None]
    sources = {k: (TIER_LABELS["A"], f"Extracted from {method}") for k in filled}
    sources.update({k: (TIER_LABELS["C"], "System default") for k in system})
    reply = (f"I filled in {len(filled)} of {len(TIER_A_KEYS)} details from {source_phrase(method)} "
             "and checked the risk.")
    return {"form": form, "sources": sources, "reply": reply, "warnings": warnings}


@tool
def edit_interaction_tool(instruction: str, form: dict, user_overrides: dict, history: str = "") -> dict:
    """Apply a natural-language edit (set / update / clear) to any editable field of the current form.

    The LLM (or mock parser) proposes operations {field, action, value, reason};
    operations.apply_operations() validates each one against the field registry.
    Returns {"form", "user_overrides", "sources", "applied", "rejected", "reply"} or {"error"}.
    """
    hint = None
    if settings.mock_mode:
        ops = mock.edit(instruction)
    else:
        try:
            data = call_json(prompts.EDIT_SYSTEM.replace("{fields}", editable_fields_spec()),
                             prompts.EDIT_USER.format(form=form_summary(form), history=history or "(none)",
                                                      message=instruction))
        except LLMError as exc:
            return {"error": str(exc)}
        ops, hint = data.get("operations") or [], data.get("reply")

    new_form, overrides, sources, applied, rejected = apply_operations(form, user_overrides, ops, instruction)
    parts = [confirmation(applied)]
    if rejected:
        parts.append("I didn't change anything for this part: " + " ".join(rejected))
    if not applied and not rejected:
        parts.append(computed_field_hint(instruction) or hint or "I couldn't tell which field to change. Try e.g. 'set the batch number to B-2026-114' "
                             "or 'clear the equipment ID'.")
    return {"form": new_form, "user_overrides": overrides, "sources": sources,
            "applied": applied, "rejected": rejected, "reply": "\n".join(p for p in parts if p)}


TOOLS = [pdf_extraction_tool, log_interaction_tool, edit_interaction_tool]
