"""LangGraph agent behind POST /api/ai/chat.

    START -> read_input --(file?)--> pdf_extraction_tool -> router
                        \\------------------------------> router
    router --log---> log_interaction_tool -(is it really a deviation?)-> assess_risk -> apply_rules -> finalize -> END
           --edit--> edit_interaction_tool -(risk field changed?)-> assess_risk | apply_rules
           --assess-> assess_risk
           --greeting / help / missing / summary / explain / glossary / undo / off_topic --> converse
           --save / reset / chat -----------------------------------------> finalize

Why a graph instead of one big prompt: each step has ONE job and a narrow,
validated output. The LLM extracts facts and proposes scores/edits (inside the
@tool functions in tools.py); Python validates everything and computes all
derived values (rules.py). Each node is small enough to test and explain.
"""
from __future__ import annotations

import base64
from typing import NotRequired, Optional, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from .. import crud
from ..config import settings
from ..fields import (FIELD_KEYS, FIELD_MAP, RISK_DRIVING_KEYS, SCORE_KEYS, TIER_A_KEYS, TIER_LABELS,
                      _TYPOGRAPHY, coerce_form, empty_form, missing_fields)
from ..rules import apply_rules as run_rules
from . import wording
from . import conversation, mock, prompts
from .llm import LLMError, call_json
from .operations import form_summary
from .tools import edit_interaction_tool, log_interaction_tool, pdf_extraction_tool

INTENTS = {"log", "edit", "assess", "save", "reset", "chat"} | conversation.CONVERSATIONAL
RISK_OUTPUT_KEYS = SCORE_KEYS + ["severity_reasoning", "impact_assessment", "suggested_next_action",
                                 "applicable_sop"]


class AgentState(TypedDict):
    """Graph state. Keys without NotRequired are always set by run_agent(); the rest are filled by nodes."""
    # inputs
    message: str
    file_name: Optional[str]
    file_bytes: Optional[bytes]
    form: dict                      # working copy of the form (replaced by nodes)
    original_form: dict             # form as received (for the change log)
    history: list[dict]
    user_overrides: dict
    # working data
    source_text: NotRequired[Optional[str]]
    extraction_method: NotRequired[Optional[str]]
    intent: NotRequired[str]
    tools_used: list[str]
    sources: dict                   # {field: (source_label, instruction)} -> change log / audit
    needs_risk: bool
    replies: list[str]
    errors: list[str]
    action: Optional[str]
    # output
    response: NotRequired[dict]


def _mark(sources: dict, keys, source: str, instruction: Optional[str] = None) -> dict:
    """Return a NEW sources dict recording who/what produced each field value."""
    return {**sources, **{k: (source, instruction) for k in keys}}


def _has_data(form: dict) -> bool:
    return any(form.get(k) not in (None, "") for k in TIER_A_KEYS)


def _history_text(history: list[dict]) -> str:
    return "\n".join(f"{m.get('role')}: {str(m.get('content'))[:300]}" for m in (history or [])[-6:]) or "(none)"


# --------------------------------------------------------------------------- nodes
def read_input(state: AgentState) -> dict:
    """Entry node: nothing to compute - the edge below decides whether a document must be read."""
    return {}


def pdf_extraction_node(state: AgentState) -> dict:
    """Tool node: uploaded file -> text (PDF / OCR / EML / TXT)."""
    result = pdf_extraction_tool.invoke({
        "file_name": state["file_name"], "file_b64": base64.b64encode(state["file_bytes"] or b"").decode()})
    used = state["tools_used"] + ["pdf_extraction_tool"]
    if "error" in result:
        return {"errors": state["errors"] + [result["error"]], "tools_used": used}
    text = result["text"]
    if state.get("message"):  # the user's typed note is extra context for extraction
        text = f"{text}\n\nAdditional note from user: {state['message']}"
    return {"source_text": text, "extraction_method": result["method"], "tools_used": used}


def router(state: AgentState) -> dict:
    """Classify the user's intent. A readable file upload is always a new 'log'."""
    if state.get("file_bytes"):
        return {"intent": "log" if state.get("source_text") else "chat"}
    message = state.get("message", "").strip()
    if not message:
        return {"intent": "chat"}
    # Deterministic first: small talk, review questions, undo and off-topic chit-chat never reach
    # the log/edit tools, so a sentence like "I am staying in Salem" can't change the form.
    conv = conversation.detect(message, _has_data(state["form"]))
    # Conversation memory: a short answer to the Copilot's own question ("reported by") is part of the
    # earlier request ("change my name to Surendar"), so both go to the edit tool together.
    follow = conversation.pending_question(state.get("history"), message)
    if follow and _has_data(state["form"]) and conv in (None, "off_topic", "ack") and len(message.split()) <= 12:
        request, question = follow
        return {"intent": "edit",
                "message": f'{request} (You asked: "{question}" The user answered: "{message}")'}
    if conv:
        return {"intent": conv}
    if settings.mock_mode:
        return {"intent": mock.route(message, False)}
    try:
        data = call_json(prompts.ROUTER_SYSTEM, prompts.ROUTER_USER.format(
            has_data=_has_data(state["form"]), history=_history_text(state.get("history")), message=message),
            light=True)
        intent = str(data.get("intent", "")).lower()
    except LLMError as exc:
        return {"intent": "chat", "errors": state["errors"] + [str(exc)]}
    if intent not in INTENTS:  # safety net: a long pasted incident is a new deviation
        intent = "log" if len(message) > 250 else "chat"
    return {"intent": intent}


def log_interaction_node(state: AgentState) -> dict:
    """Tool node: extract Tier-A facts into a FRESH form (a new source = a new deviation)."""
    result = log_interaction_tool.invoke({
        "text": state.get("source_text") or state.get("message", ""),
        "method": state.get("extraction_method") or "chat message",
        "file_name": state.get("file_name")})
    used = state["tools_used"] + ["log_interaction_tool"]
    if "error" in result:
        return {"errors": state["errors"] + [result["error"]], "tools_used": used}
    # Relevance gate: text without real deviation facts must not replace the current form.
    ok, why = conversation.looks_like_deviation(state.get("source_text") or state.get("message", ""), result["form"])
    if not ok:
        return {"tools_used": used, "intent": "rejected", "replies": state["replies"] + [why]}
    return {"form": result["form"], "user_overrides": {}, "sources": result["sources"], "needs_risk": True,
            "tools_used": used,
            "replies": state["replies"] + [result["reply"]] + [f"Note: {w}" for w in result["warnings"]]}


def edit_interaction_node(state: AgentState) -> dict:
    """Tool node: natural-language edit -> validated operations on the current form."""
    if not _has_data(state["form"]):  # nothing to edit: never build a "deviation" out of chat fragments
        return {"replies": state["replies"] + [conversation.answer("missing", "", {}, {}, [])]}
    result = edit_interaction_tool.invoke({
        "instruction": state["message"], "form": state["form"],
        "user_overrides": state.get("user_overrides") or {}, "history": _history_text(state.get("history"))})
    used = state["tools_used"] + ["edit_interaction_tool"]
    if "error" in result:
        return {"errors": state["errors"] + [result["error"]], "tools_used": used}
    # Re-score only when a fact that drives risk changed (saves an LLM call otherwise).
    needs_risk = any(k in RISK_DRIVING_KEYS for k in result["sources"]) and _has_data(result["form"])
    return {"form": result["form"], "user_overrides": result["user_overrides"], "needs_risk": needs_risk,
            "sources": {**state["sources"], **result["sources"]}, "tools_used": used,
            "replies": state["replies"] + [result["reply"]]}


# The measured facts the scorer must trust over the free-text description (which can predate a correction).
RISK_KEY_VALUES = ("process_parameter", "approved_range", "observed_value", "manufacturing_stage",
                   "equipment_id", "batch_number", "product_name", "gmp_impact")


def assess_risk(state: AgentState, config: RunnableConfig) -> dict:
    """LLM proposes S/O/D + reasoning + impact + next action. Human overrides are never overwritten."""
    form = dict(state["form"])
    if not _has_data(form):
        return {"replies": state["replies"] + ["There is no deviation data to assess yet."]}
    overrides = state.get("user_overrides") or {}
    # Magnitude and repeat status are deterministic context for the scorer, so compute them first.
    pre = run_rules(form, overrides, _related_lookup(config))
    if settings.mock_mode:
        data = mock.assess(pre)
    else:
        try:
            data = call_json(prompts.RISK_SYSTEM, prompts.RISK_USER.format(
                key_values=form_summary({k: form.get(k) for k in RISK_KEY_VALUES}),
                facts=form_summary({k: form.get(k) for k in TIER_A_KEYS}),
                magnitude=pre.get("deviation_magnitude") or "not computable",
                repeat=f"Yes ({pre.get('related_deviation_id')})" if pre.get("repeat_deviation") == "Yes" else "No"))
        except LLMError as exc:
            return {"errors": state["errors"] + [f"Risk assessment failed: {exc}"]}
    values, _ = coerce_form({k: data.get(k) for k in RISK_OUTPUT_KEYS})
    updated = [k for k, v in values.items() if v is not None and k not in overrides]
    form.update({k: values[k] for k in updated})
    return {"form": form, "sources": _mark(state["sources"], updated, TIER_LABELS["B"], "AI risk assessment")}


def apply_rules(state: AgentState, config: RunnableConfig) -> dict:
    """Deterministic Tier-B fields: RPN, classification, CAPA, due date, magnitude, repeat."""
    before = state["form"]
    if not _has_data(before):  # no facts -> nothing to derive (and no "Repeat: No" on a blank form)
        return {}
    after = run_rules(before, state.get("user_overrides") or {}, _related_lookup(config))
    changed = [k for k in after if after.get(k) != before.get(k) and k not in state["sources"]]
    return {"form": after, "sources": _mark(state["sources"], changed, TIER_LABELS["B"], "Rule engine")}


def converse(state: AgentState) -> dict:
    """Small talk, help, review questions (missing / summary / explain / glossary), undo, off-topic."""
    reply = conversation.answer(state.get("intent", "chat"), state.get("message", ""), state["form"],
                                state.get("user_overrides") or {}, state.get("history") or [])
    return {"replies": state["replies"] + [reply], "action": "undo" if state.get("intent", "chat") == "undo" else None}


def save_action(state: AgentState) -> dict:
    if not _has_data(state["form"]):  # never commit an empty record to the ledger
        return {"replies": state["replies"] + ["There's nothing to save yet. Paste or upload a report first."]}
    return {"action": "save", "replies": state["replies"] + ["Committing the deviation to the QMS ledger…"]}


def reset_action(state: AgentState) -> dict:
    return {"action": "reset", "form": empty_form(), "user_overrides": {},
            "replies": state["replies"] + ["Form cleared. Paste or upload a new report to begin."]}


def chat_reply(state: AgentState) -> dict:
    """Answer questions without touching the form."""
    if state["errors"]:  # e.g. unreadable upload: just report the error
        return {}
    if settings.mock_mode:  # no LLM for open questions: point to what mock mode CAN answer
        reply = ("[Mock mode] Open questions need the Groq LLM. I can still answer \"what's missing?\", "
                 "\"summarize\", \"explain the risk\" and \"what is RPN / CAPA / GMP?\", or say \"help\".")
        return {"replies": state["replies"] + [reply]}
    try:
        data = call_json(prompts.CHAT_SYSTEM, prompts.CHAT_USER.format(
            form=form_summary(state["form"]), message=state.get("message", "")), light=True)
    except LLMError as exc:
        return {"errors": state["errors"] + [str(exc)]}
    return {"replies": state["replies"] + [str(data.get("reply", ""))]}


def finalize(state: AgentState) -> dict:
    """Build the API response, including a per-field change log (old -> new, source, instruction)."""
    old, new = state["original_form"], state["form"]
    changes = []
    if state.get("action") != "reset":
        for key in FIELD_KEYS:
            if old.get(key) != new.get(key):
                source, instruction = state["sources"].get(key, (TIER_LABELS[FIELD_MAP[key].tier], None))
                changes.append({"field": key, "old": old.get(key), "new": new.get(key),
                                "source": source, "instruction": instruction or state.get("message")})

    replies = list(state["replies"])
    risk_keys = set(RISK_OUTPUT_KEYS) | {"rpn", "severity_classification"}
    risk_changed = any(c["field"] in risk_keys for c in changes)
    if new.get("severity_classification") and (state.get("intent", "chat") in ("log", "assess") or risk_changed):
        overridden = "severity_classification" in (state.get("user_overrides") or {})
        replies.append(wording.risk_line(new, overridden))
    miss = missing_fields(new) if _has_data(new) else []
    if state.get("intent", "chat") == "log" and miss:
        replies.append("Not in the report, so I left these blank: " + wording.labels(miss) + ".")
    replies += [f"⚠ {e}" for e in state["errors"]]

    text = state.get("source_text")
    return {"response": {
        "intent": state.get("intent", "chat"),
        "reply": ("\n".join(r for r in replies if r) or "Done.").translate(_TYPOGRAPHY),
        "form": new,
        "changes": changes,
        "missing_fields": miss,
        "user_overrides": state.get("user_overrides") or {},
        "action": state.get("action"),
        "tools_used": state["tools_used"],
        "extraction_method": state.get("extraction_method"),
        "extracted_text_preview": text[:1500] if text else None,
        "errors": state["errors"],
        "mock_mode": settings.mock_mode,
    }}


# --------------------------------------------------------------------------- DB hook
def _related_lookup(config: RunnableConfig):
    """Repeat-deviation lookup. The DB session arrives via LangGraph's config (not global state);
    the lookup is skipped if the DB is unavailable so the AI still works."""
    db = (config or {}).get("configurable", {}).get("db")
    if db is None:
        return None

    def lookup(form):
        try:
            return crud.find_related(db, form)
        except Exception:
            db.rollback()
            return None
    return lookup


# --------------------------------------------------------------------------- graph
def _after_read(state: AgentState) -> str:
    return "pdf_extraction_tool" if state.get("file_bytes") else "router"


def _after_router(state: AgentState) -> str:
    return {"log": "log_interaction_tool", "edit": "edit_interaction_tool", "assess": "assess_risk",
            "save": "save_action", "reset": "reset_action",
            **{i: "converse" for i in conversation.CONVERSATIONAL}}.get(state.get("intent", "chat"), "chat_reply")


def _after_log(state: AgentState) -> str:
    return "assess_risk" if state.get("needs_risk") and state.get("intent", "chat") == "log" else "finalize"


def _after_edit(state: AgentState) -> str:
    return "assess_risk" if state.get("needs_risk") else "apply_rules"


def build_graph():
    g = StateGraph(AgentState)
    for name, fn in [("read_input", read_input), ("pdf_extraction_tool", pdf_extraction_node),
                     ("router", router), ("log_interaction_tool", log_interaction_node),
                     ("edit_interaction_tool", edit_interaction_node), ("assess_risk", assess_risk),
                     ("apply_rules", apply_rules), ("save_action", save_action),
                     ("reset_action", reset_action), ("chat_reply", chat_reply), ("converse", converse),
                     ("finalize", finalize)]:
        g.add_node(name, fn)
    g.add_edge(START, "read_input")
    g.add_conditional_edges("read_input", _after_read)
    g.add_edge("pdf_extraction_tool", "router")
    g.add_conditional_edges("router", _after_router)
    g.add_conditional_edges("log_interaction_tool", _after_log)
    g.add_conditional_edges("edit_interaction_tool", _after_edit)
    g.add_edge("assess_risk", "apply_rules")
    g.add_edge("apply_rules", "finalize")
    for name in ("save_action", "reset_action", "chat_reply", "converse"):
        g.add_edge(name, "finalize")
    g.add_edge("finalize", END)
    return g.compile()


GRAPH = build_graph()


def run_agent(message: str, form: dict | None, history: list | None, user_overrides: dict | None,
              file_name: str | None = None, file_bytes: bytes | None = None, db=None) -> dict:
    """Entry point used by the API route. The DB session is passed via config, not state."""
    base = empty_form()
    base.update({k: v for k, v in (form or {}).items() if k in FIELD_MAP})
    state: AgentState = {
        "message": message or "", "file_name": file_name, "file_bytes": file_bytes,
        "form": dict(base), "original_form": dict(base), "history": list(history or []),
        "user_overrides": dict(user_overrides or {}), "sources": {}, "replies": [], "errors": [],
        "tools_used": [], "needs_risk": False, "action": None,
    }
    return GRAPH.invoke(state, config={"configurable": {"db": db}})["response"]
