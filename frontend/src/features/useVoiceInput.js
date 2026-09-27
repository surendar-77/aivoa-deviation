/**
 * Voice input for the Copilot composer.
 *
 * Normal mode: record with MediaRecorder and transcribe on the backend (Groq Whisper).
 * Mock mode (no Groq key): fall back to the browser's SpeechRecognition (Chrome / Edge).
 * Either way the result is handed to `onText` for the user to review - it is never sent automatically.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api";

export const MAX_SECONDS = 60;
// Peak loudness (0..1) below this for the whole recording = the microphone delivered silence.
const SILENCE_LEVEL = 0.03;
const SILENT_MIC =
  "Your microphone isn't picking up any sound. Click the microphone icon in Chrome's address bar to choose the right one, check it isn't muted, then try again.";

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
const EXT = { webm: "webm", ogg: "ogg", mp4: "m4a" };

function micError(err) {
  if (err?.name === "NotAllowedError" || err?.name === "SecurityError")
    return "Microphone access is blocked. Allow the microphone for this site in the browser's address bar, then try again.";
  if (err?.name === "NotFoundError") return "No microphone was found. Connect one and try again.";
  if (err?.name === "NotReadableError") return "The microphone is in use by another application.";
  return `Could not start recording: ${err?.message || err}`;
}

export function useVoiceInput({ onText, useBrowserRecognition }) {
  const [state, setState] = useState("idle"); // idle | recording | transcribing
  const [error, setError] = useState(null);
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0); // 0..1 input loudness, for the meter
  const r = useRef({});
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  const SpeechRecognition = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);
  const supported = useBrowserRecognition
    ? Boolean(SpeechRecognition)
    : Boolean(typeof navigator !== "undefined" && navigator.mediaDevices?.getUserMedia && window.MediaRecorder);

  /** Release the microphone, timers and audio graph. */
  const cleanup = useCallback(() => {
    const c = r.current;
    clearInterval(c.timer);
    cancelAnimationFrame(c.raf);
    c.stream?.getTracks().forEach((t) => t.stop());
    c.audioCtx?.close().catch(() => {});
    r.current = { cancelled: c.cancelled };
    setLevel(0);
  }, []);

  useEffect(() => () => { r.current.cancelled = true; r.current.recorder?.state === "recording" && r.current.recorder.stop(); r.current.recognition?.abort(); cleanup(); }, [cleanup]);

  const startTimer = () => {
    const started = Date.now();
    setElapsed(0);
    r.current.timer = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      setElapsed(s);
      if (s >= MAX_SECONDS) stop();
    }, 250);
  };

  const meter = (stream) => {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const audioCtx = new Ctx();
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 512;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    const buf = new Uint8Array(analyser.fftSize);
    const tick = () => {
      analyser.getByteTimeDomainData(buf);
      let peak = 0;
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      const lvl = Math.min(1, peak / 64);
      r.current.maxLevel = Math.max(r.current.maxLevel || 0, lvl);
      setLevel(lvl);
      r.current.raf = requestAnimationFrame(tick);
    };
    r.current.audioCtx = audioCtx;
    tick();
  };

  const startRecorder = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const mimeType = MIME_TYPES.find((t) => window.MediaRecorder.isTypeSupported?.(t)) || "";
    const recorder = new window.MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    const chunks = [];
    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.onstop = async () => {
      const cancelled = r.current.cancelled;
      const type = recorder.mimeType || mimeType || "audio/webm";
      // Only trust the meter if it actually ran (no AudioContext = no reading).
      const silent = r.current.audioCtx && (r.current.maxLevel || 0) < SILENCE_LEVEL;
      cleanup();
      if (cancelled) return setState("idle");
      if (silent) {
        setError(SILENT_MIC);
        return setState("idle");
      }
      setState("transcribing");
      try {
        const blob = new Blob(chunks, { type });
        const ext = EXT[type.split("/")[1]?.split(";")[0]] || "webm";
        const { text } = await api.transcribe(blob, `voice.${ext}`);
        onTextRef.current(text);
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setState("idle");
      }
    };
    Object.assign(r.current, { stream, recorder, cancelled: false, maxLevel: 0 });
    recorder.start();
    meter(stream);
  };

  const startRecognition = () => {
    const rec = new SpeechRecognition();
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.continuous = true;
    const parts = [];
    rec.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) parts.push(e.results[i][0].transcript);
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed") setError(micError({ name: "NotAllowedError" }));
      else if (e.error !== "aborted" && e.error !== "no-speech") setError(`Speech recognition error: ${e.error}`);
    };
    rec.onend = () => {
      const cancelled = r.current.cancelled;
      cleanup();
      setState("idle");
      const text = parts.join(" ").trim();
      if (!cancelled && text) onTextRef.current(text);
      else if (!cancelled && !text) setError((prev) => prev || "No speech was detected. Try again closer to the microphone.");
    };
    Object.assign(r.current, { recognition: rec, cancelled: false });
    rec.start();
  };

  const start = async () => {
    if (state !== "idle") return;
    setError(null);
    if (!supported) {
      setError(useBrowserRecognition
        ? "Voice input in mock mode needs Chrome or Edge. Add a GROQ_API_KEY to use it in any browser."
        : "This browser cannot record audio.");
      return;
    }
    try {
      if (useBrowserRecognition) startRecognition();
      else await startRecorder();
      setState("recording");
      startTimer();
    } catch (e) {
      cleanup();
      setState("idle");
      setError(micError(e));
    }
  };

  /** Finish recording and transcribe. */
  function stop() {
    const c = r.current;
    clearInterval(c.timer);
    if (c.recorder?.state === "recording") c.recorder.stop();
    else if (c.recognition) c.recognition.stop();
  }

  /** Discard the recording. */
  const cancel = () => {
    r.current.cancelled = true;
    stop();
  };

  return { state, error, clearError: () => setError(null), elapsed, level, supported, start, stop, cancel };
}
