"""Voice input: turn a short recording into text with Groq-hosted Whisper.

Why only transcription (no voice replies): in a GMP record a misheard batch number is a
data-integrity error, so the transcript goes back to the chat box for the user to check
before it is sent. The spoken words never change the form directly.
"""
from __future__ import annotations

import re
from functools import lru_cache

from ..config import settings

# Whisper uses the prompt as spelling context: domain terms it would otherwise mishear.
VOCABULARY_PROMPT = (
    "Pharmaceutical API manufacturing deviation. Terms: batch, lot, reactor R-201, centrifuge, "
    "fluid-bed dryer, crystallization, LOD, NMT, NLT, degrees Celsius, rpm, out of specification, "
    "OOS, CAPA, RPN, GMP, SOP, quarantine, QA investigation, Metoprolol Succinate. "
    "Batch numbers are written like MS-2609-017 or AC-2609-042; equipment IDs like R-201, CF-102, FBD-305; "
    "values like 72 °C, 750 rpm, 1.2 %."
)
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # ~10 min of compressed speech; Groq's own limit is 25 MB
MIN_AUDIO_BYTES = 1024              # anything smaller is a click, not speech

# Spoken units -> the notation used in records, so voice and typed input read the same.
UNIT_FIXES = [
    (re.compile(r"\s*(?:°\s*|degrees?\s+)(?:celsius|centigrade|c)(?![a-z])", re.I), " °C"),
    (re.compile(r"\s*per\s*cent(?![a-z])", re.I), " %"),
]


# Whisper "hears" these stock phrases in silence or hum (a muted / wrong microphone). Returned alone,
# they are almost never what the user said, so they are rejected instead of being put in the chat box.
HALLUCINATIONS = {
    "thank you", "thank you very much", "thanks", "thanks for watching", "thank you for watching",
    "thank you so much", "bye", "you", "okay", "ok", "so", "please subscribe", "subtitles by the amara.org community",
}
NO_SPEECH_PROB = 0.6  # Whisper's own per-segment "this was silence" probability
SILENT_MIC = ("I couldn't hear any speech: the recording was silent. Check that the right microphone is selected "
              "(click the microphone icon in Chrome's address bar) and that it isn't muted, then try again.")


def is_hallucination(text: str, segments: list | None = None) -> bool:
    """True when the transcript is Whisper filling silence rather than real speech."""
    phrase = re.sub(r"[^a-z. ]", "", text.lower()).strip(" .")
    if phrase in HALLUCINATIONS:
        return True
    probs = [_seg(s, "no_speech_prob") for s in (segments or [])]
    probs = [p for p in probs if p is not None]
    return bool(probs) and min(probs) >= NO_SPEECH_PROB


def _seg(segment, key):
    return segment.get(key) if isinstance(segment, dict) else getattr(segment, key, None)


def normalize_units(text: str) -> str:
    """'72 degrees Celsius' -> '72 °C', '1.2 percent' -> '1.2 %'."""
    for pattern, repl in UNIT_FIXES:
        text = pattern.sub(repl, text)
    return text


class SpeechError(Exception):
    """User-facing reason a transcription failed."""


@lru_cache(maxsize=1)
def _client():
    from groq import Groq

    return Groq(api_key=settings.GROQ_API_KEY, timeout=60, max_retries=2)


def transcribe(audio: bytes, filename: str) -> str:
    """Return the transcript, or raise SpeechError with a message the UI can show as-is."""
    if len(audio) < MIN_AUDIO_BYTES:
        raise SpeechError("The recording was too short. Speak for a moment longer before pressing Done.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise SpeechError("The recording is too long (max 10 MB). Record a shorter message.")
    try:
        result = _client().audio.transcriptions.create(
            file=(filename or "voice.webm", audio),
            model=settings.GROQ_WHISPER_MODEL,
            prompt=VOCABULARY_PROMPT,
            language="en",
            temperature=0,
            response_format="verbose_json",  # includes per-segment no_speech_prob
        )
    except Exception as exc:  # groq.APIError, network errors ...
        raise SpeechError(f"Transcription failed ({type(exc).__name__}): {str(exc)[:160]}") from exc
    text = (getattr(result, "text", "") or "").strip()
    if not text:
        raise SpeechError("No speech was detected in the recording. Try again closer to the microphone.")
    if is_hallucination(text, getattr(result, "segments", None)):
        raise SpeechError(SILENT_MIC)
    return normalize_units(text)
