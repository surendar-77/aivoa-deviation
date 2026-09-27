# 🏗️ Architecture

> [!NOTE]
> Diagrams are written in Mermaid, which GitHub renders them automatically. Click a diagram to zoom or pan.

**Contents:** [Context](#1-system-context) · [Containers](#2-containers) · [Backend modules](#3-backend-modules) ·
[Request lifecycle](#4-request-lifecycle) · [Data model](#5-data-model) · [Record states](#6-record-lifecycle) ·
[Frontend](#7-frontend) · [Deployment](#8-deployment) · [Decisions](#9-key-decisions)

---

## 1. System context

```mermaid
flowchart TB
    QA["🧑‍🔬 QA officer / supervisor"]
    AUD["🕵️ Auditor"]
    SYS["🖥️ AIVOA Deviation Intake"]
    GROQ["☁️ Groq API<br/>LLM + Whisper"]
    QA -- "report, chat, voice" --> SYS
    SYS -- "form, risk, replies" --> QA
    AUD -- "history, print" --> SYS
    SYS -- "prompts, audio" --> GROQ
```

## 2. Containers

```mermaid
flowchart LR
    subgraph Browser
        R["React 18 SPA<br/>Redux Toolkit · Axios"]
    end
    subgraph Docker["Docker Compose (private network)"]
        N["frontend<br/>nginx 1.27<br/>static files + /api proxy"]
        B["backend<br/>FastAPI · LangGraph<br/>Tesseract · Poppler"]
        D[("db<br/>PostgreSQL 16")]
    end
    G["Groq"]
    R -->|"HTTP 127.0.0.1:8080"| N
    N -->|"/api → :8000"| B
    B -->|"SQLAlchemy"| D
    B -->|"HTTPS"| G
```

| Container | Image | Published | Health check |
|---|---|---|---|
| `frontend` | node:20-slim build → nginx:1.27-alpine | `127.0.0.1:8080` | Waits for the backend to be healthy |
| `backend` | python:3.11-slim + tesseract-ocr + poppler-utils | none | `GET /api/health` |
| `db` | postgres:16-alpine | none | `pg_isready` |

## 3. Backend modules

```mermaid
flowchart TB
    main["main.py<br/>endpoints"] --> agent["ai/graph.py<br/>LangGraph"]
    main --> crud["crud.py"]
    main --> speech["ai/speech.py"]
    agent --> tools["ai/tools.py"]
    agent --> conv["ai/conversation.py"]
    agent --> rules["rules.py"]
    tools --> reader["reader.py"]
    tools --> llm["ai/llm.py"]
    tools --> ops["ai/operations.py"]
    tools --> prompts["ai/prompts.py"]
    llm -.->|no key| mock["ai/mock.py"]
    ops --> fields["fields.py<br/>REGISTRY"]
    rules --> fields
    crud --> models["models.py"] --> fields
    agent --> wording["ai/wording.py"]

    style fields fill:#fef7c3,stroke:#eab308
```

`fields.py` is the **single source of truth**. The form layout, the AI prompts, validation, the database columns
and `db/schema.sql` are all derived from it. Adding a field there adds it everywhere.

## 4. Request lifecycle

```mermaid
sequenceDiagram
    autonumber
    participant UI as Browser
    participant NG as nginx
    participant API as FastAPI
    participant RD as reader.py
    participant AG as LangGraph
    participant LLM as Groq
    participant RL as rules.py

    UI->>NG: POST /api/ai/chat (multipart + scan.jpg)
    NG->>API: proxy (180 s timeout, 20 MB)
    API->>AG: run_agent(message, file, form, history, overrides)
    AG->>RD: read_document()
    RD-->>AG: text + "image OCR (Tesseract)"
    AG->>AG: relevance gate (≥ 2 deviation facts)
    AG->>LLM: router (JSON mode, T=0)
    LLM-->>AG: intent = log
    AG->>LLM: extract Tier-A fields
    AG->>LLM: assess S / O / D + reasoning
    AG->>RL: RPN · level · CAPA · due date · magnitude · repeat
    AG-->>API: {intent, reply, form, changes[], missing_fields}
    API-->>UI: 200 JSON
```

<details>
<summary><b>Error paths</b></summary>

| Failure | Behaviour |
|---|---|
| Unsupported / empty file | 422 with a plain message shown in chat |
| No text found (blank scan) | "No readable text was found in the document." |
| LLM rate limit / timeout | One retry, then a friendly chat message; the form is untouched |
| Invalid LLM JSON | One retry with a stricter instruction |
| No Groq key | Mock mode for chat; browser speech recognition for voice |
| Silent voice clip | Rejected before or after transcription with microphone guidance |

</details>

## 5. Data model

```mermaid
erDiagram
    deviations ||--o{ deviation_audit : "has history"
    deviation_sequence ||..o{ deviations : "numbers per year"

    deviations {
        int id PK
        varchar deviation_id UK "DEV-YYYY-NNNN"
        varchar title
        date date_detected
        varchar batch_number
        varchar equipment_id
        varchar observed_value
        varchar approved_range
        int severity_score "1-5"
        int occurrence_score "1-5"
        int detection_score "1-5"
        int rpn "S x O x D"
        varchar severity_classification "Critical/Major/Minor"
        varchar capa_required
        date investigation_due_date
        varchar status
        json user_overrides
        timestamptz created_at
        timestamptz last_updated_at
    }
    deviation_audit {
        int id PK
        varchar deviation_id FK
        varchar field
        text old_value
        text new_value
        varchar source "AI-extracted | AI-computed | User instruction | System"
        text instruction "chat message"
        varchar changed_by
        timestamptz changed_at
    }
    deviation_sequence {
        int year PK
        int last_number
    }
```

<sub>`deviations` has one column per registry field (≈ 45); only representative columns are shown.</sub>

**ID generation.** `deviation_sequence` is locked with `SELECT … FOR UPDATE`, so IDs are unique under
concurrency and never reused after a delete.

## 6. Record lifecycle

```mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> Draft: log (paste / upload / voice)
    Draft --> Draft: edit in chat / undo
    Draft --> Saved: save → DEV-YYYY-NNNN
    Saved --> Editing: load from Saved reports
    Editing --> Editing: edit in chat
    Editing --> Saved: save (audit rows appended)
    Saved --> [*]: delete (history cascades)
    Draft --> Empty: new deviation
```

Workflow `status` (shown in the stepper): **Draft → Open → Under Investigation → Pending QA Approval → Closed**.

## 7. Frontend

```mermaid
flowchart TB
    App["App.jsx<br/>SidebarProvider · split view · commit bar"]
    App --> SB["AppSidebar"]
    App --> RH["RecordHeader<br/>KPIs · stepper · section nav"]
    App --> DF["DeviationForm<br/>read-only fields"]
    App --> RC["RiskCard<br/>FMEA · 5×5 matrix"]
    App --> CP["AICopilotPanel<br/>feed · diff · voice · chips"]
    App --> DL["DeviationList<br/>drawer · history modal"]
    App --> PR["PrintReport<br/>A4 portal"]
    CP --> IS["IntakeStart"]
    CP --> VH["useVoiceInput"]
    Store[("Redux<br/>deviationSlice")]
    DF & RC & CP & RH & DL --- Store
```

<details>
<summary><b>Redux state shape</b></summary>

```js
{
  registry,                      // field definitions from GET /api/fields
  form: { [key]: value },        // current record
  userOverrides: { [key]: { value, reason } },
  changeLog: Change[],           // unsaved changes, sent with save
  messages: ChatMessage[],       // copilot feed (also the history for memory)
  highlight: { fields, token },  // drives the flash animation
  past: Snapshot[],              // undo stack
  copilotStatus,                 // idle | working | done
  currentId, dirty, savedList, audit,
  loading, saving, error, notice, mockMode, model
}
```

</details>

## 8. Deployment

```mermaid
flowchart LR
    subgraph Host["Host machine"]
        L["127.0.0.1:8080"]
        subgraph Net["compose network (internal)"]
            F[frontend:80] --> BK[backend:8000] --> DB[(db:5432)]
        end
        L --> F
        V[("volume<br/>pgdata")] --- DB
        E1[".env<br/>POSTGRES_PASSWORD"] -.-> DB
        E2["backend/.env<br/>GROQ_API_KEY"] -.-> BK
    end
```

| Setting | Where | Default |
|---|---|---|
| `POSTGRES_PASSWORD` | root `.env` (required) | none |
| `APP_PORT` | root `.env` | `8080` |
| `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_WHISPER_MODEL` | `backend/.env` | Mock mode · `openai/gpt-oss-120b` · `whisper-large-v3-turbo` |
| `CORS_ORIGINS` | compose env | `http://localhost:8080` |

## 9. Key decisions

| # | Decision | Why | Trade-off |
|---|---|---|---|
| 1 | **Read-only form, chat-only edits** | Every change gets a source and an instruction for the audit trail | Less direct than typing in a field |
| 2 | **Rules in Python, not the LLM** | Reproducible, testable, explainable risk | Rules need code changes to tune |
| 3 | **Field registry drives everything** | The UI, AI, DB and validation can never disagree | One more abstraction to learn |
| 4 | **Deterministic conversation layer first** | Greetings, help and guardrails work without the LLM and cannot hallucinate | Keyword lists need upkeep |
| 5 | **LangGraph over a single prompt** | Explicit, inspectable steps; conditional re-assessment | More moving parts |
| 6 | **Same-origin `/api` via nginx** | One URL, no CORS in production | nginx config to maintain |
| 7 | **Transcript never auto-sent** | A misheard batch number must be caught by a person | One extra click |
