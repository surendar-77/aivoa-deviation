# QA audit report: AIVOA Deviation Intake

**Date:** 27 September 2026 · **Scope:** full UI + API regression pass
**Environment:** Windows 11, backend FastAPI on :8000 (Groq `openai/gpt-oss-120b`, Whisper `whisper-large-v3-turbo`,
PostgreSQL, Tesseract), frontend Vite on :5173, headless Google Chrome via Playwright for end-to-end tests.

## 1. Summary

| Area | Result |
|------|--------|
| Backend unit + API tests (pytest) | **148 / 148 pass** (was 140; 8 new regression tests added) |
| Frontend production build | **Clean** (no errors, no warnings) |
| TypeScript strict check (`--noUnusedLocals --noUnusedParameters`) | **0 errors** |
| End-to-end browser suite, live AI (23 scenarios) | **23 / 23 pass**, 0 console errors, 0 failed API calls |
| UI regression after final fixes (9 non-AI scenarios) | **9 / 9 pass** |
| API error-handling probes (9 cases) | **9 / 9 correct** status codes and messages |
| Bugs found | **9 fixed**, 4 open recommendations |
| Dead code removed | 2 files, 4 icons, 9 CSS rules, 1 stale selector |

Overall verdict: **ready for the HR demo**, with the Groq free-tier caveat in section 6.

## 2. What was tested

### 2.1 Buttons and controls (all exercised in the browser)
| Control | Checked | Result |
|---------|---------|--------|
| Sidebar: New deviation | empty form → focuses assistant; dirty form → confirm dialog (Keep editing / Discard changes) | Pass |
| Sidebar: Current report / Saved reports / Change history | drawer opens and lists records; history disabled until first save, then opens modal | Pass |
| Sidebar: theme toggle | light → dark → light, persisted | Pass |
| Sidebar trigger (collapse/expand) | state changes both ways | Pass |
| Header: Undo | restores previous values, disabled when nothing to undo | Pass |
| Header: Report / Assistant switch (phone) | visible below 1100 px, swaps panes | Pass |
| Start panel: Upload a document / Paste an email | opens file picker / focuses assistant | Pass |
| Section index | scrolls to section, active item follows | Pass |
| Resize divider (record ↔ assistant) | keyboard arrows resize (720 px → 523 px) | Pass |
| Save report | Saving… → Saved ✓ → "Saved as DEV-…", toast with record number, button disabled after | Pass |
| Suggestion chips | plain label shown, glossary term sent | Pass |
| Composer: Enter / Shift+Enter | sends / new line | Pass |
| Attach (PDF) | chip appears, PDF read, form filled | Pass |
| Voice | recording strip with timer/level, Cancel discards, no text inserted | Pass |
| Change-history modal | 38 rows, plain column names, Escape closes | Pass |
| Saved-reports drawer: Change history / Delete | inline confirm, record removed | Pass |

### 2.2 End-to-end flows (live AI)
1. Log the HR demo report → 19–20 of 20 details filled, risk Major, matrix cell highlighted, status "Ready to save".
2. Casual correction ("batch is PC-2609-046, pH 9.1") → only those fields change; title/description corrected;
   change table shown.
3. Undo → previous values restored; re-apply works.
4. Human decisions (investigator, status) → stepper moves to "Open".
5. "Why is it Major?" → rule explanation with current values (no stale 8.9).
6. Off-topic request → politely refused, form unchanged.
7. "Set rpn to 5" → explains the risk score is calculated.
8. Save → record number, toast, change history (38 rows).
9. Dirty form + New → confirm dialog guards unsaved work.
10. PDF upload → read and filled.
11. Delete the QA record → removed (test data cleaned up).
12. Phone width 390 px → no horizontal scroll, pane switch works.

### 2.3 API edge cases
| Request | Expected | Actual |
|---------|----------|--------|
| Chat with no message and no file | 422 | 422 "Send a message or attach a file." |
| Chat with invalid form JSON | 422 | 422 "'form' must be valid JSON." |
| GET / PUT / DELETE / audit of unknown record | 404 | 404 "Deviation … not found." |
| Save an empty form | 422 | 422 "Nothing to save yet …" |
| Upload unsupported `.docx` | friendly refusal | "Unsupported file type '.docx' …" |
| Voice clip too small | 422 | 422 with guidance |

## 3. Bugs found and fixed

| # | Severity | Bug | Fix |
|---|----------|-----|-----|
| 1 | **High** | Correcting a select/status value (e.g. GMP impact Potential → Yes, status Draft → Open) would rewrite every whole-word "Potential"/"Draft" in the title and description, corrupting the narrative. | Propagation limited to identifier-like fields (batch, equipment, product, measured values, dates, people); regression test added. |
| 2 | **High** | Record numbers were reused after a deletion (DEV-2026-0006 issued twice) — not acceptable in a regulated QMS. | New `deviation_sequence` table; numbers only go up, row-locked on PostgreSQL; schema.sql updated; regression test added. |
| 3 | Medium | "Save" by chat depended on the LLM router, so it failed whenever Groq was rate-limited. | Save commands ("save", "save it", "commit", …) recognised deterministically; tests added. |
| 4 | Medium | Browser console error on every load (404 for `/favicon.ico`). | Inline SVG favicon added to `index.html`. |
| 5 | Low | Tool chip said "Applied your change" even when nothing changed (e.g. refused "set rpn to 5"). | Shows "Checked your request" when no fields changed. |
| 6 | Low | Risk panel label "Initial Risk Assessment" bypassed the plain-language layer. | Uses the plain label "Why this risk level". |
| 7 | Low | "Corrective action needed? (CAPA)" label truncated in the 3-column row; last workflow step ("Closed") clipped at laptop width. | Shorter label; tighter stepper spacing. |
| 8 | Low | Voice "too short" message said "Hold the mic button" although the button is click-to-start/stop; CAPA help text said it "can't be set" although a person may override it; `.txt` uploads showed the raw method name; empty-field placeholders used jargon ("Awaiting AI extraction…"). | Copy corrected in `speech.py`, `operations.py`, `plainLanguage.js`, `DeviationForm.jsx`. |
| 9 | Low | Staggered "AI writing" animation left fields blank for up to 1.35 s on large updates; tool labels still in a code font. | Stagger 28 ms, capped at 24 fields (≤ 0.7 s); normal font. |

## 4. Unwanted code removed
- `frontend/src/components/BrandTexture.tsx` and the unused WebGL background component + demo page.
- `frontend/src/components/ui/badge.tsx` (installed, never used).
- Icons `HistoryIcon`, `PlusIcon`, `SunIcon`, `MoonIcon` (replaced by lucide icons).
- CSS rules for removed features: composer hints, `kbd`, "powered by" caption, old rail buttons, old severity dot, `.small`; stale `.rail-btn` selector.

Verification: no unused imports in any `.jsx/.tsx`, no unreferenced CSS classes, strict TypeScript clean, CSS braces balanced.

## 5. Changed files (this QA pass)
Backend: `app/ai/operations.py`, `app/ai/conversation.py`, `app/ai/speech.py`, `app/crud.py`, `app/models.py`,
`db/schema.sql`, `tests/test_tools.py`, `tests/test_crud.py`, `tests/test_conversation.py`.
Frontend: `index.html`, `src/styles.css`, `src/plainLanguage.js`, `src/components/{AICopilotPanel,DeviationForm,RiskCard,ChangeHighlight,Icons}.jsx`.

## 6. Open issues and recommendations
| # | Priority | Item | Recommendation |
|---|----------|------|----------------|
| R1 | High (demo) | **Groq free tier:** ~8,000 tokens/minute; one report uses ~5,000. Rapid back-to-back messages return "rate limit reached" (handled gracefully, but visible). | In the demo, wait ~30 s after pasting a report; or use a paid Groq key. |
| R2 | Medium | Every change is attributed to "QA Reviewer": there is no login, so ALCOA+ "attributable" is not fully met. | Add login + roles (Reporter / QA reviewer / Approver). |
| R3 | Low | Resizing the window across 1100 px rebuilds the assistant panel, clearing a half-typed message (chat history is kept). | Keep one tree and switch layout with CSS only. |
| R4 | Low | The Playwright suite used for this audit lives outside the repo (`%TEMP%\aivoa-qa\e2e.mjs`). | Add it under `frontend/e2e/` with `playwright-core` as a dev dependency so it can run in CI. |

Housekeeping: README "Video 2" line numbers are out of date after the redesigns; nothing is committed to git yet;
records DEV-2026-0001…0005 in the database include earlier test data.
