# 🎨 Design System

A calm, neutral, enterprise QMS look. Colour is reserved for **meaning** (risk level, source of a value, status),
never for decoration.

| Principle | In practice |
|---|---|
| **Trust through provenance** | Every value shows where it came from: report, calculated, or person |
| **Calm by default** | Neutral surfaces with black/white primary; colour only for status |
| **Motion answers actions** | Animations confirm what just changed; nothing loops for decoration |
| **Plain language** | "Risk score", not "RPN"; "From the report", not "Tier A" |

Sources: [`frontend/src/index.css`](frontend/src/index.css) (theme variables) ·
[`frontend/src/styles.css`](frontend/src/styles.css) (app tokens and components).

---

## 1. Token architecture

```mermaid
flowchart LR
    T1["Theme variables<br/>--background · --foreground<br/>--primary · --muted · --border"] --> T2["App aliases<br/>--brand · --line · --field-filled<br/>--risk-bg · --focus-ring"]
    T2 --> C["Components<br/>.card · .field · .btn · .chip"]
    S["Semantic palette<br/>--ok · --warn · --err<br/>--info · --purple · --sev-*"] --> C
    D["[data-theme=dark]"] -.->|redefines| T1
    D -.->|redefines| S
```

Themes switch by setting `data-theme="light" | "dark"` on `<html>`. The default is **light**, and the choice is
remembered per browser.

## 2. Colour

### Neutrals (OKLCH)

| Token | Light | Use |
|---|---|---|
| `--background` | `oklch(1 0 0)` | Page, cards |
| `--foreground` | `oklch(0.145 0 0)` | Body text |
| `--primary` | `oklch(0.205 0 0)` | Primary buttons, active items |
| `--muted` | `oklch(0.97 0 0)` | Subtle fills, empty fields |
| `--muted-foreground` | `oklch(0.556 0 0)` | Secondary text |
| `--border` | `oklch(0.922 0 0)` | Hairlines, card borders |
| `--destructive` | `oklch(0.577 0.245 27.3)` | Delete actions |

### Semantic

| | Token | Light | Dark | Meaning |
|---|---|---|---|---|
| ![](https://img.shields.io/badge/-%20%20%20%20-067647) | `--ok` | `#067647` | `#4ecb8d` | Saved, Minor, complete |
| ![](https://img.shields.io/badge/-%20%20%20%20-a4400a) | `--warn` | `#a4400a` | `#f8b545` | Unsaved changes, due soon |
| ![](https://img.shields.io/badge/-%20%20%20%20-b42318) | `--err` | `#b42318` | `#f97a70` | Errors, Critical |
| ![](https://img.shields.io/badge/-%20%20%20%20-175cd3) | `--info` | `#175cd3` | `#6cbcfd` | From the report (Tier A) |
| ![](https://img.shields.io/badge/-%20%20%20%20-6941c6) | `--purple` | `#6941c6` | `#bd9cf7` | Calculated (Tier B) |
| ![](https://img.shields.io/badge/-%20%20%20%20-eab308) | `--flash-border` | `#eab308` | amber 65 % | Just changed |

Each semantic colour has `-bg` and `-border` companions for badges and callouts.

### Risk levels

```mermaid
flowchart LR
    MI["🟢 Minor<br/>--sev-minor<br/>S < 3 and RPN < 40"] --> MA["🟠 Major<br/>--sev-major<br/>S ≥ 3 or RPN ≥ 40"] --> CR["🔴 Critical<br/>--sev-critical<br/>S ≥ 5 or RPN ≥ 100"]
    style MI fill:#ecfdf3,stroke:#067647,color:#067647
    style MA fill:#fff8eb,stroke:#b54708,color:#b54708
    style CR fill:#fef3f2,stroke:#c4320a,color:#c4320a
```

## 3. Typography

| Role | Font | Size / weight |
|---|---|---|
| Body & UI | **Geist Variable** → Inter → system-ui | 14 px / 1.5 |
| Section heading | Geist | 12 px / 600, uppercase, 0.08 em tracking, muted |
| KPI figure | Geist | 17 px / 600, tabular numbers |
| Meta & counts | Geist | 12 px, muted, tabular numbers |
| Code & IDs | `--mono` (SF Mono, Cascadia Mono, Consolas) | inherits size |

## 4. Shape, depth and spacing

| Token | Value | Use |
|---|---|---|
| `--r-xs` | `0.5rem` | Icon tiles, small controls |
| `--r-sm` | `0.625rem` | Inputs, buttons, list rows |
| `--r` | `0.875rem` | Cards, panels |
| `--r-lg` | `1rem` | Overlays, dialogs |
| `--pill` | `999px` | Badges, chips |
| `--shadow-xs` | 1 px hairline | Resting cards |
| `--shadow-md` | 4/12 px soft | Hover, popovers |
| `--shadow-lg` | 16/32 px | Drawers, dialogs |

Spacing follows a **4 px grid** (4 · 8 · 12 · 16 · 24 · 32).

## 5. Layout

```mermaid
block-beta
    columns 12
    SB["Sidebar<br/>New · Current · Saved · History · Theme"]:2
    block:MAIN:10
        columns 10
        HD["Header: breadcrumb · view switch · Undo · Print"]:10
        FORM["Log Deviation<br/>KPIs · stepper · sections · risk check"]:6
        CP["Copilot<br/>feed · chips · composer · voice"]:4
        CB["Commit bar: unsaved changes · Save"]:10
    end
```

- **≥ 1100 px:** a resizable split (form | copilot). The divider position is remembered.
- **< 1100 px:** a tabbed view switch between *Form* and *Copilot*.
- **Sidebar:** collapsible to icons; it becomes a sheet on mobile.

## 6. Components

| Component | Anatomy | States |
|---|---|---|
| **Field** | label · source chip · value · flash | empty · filled · just changed · overridden |
| **Source chip** | icon + "From the report" / "Calculated" / "Set by you" | info · purple · ok |
| **KPI card** | label · count-up number · caption | idle · pop on change |
| **Stepper** | 5 dots + connector | done · current (pulse once) · upcoming |
| **Risk matrix** | 5×5 S × O grid | the active cell pops; diagonal stagger on first show |
| **Copilot message** | avatar · text · tool chips · change table | enter slide-up · working (typing dots) |
| **Button** | primary · secondary · ghost · destructive | hover lift · press 0.97 · loading · success ✓ |
| **Toast** | icon · text · countdown bar | enter · paused on hover · dismiss |
| **Print report** | A4 header · summary · KV tables · risk · history · sign-off | screen preview · paper |

## 7. Motion

| Token | Value |
|---|---|
| `--ease` | `cubic-bezier(0.16, 1, 0.3, 1)` |
| Hover / press | 150 ms |
| Enter / exit | 200–300 ms |
| Field-fill stagger | 28 ms per field, capped at 24 fields |
| Count-up | 600 ms ease-out |

```mermaid
stateDiagram-v2
    direction LR
    Idle --> Saving: click Save
    Saving --> Saved: 200 OK (check draws in)
    Saved --> Idle: after 1.5 s → "Saved as DEV-…"
    Saving --> Idle: error toast
```

> [!IMPORTANT]
> Every animation is disabled under `prefers-reduced-motion: reduce`, and values then update instantly.

## 8. Accessibility checklist

- [x] Text contrast ≥ 4.5 : 1 in both themes
- [x] Visible focus ring (`--focus-ring`) on every interactive element
- [x] Full keyboard use: Enter sends, Shift+Enter adds a new line, Escape closes overlays and cancels recording
- [x] Confirm dialogs move focus to the safe (Cancel) action
- [x] Status is never shown by colour alone: level text, icons and labels are always present
- [x] `role=status` / `role=alert` regions announce copilot progress, voice state and errors
- [x] Reduced-motion support

## 9. Voice and tone

| ✅ Say | 🚫 Avoid |
|---|---|
| "I filled in 19 of 20 details from the image." | "Extraction pipeline completed." |
| "Not in the report, so I left these blank: likely cause." | "Null values for: root_cause_hypothesis." |
| "Risk: Major (severity 4 × likelihood 2 × hard to detect 3 = 24)." | "RPN=24, class=MAJOR." |
| "I couldn't hear any speech. Check the microphone." | "Error 422." |
