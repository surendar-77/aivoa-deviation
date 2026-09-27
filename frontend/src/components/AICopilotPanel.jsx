/**
 * AIVOA Copilot: the ONLY way to fill or change the form.
 * Rendered as an activity feed (not chat bubbles): every agent turn is an entry that says what
 * happened, which tools ran and exactly which fields changed - the same facts that reach the audit trail.
 */
import { fieldLabel, methodLabel, sourceLabel, TOOL_LABELS } from "../plainLanguage";
import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { fileKind, sendChat, undo } from "../features/deviationSlice";
import IntakeStart, { COMPOSE_EVENT } from "./IntakeStart";
import { MAX_SECONDS, useVoiceInput } from "../features/useVoiceInput";
import {
  AlertIcon, CheckIcon, FileIcon, FlaskIcon, ImageIcon, MailIcon, MicIcon, PaperclipIcon, SearchIcon, ShieldIcon,
  UploadIcon, XIcon, ZapIcon,
} from "./Icons";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.txt,.eml";
const ALLOWED = /\.(pdf|jpe?g|png|txt|eml)$/i;
const DIFF_PREVIEW = 5;

function fmt(v) {
  if (v === null || v === undefined || v === "") return "empty";
  const s = String(v);
  return s.length > 48 ? s.slice(0, 45) + "…" : s;
}

const time = (at) => (at ? new Date(at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "");

/** Minimal formatting for AI replies: **bold** only (everything else stays plain text, no HTML injection). */
function RichText({ text }) {
  return String(text).split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <b key={i}>{part.slice(2, -2)}</b> : part);
}

function FileCard({ file }) {
  const kind = file.kind.includes("Image") ? "img" : file.kind.includes("Email") ? "mail" : "";
  return (
    <div className="attachment">
      <span className={`attachment-icon ${kind}`}>
        {kind === "img" ? <ImageIcon size={16} /> : kind === "mail" ? <MailIcon size={16} /> : <FileIcon size={16} />}
      </span>
      <div className="attachment-text">
        <div className="attachment-name">{file.name}</div>
        <div className="attachment-kind">{file.kind}</div>
      </div>
    </div>
  );
}

/** What kind of event an agent reply is: drives the entry title, icon and accent. */
function describe(meta) {
  const tools = meta.toolsUsed || [];
  if (meta.isError) return { title: "Request failed", tone: "err", Icon: AlertIcon };
  if (meta.icon === "guard") return { title: "Not something I can do", tone: "guard", Icon: ShieldIcon };
  if (tools.includes("log_interaction_tool")) return { title: "Report filled in", tone: "ok", Icon: CheckIcon };
  if (tools.includes("edit_interaction_tool") && meta.changes?.length) return { title: "Report updated", tone: "ok", Icon: CheckIcon };
  if (meta.changes?.length) return { title: "Report updated", tone: "ok", Icon: CheckIcon };
  if (meta.icon === "success") return { title: "Done", tone: "ok", Icon: CheckIcon };
  return { title: "Assistant", tone: "info", Icon: ZapIcon };
}

function Diff({ changes, labels }) {
  const [all, setAll] = useState(false);
  const rows = all ? changes : changes.slice(0, DIFF_PREVIEW);
  return (
    <div className="diff">
      <div className="diff-head">
        <span>{changes.length} field{changes.length > 1 ? "s" : ""} changed</span>
      </div>
      {rows.map((c) => (
        <div className="diff-row" key={c.field} title={c.instruction || c.source}>
          <span className="diff-field">{labels[c.field] || c.field}</span>
          <span className="diff-vals">
            {c.old !== null && c.old !== undefined && c.old !== "" && <s>{fmt(c.old)}</s>}
            <span className="diff-new">{fmt(c.new)}</span>
          </span>
          <span className="diff-src">{sourceLabel(c.source)}</span>
        </div>
      ))}
      {changes.length > DIFF_PREVIEW && (
        <button className="diff-more" onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${changes.length}`}
        </button>
      )}
    </div>
  );
}

const LONG = 320;

/** Pasted e-mails can be pages long: show the start and let the user expand. */
function UserText({ text }) {
  const [open, setOpen] = useState(false);
  const long = text.length > LONG;
  return (
    <div className="user-text">
      {long && !open ? text.slice(0, LONG).trimEnd() + "…" : text}
      {long && (
        <button className="link-btn" onClick={() => setOpen(!open)}>
          {open ? "Show less" : `Show full text (${text.length.toLocaleString()} chars)`}
        </button>
      )}
    </div>
  );
}

function Message({ m, labels }) {
  const meta = m.meta || {};
  if (m.role === "user") {
    return (
      <div className="entry entry-user">
        <div className="entry-head">
          <span className="who">You</span>
          <time>{time(m.at)}</time>
        </div>
        {m.file && <FileCard file={m.file} />}
        {m.content && <UserText text={m.content} />}
      </div>
    );
  }
  const { title, tone, Icon } = describe(meta);
  return (
    <div className={`entry entry-ai tone-${tone}`}>
      <span className="entry-icon"><Icon size={13} strokeWidth={2.4} /></span>
      <div className="entry-main">
        <div className="entry-head">
          <span className="who">{title}</span>
          <time>{time(m.at)}</time>
        </div>
        {(meta.extractionMethod || meta.toolsUsed?.length > 0) && (
          <div className="tools">
            {meta.extractionMethod && <span className="tool method" title={meta.extractionMethod}><SearchIcon size={11} /> {methodLabel(meta.extractionMethod)}</span>}
            {meta.toolsUsed?.map((t) => (
              <span key={t} className="tool" title={t}>
                {/* the edit tool can run without changing anything (e.g. a refused request) */}
                {t === "edit_interaction_tool" && !meta.changes?.length ? "Checked your request" : TOOL_LABELS[t] || t}
              </span>
            ))}
          </div>
        )}
        <div className="entry-text"><RichText text={m.content} /></div>
        {meta.changes?.length > 0 && <Diff changes={meta.changes} labels={labels} />}
        {meta.preview && (
          <details className="preview">
            <summary>Show the text read from the document</summary>
            <pre>{meta.preview}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

/** Seconds since mount - used to explain long waits (Groq free tier rate limit retries). */
function useElapsed() {
  const [s, setS] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setS((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, []);
  return s;
}

const SLOW_NOTE = "This is taking longer than usual. The AI service may be rate-limiting; the request retries automatically.";

/** While the agent works: what it is doing (not a fake percentage), plus elapsed time for long waits. */
function Working({ file }) {
  const elapsed = useElapsed();
  const read = file
    ? file.kind === "PDF Document" ? "Extracting text from the PDF (OCR for scanned pages)"
      : file.kind.includes("Image") ? "Extracting text from the image with OCR"
      : "Reading the document"
    : null;
  return (
    <div className="entry entry-ai tone-info working" role="status">
      <span className="entry-icon"><span className="spinner" aria-hidden="true" /></span>
      <div className="entry-main">
        <div className="entry-head">
          <span className="who">Working on it</span>
          <span className="typing-dots" aria-hidden="true"><i /><i /><i /></span>
          <time>{elapsed}s</time>
        </div>
        <p className="entry-text">
          {read ? `${read}, then filling in the form and checking the risk.` : "Reading your message and updating the report."}
        </p>
        <div className="progress" aria-hidden="true"><span /></div>
        {elapsed >= 12 && <div className="slow-note">{SLOW_NOTE}</div>}
      </div>
    </div>
  );
}

const CAPABILITIES = [
  { Icon: FileIcon, title: "Read any report", text: "Emails, PDFs, scanned pages and photos of paper forms." },
  { Icon: ShieldIcon, title: "Check the risk", text: "Rates how serious, how likely and how hard to spot the problem is, then applies fixed rules." },
  { Icon: CheckIcon, title: "Make changes when asked", text: "Just say it: “change the batch number to MS-2609-018”." },
  { Icon: SearchIcon, title: "Explain its decisions", text: "Ask “why is it Major?” or “what's missing?”." },
];

function Capabilities() {
  return (
    <ul className="capabilities" aria-label="What the Copilot can do">
      {CAPABILITIES.map(({ Icon, title, text }) => (
        <li key={title}>
          <span className="cap-icon"><Icon size={15} /></span>
          <span><b>{title}</b><span>{text}</span></span>
        </li>
      ))}
    </ul>
  );
}

/** Next-step suggestions that depend on where the user is in the workflow. */
function suggestions({ hasForm, canUndo, committed }) {
  // [label shown, message sent]: plain questions, but the terms the Copilot's glossary recognises.
  if (!hasForm) return [["What can you do?", "What can you do?"], ["What is a risk score?", "What is RPN?"],
                        ["What is corrective action?", "What is CAPA?"]];
  const list = [["What's missing?", "What's missing?"], ["Why this risk level?", "Explain the risk"], ["Summarize", "Summarize"]];
  if (canUndo) list.push(["Undo", "Undo"]);
  if (!committed) list.push(["Save", "Save"]);
  return list;
}

export default function AICopilotPanel() {
  const dispatch = useDispatch();
  const { messages, loading, saving, registry, copilotStatus, form, past, currentId, dirty, mockMode } = useSelector((s) => s.deviation);
  // A chat turn during a commit would race the save response, so the composer locks for both.
  const busy = loading || saving;
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [pendingFile, setPendingFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const [dropError, setDropError] = useState(null);
  const fileRef = useRef(null);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const [voiceNote, setVoiceNote] = useState(false);
  // Voice: the transcript is appended to the box for review, never sent automatically.
  const voice = useVoiceInput({
    useBrowserRecognition: mockMode,
    onText: (t) => {
      setText((prev) => (prev.trim() ? `${prev.trim()} ${t}` : t));
      setVoiceNote(true);
      setTimeout(() => inputRef.current?.focus(), 0);
    },
  });
  const voiceBusy = voice.state !== "idle";
  const labels = Object.fromEntries((registry?.fields || []).map((f) => [f.key, fieldLabel(f.key, f.label)]));
  const hasForm = Object.values(form).some((v) => v !== null && v !== "");
  const chips = suggestions({ hasForm, canUndo: past.length > 0, committed: currentId && !dirty });

  // Block body on purpose: newer Chrome returns a Promise from scrollIntoView, and an effect
  // must return nothing (or a cleanup function) or React unmounts the whole tree.
  useEffect(() => {
    // With only the welcome message, stay at the top so it reads welcome → start card → capabilities.
    if (messages.length <= 1 && !loading) return;
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  // "New deviation" in the sidebar asks the Copilot to focus its message box.
  useEffect(() => {
    const onCompose = () => setTimeout(() => inputRef.current?.focus(), 0);
    window.addEventListener(COMPOSE_EVENT, onCompose);
    return () => window.removeEventListener(COMPOSE_EVENT, onCompose);
  }, []);

  const submit = (message, attachment) => {
    if (busy || voiceBusy || (!message.trim() && !attachment)) return;
    setPendingFile(attachment ? { name: attachment.name, kind: fileKind(attachment.name) } : null);
    dispatch(sendChat({ message: message.trim(), file: attachment }));
  };

  const send = () => {
    if (voiceBusy || (!text.trim() && !file)) return;
    submit(text, file);
    setVoiceNote(false);
    setText("");
    setFile(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const pick = (f) => {
    if (!f || busy) return;
    if (!ALLOWED.test(f.name)) {
      setDropError(`${f.name}: unsupported type. Use PDF, JPG/JPEG, PNG, TXT or EML.`);
      return;
    }
    setDropError(null);
    setFile(f);
    inputRef.current?.focus();
  };

  const onChip = (chip) => {
    if (chip === "Undo") dispatch(undo());
    else submit(chip, null);
  };

  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  // Drag-and-drop: dragleave also fires when moving over children, so only reset when leaving the panel.
  const onDragOver = (e) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    setDragging(true);
  };
  const onDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false);
  };
  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    pick(e.dataTransfer.files?.[0]);
  };

  return (
    <aside className={`copilot ${dragging ? "dragging" : ""}`} onDragOver={onDragOver} onDragLeave={onDragLeave} onDrop={onDrop}
           aria-label="AIVOA Copilot">
      <header className="copilot-head">
        <span className="copilot-mark"><FlaskIcon size={16} /></span>
        <div className="copilot-titles">
          <h2>AIVOA Copilot</h2>
          <p>Your AI assistant. Upload a report or type a request.</p>
        </div>
        <span className={`copilot-status ${copilotStatus}`} role="status">
          <i />{{ working: "Working", done: "Done", idle: "Ready" }[copilotStatus] || "Ready"}
        </span>
      </header>

      <div className="feed">
        {messages.map((m, i) => <Message key={i} m={m} labels={labels} />)}
        {!hasForm && !busy && (
          <IntakeStart onUpload={() => fileRef.current?.click()} onPaste={() => inputRef.current?.focus()} />
        )}
        {messages.length === 1 && !busy && <Capabilities />}
        {loading && <Working file={pendingFile} />}
        <div ref={endRef} />
      </div>

      {dragging && (
        <div className="drop-overlay">
          <div className="drop-card">
            <UploadIcon size={26} />
            <b>Drop to extract</b>
            <span>PDF · JPG/PNG · EML · TXT</span>
          </div>
        </div>
      )}

      <div className="composer-wrap">
        {!busy && (
          <div className="suggestions" role="list" aria-label="Suggestions">
            {chips.map(([label, message], i) => (
              <button key={label} className="suggestion" onClick={() => onChip(message)} role="listitem"
                      style={{ "--i": i }}>{label}</button>
            ))}
          </div>
        )}
        {dropError && <div className="drop-error" onClick={() => setDropError(null)}>{dropError}</div>}
        {voice.error && <div className="drop-error" role="alert" onClick={voice.clearError}>{voice.error}</div>}
        <div className={`composer ${busy ? "busy" : ""}`}>
          {file && (
            <div className="attach-chip">
              <PaperclipIcon size={13} /> <span>{file.name}</span>
              <button onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ""; }} aria-label="Remove file">
                <XIcon size={12} />
              </button>
            </div>
          )}
          <textarea
            ref={inputRef}
            rows={2}
            placeholder={saving ? "Committing to the QMS ledger…" : "Type a message or paste a deviation..."}
            value={text}
            onChange={(e) => { setText(e.target.value); if (!e.target.value.trim()) setVoiceNote(false); }}
            onKeyDown={onKey}
            disabled={busy}
            aria-label="Message the Copilot"
          />
          {voice.state === "recording" && (
            <div className="voice-strip" role="status">
              <span className="rec-dot" aria-hidden="true" />
              <span className="voice-label">Listening</span>
              <span className={`voice-level ${mockMode ? "pulse" : ""}`} aria-hidden="true">
                {[0.5, 0.8, 1, 0.8, 0.5].map((f, i) => (
                  <i key={i} style={{ height: `${4 + voice.level * 14 * f}px` }} />
                ))}
              </span>
              <time className="voice-time">
                {Math.floor(voice.elapsed / 60)}:{String(voice.elapsed % 60).padStart(2, "0")} / {MAX_SECONDS / 60}:00
              </time>
              <button className="btn btn-ghost btn-sm" onClick={voice.cancel}>Cancel</button>
              <button className="btn btn-primary btn-sm" onClick={voice.stop}><CheckIcon size={14} strokeWidth={2.6} /> Done</button>
            </div>
          )}
          {voice.state === "transcribing" && (
            <div className="voice-strip" role="status">
              <span className="spinner" aria-hidden="true" /> <span className="voice-label">Transcribing your recording…</span>
            </div>
          )}
          <div className="composer-bar">
            <input ref={fileRef} type="file" accept={ACCEPT} hidden onChange={(e) => pick(e.target.files[0] || null)} />
            <button className="btn btn-ghost btn-sm" title="Upload PDF, JPG/JPEG, PNG, TXT or EML" aria-label="Attach file"
                    onClick={() => fileRef.current.click()} disabled={busy}>
              <PaperclipIcon size={15} /> Attach
            </button>
            <button className={`btn btn-ghost btn-sm ${voice.state === "recording" ? "rec" : ""}`}
                    onClick={voice.state === "recording" ? voice.stop : voice.start}
                    disabled={busy || voice.state === "transcribing"}
                    aria-pressed={voice.state === "recording"}
                    title={mockMode ? "Dictate with the browser's speech recognition (mock mode)" : "Dictate a message (transcribed with Whisper; you review it before sending)"}>
              <MicIcon size={15} /> {voice.state === "recording" ? "Stop" : "Voice"}
            </button>
            <button className={`send-btn ${text.trim() || file ? "ready" : ""}`} onClick={send}
                    disabled={busy || voiceBusy || (!text.trim() && !file)} title="Send (Enter)" aria-label="Send">
              {loading ? <span className="btn-spinner light" aria-hidden="true" /> : <CheckIcon size={16} strokeWidth={2.6} />}
            </button>
          </div>
        </div>
        {voiceNote && text.trim() && (
          <p className="voice-note">Transcribed from voice. Check names, batch numbers and values before sending.</p>
        )}
      </div>
    </aside>
  );
}
