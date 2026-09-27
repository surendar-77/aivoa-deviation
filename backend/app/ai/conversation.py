"""Conversational NLP layer: everything the user says that is NOT a log/edit/save.

Why deterministic (no LLM): these answers are built from the form itself, so they are
instant, identical in mock and Groq mode, can never hallucinate a value, and are easy
to unit-test. The LLM is only used for open GMP questions (graph.chat_reply).

It also contains the two guardrails that stop chit-chat from touching the form:
  * detect()           - catches greetings, personal statements and off-topic requests first
  * looks_like_deviation() - a pasted text must contain real deviation facts before it is logged
"""
from __future__ import annotations

import re
from typing import Optional

from ..fields import TIER_A_KEYS, missing_fields
from . import wording

# Intents answered here (the graph routes them to the "converse" node).
CONVERSATIONAL = {"greeting", "thanks", "ack", "help", "missing", "summary", "explain", "glossary",
                  "changes", "undo", "off_topic"}

# Words that make a message "about the deviation / QMS" - used to tell domain questions from chit-chat.
DOMAIN_WORDS = re.compile(
    r"\b(deviation|batch|lot|reactor|dryer|centrifuge|equipment|temperature|pressure|ph|lod|assay|impurity|"
    r"spec(ification)?|range|excursion|oos|oot|gmp|capa|rpn|severity|occurrence|detectability|risk|sop|qa|qc|"
    r"quality|investigat\w*|quarantine|product|api|crystalli[sz]ation|drying|filtration|stage|parameter|"
    r"observed|approved|root cause|impact|audit|form|field|status|ich|fda|21 cfr|validation|"
    r"notification|disposition|containment|save|commit|submit|ledger|record|entry|"
    r"reset|scrap|discard|fresh|start over|start again|begin again|clear|wipe|new one|blank)\b", re.I)

# Facts that make a text a real deviation (at least two, or one plus deviation vocabulary).
CORE_FACTS = ["product_name", "batch_number", "equipment_id", "process_parameter", "approved_range",
              "observed_value", "manufacturing_stage", "category"]
DEVIATION_WORDS = re.compile(
    r"\b(deviation|excursion|out of (spec|range|specification)|oos|exceed\w*|outside|failure|failed|"
    r"malfunction|breakdown|alarm|spill|contamination|mix-?up|not as per|incident|non-?conformance)\b", re.I)

GLOSSARY = {
    "rpn": "The risk score (RPN, Risk Priority Number) is severity × likelihood × how hard the problem is to "
           "detect, each rated 1 to 5, so it runs from 1 to 125. Here a score of 100 or more means Critical and "
           "40 or more means Major; 60 or more also calls for corrective action (CAPA).",
    "capa": "Corrective action (CAPA, Corrective And Preventive Action) is the plan to fix the cause so the problem "
            "does not happen again. Here it is needed for Critical and Major cases, or when the risk score is 60 or more.",
    "severity": "Severity (1 to 5) is how much the problem could affect product quality or patient safety: "
                "1 negligible up to 5 critical. 5 means Critical, 3 or more means Major, otherwise Minor "
                "(unless the risk score says higher).",
    "occurrence": "Likelihood (occurrence, 1 to 5) is how likely the problem is to happen again: 1 a one-off, "
                  "5 keeps recurring.",
    "detectability": "Hard to detect (detectability, 1 to 5) is how likely our checks would miss the problem "
                     "before the product is released: 1 we would certainly catch it, 5 we would not.",
    "gmp": "GMP (Good Manufacturing Practice) is the set of rules for making medicines safely. 'Affects product "
           "quality (GMP impact)' says whether this event could affect quality or compliance: Yes, No or Potential.",
    "oos": "OOS (Out Of Specification) means a test result is outside the approved limits.",
    "api": "API (Active Pharmaceutical Ingredient) is the drug substance made at this site, the part of a "
           "medicine that has the effect.",
    "sop": "An SOP (Standard Operating Procedure) is a written work instruction. The suggested procedures are "
           "only a hint and must be checked by the quality team.",
    "tier": "Each field shows who may fill it: 'From the report' (the AI, only with facts written in the report), "
            "'Calculated' (the AI risk check or fixed rules) and 'Set by a person' (never guessed by the AI).",
    "magnitude": "'How far outside the limit' is calculated by fixed rules from the actual value and the allowed "
                 "range, for example '+6 °C above upper limit 65 °C (9.2% over)'.",
    "repeat": "A repeat means an earlier report on the same machine, or on the same product and measurement. "
              "It is looked up automatically and makes the likelihood score higher.",
    "alcoa": "ALCOA+ is the rule that records must show who did what and when, be readable, original, accurate "
             "and complete. That is why every change here is kept in a change history.",
}
_GLOSSARY_ALIASES = {"risk priority number": "rpn", "corrective": "capa", "preventive": "capa",
                     "good manufacturing": "gmp", "out of specification": "oos", "s score": "severity",
                     "o score": "occurrence", "d score": "detectability", "tiers": "tier", "ai-extracted": "tier",
                     "human/system": "tier", "ai-computed": "tier", "repeat deviation": "repeat",
                     "standard operating": "sop", "data integrity": "alcoa"}

HELP_TEXT = (
    "I'm the AIVOA assistant for reporting quality problems (deviations). I can:\n"
    "• Fill in the form from a report: paste an email or text, or upload a PDF, photo, EML or TXT file.\n"
    "• Change anything when you ask in plain words: \"the batch number is MS-2609-018\", \"clear the equipment ID\", "
    "\"assign Dr. Priya Rao as investigator\", \"severity should be Major because …\", \"status to Open\", "
    "\"it was found yesterday\".\n"
    "• Check the report: \"what's missing?\", \"summarize\", \"why is it Major?\", \"what did you change?\", "
    "\"what is a risk score?\".\n"
    "• Undo, check the risk again, save or start over: \"undo\", \"reassess the risk\", \"save\", \"start over\".")


def _norm(message: str) -> str:
    return " ".join(re.sub(r"[^\w\s?'/-]", " ", message.lower()).split())


def detect(message: str, has_data: bool) -> Optional[str]:
    """Return a conversational intent, or None to let the log/edit router decide.

    Only short messages are considered: a long pasted report is never small talk.
    """
    m = _norm(message)
    if not m or len(message) > 240:
        return None
    words = m.split()

    if re.fullmatch(r"(hi|hello|hey|hii+|hai|good (morning|afternoon|evening)|namaste|vanakkam|yo|greetings)"
                    r"( there| team| copilot| aivoa)?[!. ]*", m):
        return "greeting"
    if re.fullmatch(r"(thanks|thank you|thankyou|thx|ty|great|awesome|perfect|nice|cool|good job|well done)"
                    r"( so much| a lot| copilot)?[!. ]*", m):
        return "thanks"
    if re.fullmatch(r"(ok|okay|k|fine|yes|yeah|yep|no|nope|sure|alright|got it|hmm+|done)[!. ]*", m):
        return "ack"
    if re.fullmatch(r"(undo|undo (that|it|this|the last (change|edit))|revert( that| it| the last (change|edit))?|"
                    r"go back|roll ?back|cancel (that|the last (change|edit)))[!. ]*", m):
        return "undo"
    # Save is a plain command: recognising it without the LLM means it still works when Groq is rate-limited.
    if re.fullmatch(r"(please )?(save|save it|save (this|the|my) (report|record|deviation|changes)|save changes|"
                    r"commit( it)?|submit( it)?)( please| now)?[!. ]*", m):
        return "save"
    if re.search(r"^(help|\?|menu|commands)$|what can you do|how (do|does) (this|it|you) work|who are you|"
                 r"what are you|how to use|what should i (do|type|say)|guide me|show (me )?(the )?commands", m):
        return "help"
    if re.search(r"\b(what'?s|what is|which (fields? )?(are|is)|anything|show|list)\b.*\b(missing|empty|blank|left|pending)\b|"
                 r"^missing( fields)?\??$|what else (do you need|is needed)", m):
        return "missing"
    if re.search(r"\b(what did you|what (was|has been|got)|show( me)?( the)?|list( the)?)\b.*\b(chang|updat|edit)\w*|"
                 r"^(changes|history|change log)\??$", m):
        return "changes"
    if re.search(r"^(summari[sz]e|summary|recap|overview|read (it|the form) back|show (me )?(the )?form|"
                 r"what do (you|we) have( so far)?|status of (the )?form|give me (a )?summary)\b", m):
        return "summary"
    if re.search(r"\b(why|explain|justify|reason|how come|how did you)\b.*\b(risk|severity|major|minor|critical|"
                 r"rpn|score|classif\w*|capa|due date|magnitude)\b|^explain( it)?\??$", m):
        return "explain"
    if _glossary_term(m) and re.search(r"\b(what|meaning|mean|define|definition|stand for|explain)\b", m):
        return "glossary"

    # Personal statements / chit-chat that mention nothing about the deviation or the form.
    # e.g. "I am staying in Salem", "my name is Surendar", "tell me a joke", "what's the weather".
    # Commands always go to the router (it gives the precise "not a field" / "invalid option" feedback).
    # Conversational openers ("actually", "sorry", "can you") often come before the verb.
    if re.match(r"^((please|pls|kindly|actually|sorry|oh|ah|oops|wait|hmm+|ok|okay|no|and|also|then|"
                r"can you|could you|would you|i want to|i'd like to|let's)\s+)*"
                r"(set|change|update|clear|remove|delete|assign|make|mark|correct|fix|replace|put|revert|restore|"
                r"save|submit|reset|start over|start again|new|discard|re-?assess|assess)\b", m):
        return None
    # "location is Block C" or "reporter was Ravi" name a form field, so they stay edits.
    if not DOMAIN_WORDS.search(m) and len(words) <= 30:
        from .operations import resolve_field  # local import avoids a cycle
        if resolve_field(m) is None:
            return "off_topic"
    return None


def pending_question(history: list[dict], message: str) -> Optional[tuple[str, str]]:
    """If the Copilot's last turn asked the user a question, return (original request, question).

    Short replies such as "reported by" only make sense together with that earlier turn, so the
    router must not judge them on their own (they would look like off-topic chit-chat).
    """
    turns = [t for t in (history or []) if str(t.get("content", "")).strip()]
    # The client sends the current message as the last history entry: drop it.
    if turns and turns[-1].get("role") == "user" and str(turns[-1]["content"]).strip() == message.strip():
        turns = turns[:-1]
    if len(turns) < 2 or turns[-1].get("role") != "assistant":
        return None
    lines = [ln.strip() for ln in str(turns[-1]["content"]).splitlines() if ln.strip()]
    question = next((ln for ln in reversed(lines) if ln.endswith("?")), None)
    if not question:
        return None
    request = next((str(t["content"]).strip() for t in reversed(turns[:-1]) if t.get("role") == "user"), None)
    return (request, question) if request else None


def _glossary_term(m: str) -> Optional[str]:
    for alias, key in _GLOSSARY_ALIASES.items():
        if alias in m:
            return key
    for key in GLOSSARY:
        if re.search(rf"\b{key}s?\b", m):
            return key
    return None


def looks_like_deviation(text: str, extracted: dict) -> tuple[bool, str]:
    """Guardrail before a text replaces the form: does it describe a real deviation?

    Rule: >= 2 core facts (product, batch, equipment, parameter, range, observed value, stage, category),
    or 1 core fact plus deviation vocabulary. Anything else is rejected with a helpful reason.
    """
    facts = [k for k in CORE_FACTS if extracted.get(k)]
    if len(facts) >= 2 or (facts and DEVIATION_WORDS.search(text or "")):
        return True, ""
    return False, ("That doesn't look like a deviation report, so I left the form unchanged. "
                   "A deviation needs at least what went wrong and where - e.g. the product or batch, the "
                   "equipment, and the parameter with its approved range and observed value. "
                   "Paste the full report/email or upload the document.")


# --------------------------------------------------------------------------- answers
def _label(key: str) -> str:
    return wording.label(key)


def _has_data(form: dict) -> bool:
    return any(form.get(k) not in (None, "") for k in TIER_A_KEYS)


def _no_form() -> str:
    return ("There's no deviation in the form yet. Paste the report or email, or upload a PDF or photo of it, "
            "and I'll fill in the form and check the risk.")


def answer(intent: str, message: str, form: dict, user_overrides: dict, history: list[dict]) -> str:
    has = _has_data(form)
    if intent == "greeting":
        return ("Hello! " + ("A report is open. Tell me what to change, or ask \"what's missing?\"."
                             if has else "Paste a report or email about a quality problem, or upload a PDF or photo, "
                                         "and I'll fill in the form for you."))
    if intent == "thanks":
        return "You're welcome! " + ("When you're happy with it, say \"save\" or click Save report."
                                     if has else "Send the next deviation whenever you're ready.")
    if intent == "ack":
        return ("Noted. " + ("You can keep editing, ask \"what's missing?\", or say \"save\"." if has
                             else "Paste or upload a report to begin."))
    if intent == "help":
        return HELP_TEXT
    if intent == "off_topic":
        return ("I can only help with reporting and reviewing quality problems, so I haven't changed anything in "
                "the form. Try pasting a report, or say \"help\" to see what I can do.")
    if intent == "glossary":
        term = _glossary_term(_norm(message))
        return GLOSSARY[term] if term else "I don't have a plain-language definition for that term yet."
    if intent == "undo":
        return "Reverting the last change…"  # the client restores its previous snapshot

    if not has:
        return _no_form()

    if intent == "missing":
        miss = missing_fields(form)
        admin = [k for k in ("assigned_investigator", "ha_notification_required", "customer_notification_required",
                             "quarantine_reference") if not form.get(k)]
        parts = []
        if miss:
            parts.append("Not in the report, please tell me: " + wording.labels(miss) + ".")
        else:
            parts.append("Everything the AI can take from a report is filled in.")
        if admin:
            parts.append("Still to be decided by a person: " + wording.labels(admin) +
                         ". Just tell me, e.g. \"assign Dr. Priya Rao as investigator\".")
        return "\n".join(parts)

    if intent == "summary":
        f = form
        lines = [f"**{f.get('title') or 'Untitled deviation'}**"]
        what = ", ".join(x for x in [f.get("product_name"), f.get("batch_number") and f"batch {f['batch_number']}",
                                     f.get("equipment_id"), f.get("manufacturing_stage")] if x)
        if what:
            lines.append(f"• What: {what}")
        if f.get("process_parameter") or f.get("observed_value"):
            lines.append(f"• Out of range: {f.get('process_parameter') or 'value'} was {f.get('observed_value') or '?'}, "
                         f"allowed {f.get('approved_range') or '?'}"
                         + (f" → {f['deviation_magnitude']}" if f.get("deviation_magnitude") else ""))
        if f.get("date_detected") or f.get("reported_by"):
            lines.append(f"• Found {f.get('date_detected') or '?'} by {f.get('reported_by') or '?'}")
        if f.get("severity_classification"):
            lines.append(f"• Risk: {f['severity_classification']} (risk score {f.get('rpn')}), corrective action needed: "
                         f"{f.get('capa_required')}, investigation deadline {f.get('investigation_due_date') or '?'}")
        if f.get("batch_disposition") or f.get("immediate_action"):
            lines.append(f"• Action taken: {f.get('batch_disposition') or f.get('immediate_action')}")
        lines.append(f"• Status: {f.get('status') or 'Draft'}"
                     + (f", investigator {f['assigned_investigator']}" if f.get("assigned_investigator") else ""))
        return "\n".join(lines)

    if intent == "explain":
        if not form.get("severity_classification"):
            return "The risk hasn't been checked yet. Say \"reassess the risk\"."
        s, o, d, rpn = (form.get(k) for k in ("severity_score", "occurrence_score", "detectability_score", "rpn"))
        cls = form["severity_classification"]
        ov = (user_overrides or {}).get("severity_classification")
        if ov:
            why = f"A person set the level to {cls}" + (f" (\"{ov.get('reason')}\")." if ov.get("reason") else ".")
        elif s and s >= 5 or (rpn or 0) >= 100:
            why = f"It is Critical because the severity is {s} (5 is the top) or the risk score is {rpn} (100 or more)."
        elif s and s >= 3 or (rpn or 0) >= 40:
            why = (f"It is Major because the severity is {s} (3 or more)"
                   + (f" and the risk score is {rpn} (40 or more)" if (rpn or 0) >= 40 else "") + ".")
        else:
            why = f"It is Minor because the severity is {s} (below 3) and the risk score is {rpn} (below 40)."
        parts = [f"Scores: severity {s} × likelihood {o} × hard to detect {d} = risk score (RPN) {rpn}. {why}"]
        if form.get("severity_reasoning"):
            parts.append(f"Why, according to the AI: {form['severity_reasoning']}")
        if form.get("deviation_magnitude"):
            parts.append(f"How far outside the limit: {form['deviation_magnitude']}.")
        parts.append(f"Corrective action (CAPA) needed: {form.get('capa_required')}. Investigation deadline: "
                     f"{form.get('investigation_due_date') or 'not set'} (Critical 15, Major 30, Minor 45 days).")
        parts.append("The AI gives the three scores; the severity level, risk score, corrective action and deadline "
                     "come from fixed rules.")
        return "\n".join(parts)

    if intent == "changes":
        for msg in reversed(history or []):
            if msg.get("role") == "assistant" and ("updated" in str(msg.get("content")) or
                                                   "cleared" in str(msg.get("content"))):
                return "Last change: " + str(msg["content"]).split("\n")[0]
        return "No changes by hand yet. All values came from the report, the AI risk check or the fixed rules."
    return HELP_TEXT
