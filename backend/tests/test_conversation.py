"""Conversational NLP + guardrails: chit-chat must never change the form (mock mode, no DB)."""
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.ai.graph import run_agent
from app.config import settings

SAMPLES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(type(settings), "GROQ_API_KEY", "")


@pytest.fixture(scope="module")
def logged():
    """A form logged from the sample e-mail, reused as the 'current form'."""
    settings_key = type(settings).GROQ_API_KEY
    type(settings).GROQ_API_KEY = ""
    try:
        res = run_agent((SAMPLES / "deviation_email.txt").read_text(encoding="utf-8"), {}, [], {})
    finally:
        type(settings).GROQ_API_KEY = settings_key
    return res


def ask(msg, res=None):
    res = res or {"form": {}, "user_overrides": {}}
    return run_agent(msg, res["form"], [], res["user_overrides"])


@pytest.mark.parametrize("msg", [
    "im staying in salem", "I am staying in Salem", "my name is Surendar", "I live in Chennai",
    "what is the weather today", "tell me a joke", "write me a python script", "asdfgh", "the sky is blue",
])
def test_off_topic_never_changes_the_form(logged, msg):
    out = ask(msg, logged)
    assert out["intent"] == "off_topic"
    assert out["changes"] == []
    assert "haven't changed anything" in out["reply"]


@pytest.mark.parametrize("msg,intent", [
    ("hi", "greeting"), ("Good morning", "greeting"), ("thanks!", "thanks"), ("ok", "ack"),
    ("help", "help"), ("what can you do", "help"), ("who are you", "help"),
    ("what is missing?", "missing"), ("which fields are empty", "missing"),
    ("summarize", "summary"), ("show me the form", "summary"),
    ("explain the risk", "explain"), ("why is it major?", "explain"),
    ("what is RPN", "glossary"), ("what does CAPA mean", "glossary"), ("define GMP", "glossary"),
    ("what did you change?", "changes"), ("undo", "undo"), ("undo that", "undo"),
])
def test_conversational_intents(logged, msg, intent):
    out = ask(msg, logged)
    assert out["intent"] == intent
    assert out["changes"] == []
    assert out["reply"]


def test_undo_returns_client_action(logged):
    assert ask("undo", logged)["action"] == "undo"


def test_explain_cites_scores_and_rule(logged):
    reply = ask("why is it major?", logged)["reply"]
    assert "RPN" in reply and "Major" in reply


def test_non_deviation_text_is_not_logged():
    out = ask("location: salem\nname: surendar\ncity: chennai\nhobby: cricket")
    assert out["intent"] == "rejected"
    assert out["changes"] == []
    assert "doesn't look like a deviation" in out["reply"]


def test_edit_on_empty_form_is_refused():
    out = ask("site is Salem")
    assert out["changes"] == []
    assert "no deviation" in out["reply"].lower()


@pytest.mark.parametrize("msg,field,value", [
    ("the reactor was R-305 not R-201", "equipment_id", "R-305"),
    ("location is Block C", "area_location", "Block C"),
    ("set date detected to yesterday", "date_detected", (date.today() - timedelta(days=1)).isoformat()),
])
def test_natural_edits_still_work(logged, msg, field, value):
    out = ask(msg, logged)
    assert out["intent"] == "edit"
    assert out["form"][field] == value


@pytest.mark.parametrize("msg", ["start over", "set foo to bar", "set status to Banana",
                                 "scrap everything and let's start a fresh one", "discard this and begin again"])
def test_commands_are_not_treated_as_off_topic(logged, msg):
    assert ask(msg, logged)["intent"] in ("reset", "edit")


def test_future_detection_date_rejected(logged):
    out = ask("set date detected to 2099-01-01", logged)
    assert out["form"]["date_detected"] == logged["form"]["date_detected"]
    assert "future" in out["reply"]


def test_save_on_empty_form_is_refused():
    out = ask("save")
    assert out["action"] is None
    assert "nothing to save" in out["reply"].lower()


# --------------------------------------------------------------------------- conversation memory
from app.ai import conversation, graph

ASKED = [
    {"role": "user", "content": "change my name to surendar"},
    {"role": "assistant", "content": "Which field should be updated to Surendar - the Reported By or Assigned Investigator?"},
]


def test_pending_question_skips_the_current_message_the_client_appends():
    history = ASKED + [{"role": "user", "content": "reportded by"}]
    assert conversation.pending_question(history, "reportded by") == (
        "change my name to surendar", ASKED[1]["content"])


def test_no_pending_question_when_the_copilot_did_not_ask():
    history = [{"role": "user", "content": "set status to Open"},
               {"role": "assistant", "content": "Got it. I have updated the Status to \"Open\"."}]
    assert conversation.pending_question(history, "reported by") is None


def _router_state(message, history, form=None):
    return {"message": message, "history": history, "file_bytes": None, "errors": [],
            "form": form if form is not None else {"title": "Reactor excursion", "batch_number": "MS-1"}}


def test_short_answer_to_a_question_is_routed_to_edit_with_the_original_request():
    out = graph.router(_router_state("reportded by", ASKED + [{"role": "user", "content": "reportded by"}]))
    assert out["intent"] == "edit"
    assert "change my name to surendar" in out["message"] and "reportded by" in out["message"]


def test_greeting_after_a_question_is_still_a_greeting():
    assert graph.router(_router_state("thanks", ASKED))["intent"] == "thanks"


def test_off_topic_is_still_refused_when_nothing_was_asked():
    history = [{"role": "user", "content": "set status to Open"}, {"role": "assistant", "content": "Updated."}]
    assert graph.router(_router_state("I am staying in Salem", history))["intent"] == "off_topic"


@pytest.mark.parametrize("msg", ["actually change it back to 72 °C", "sorry, set status to Open",
                                 "can you revert the batch number", "oh wait, clear the equipment ID"])
def test_commands_with_conversational_openers_are_not_refused(msg):
    assert conversation.detect(msg, True) is None


@pytest.mark.parametrize("msg", ["save", "save it", "Save the report.", "please save", "commit"])
def test_save_is_recognised_without_the_llm(msg):
    assert conversation.detect(msg, True) == "save"


def test_a_sentence_mentioning_save_is_not_a_save_command():
    assert conversation.detect("save the date of detection as yesterday", True) != "save"
