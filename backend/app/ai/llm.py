"""Thin wrapper around Groq (via langchain-groq) that always returns parsed JSON.

Why a wrapper: every node needs the same behaviour - JSON mode, temperature 0,
tolerant parsing, ONE retry on bad JSON, and a readable error if Groq fails.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from ..config import settings


class LLMError(Exception):
    """User-facing message explaining why the AI call failed."""


@lru_cache(maxsize=2)
def _client(light: bool = False):
    """light=True for cheap calls (intent routing, Q&A). Reasoning models (gpt-oss) then think less,
    which roughly halves output tokens - important on Groq's free tier (~8k tokens/minute).
    Extraction, edits and risk scoring keep the model's default reasoning for accuracy."""
    from langchain_groq import ChatGroq
    from pydantic import SecretStr

    kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}}  # Groq JSON mode
    if light and "gpt-oss" in settings.GROQ_MODEL:
        kwargs["reasoning_effort"] = "low"
    return ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=SecretStr(settings.GROQ_API_KEY),
        temperature=0,
        max_retries=3,  # the Groq client waits for Retry-After on 429 before each retry
        timeout=90,
        model_kwargs=kwargs,
        stop_sequences=None,
    )


def parse_json(text: str) -> dict:
    """Parse JSON even if wrapped in ``` fences or surrounded by prose."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise json.JSONDecodeError("top-level JSON is not an object", text, 0)
    return data


def _friendly(exc: Exception) -> str:
    msg = str(exc)
    low = msg.lower()
    if "401" in msg or "invalid api key" in low or "authentication" in low:
        return "Groq rejected the API key (401). Check GROQ_API_KEY in backend/.env."
    if "429" in msg or "rate limit" in low:
        return "Groq rate limit reached (429). Wait a few seconds and try again."
    if "timeout" in low or "timed out" in low:
        return "The Groq request timed out. Please try again."
    if "connect" in low:
        return "Could not reach the Groq API (network error)."
    return f"Groq call failed: {msg[:300]}"


def call_json(system: str, user: str, light: bool = False) -> dict:
    """Call the LLM and return a dict. Retries once if the output is not valid JSON."""
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    for attempt in range(2):
        try:
            response = _client(light).invoke(messages)
        except Exception as exc:  # network / auth / rate-limit
            raise LLMError(_friendly(exc)) from exc
        try:
            content = response.content
            return parse_json(content if isinstance(content, str) else "")  # non-text reply -> retry
        except (json.JSONDecodeError, TypeError):
            if attempt == 0:
                messages += [response, HumanMessage(
                    content="That was not valid JSON. Reply again with ONLY the JSON object.")]
    raise LLMError("The AI returned invalid JSON twice. Please rephrase and try again.")
