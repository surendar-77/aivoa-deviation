/**
 * Printable deviation report (A4): record, risk check and change history in one shareable document.
 * Rendered in a preview overlay first; "Print / Save as PDF" prints only the sheet (see the print
 * styles in styles.css). Always light-themed and uses the same plain labels as the screen.
 */
import { useEffect } from "react";
import { createPortal } from "react-dom";
import { useSelector } from "react-redux";
import { fieldLabel, sourceLabel } from "../plainLanguage";
import { ruleFired } from "./RiskCard";

const isSet = (v) => v !== null && v !== undefined && v !== "";
const show = (v) => (isSet(v) ? String(v) : "—");
/** History cells repeat long narratives that are already printed in full above: keep them short. */
const brief = (v, max = 160) => { const s = show(v); return s.length > max ? s.slice(0, max - 1).trimEnd() + "…" : s; };
const SCORE_KEYS = ["severity_score", "occurrence_score", "detectability_score", "rpn"];
// Risk fields shown in the summary/FMEA line are not repeated in the risk table.
const RISK_SKIP = new Set([...SCORE_KEYS, "severity_classification", "capa_required", "investigation_due_date"]);

/** Date on one line, time on the next: keeps the narrow "When" column tidy. */
function when(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return (
    <>
      {d.toLocaleDateString([], { day: "2-digit", month: "short", year: "numeric" })}
      <br />
      <span className="pr-muted">{d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
    </>
  );
}

function KV({ rows }) {
  return (
    <table className="pr-kv">
      <tbody>
        {rows.map(([label, value]) => (
          <tr key={label}>
            <th scope="row">{label}</th>
            <td className={isSet(value) ? "" : "pr-empty"}>{show(value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function History({ rows, labels }) {
  return (
    <table className="pr-history">
      <thead>
        <tr><th>When</th><th>Field</th><th>Before</th><th>After</th><th>Came from</th><th>Request</th><th>Changed by</th></tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.id ?? i}>
            <td>{when(r.changed_at)}</td>
            <td><b>{labels[r.field] || r.field}</b></td>
            <td className="pr-old">{brief(r.old_value ?? r.old)}</td>
            <td>{brief(r.new_value ?? r.new)}</td>
            <td>{sourceLabel(r.source)}</td>
            <td className="pr-muted">{brief(r.instruction, 120)}</td>
            <td>{r.changed_by || "—"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function PrintReport({ auditRows, historyError, onClose }) {
  const { form, registry, userOverrides, changeLog, currentId, dirty } = useSelector((s) => s.deviation);

  // Escape closes the preview (App's handler covers the other overlays).
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!registry) return null;
  const labels = Object.fromEntries(registry.fields.map((f) => [f.key, fieldLabel(f.key, f.label)]));
  const cls = form.severity_classification;
  const rule = ruleFired(form, "severity_classification" in (userOverrides || {}));
  const printedAt = new Date().toLocaleString([], { dateStyle: "long", timeStyle: "short" });
  const pending = dirty || !currentId ? changeLog : [];

  const print = () => {
    const previous = document.title;
    document.title = `${currentId || "Draft"} - Deviation report`; // default PDF file name
    const restore = () => { document.title = previous; window.removeEventListener("afterprint", restore); };
    window.addEventListener("afterprint", restore);
    window.print();
  };

  const sections = registry.sections.map((section) => ({
    title: section.replace(/^\d+\.\s*/, ""),
    num: section.match(/^(\d+)/)?.[1],
    rows: registry.fields.filter((f) => f.section === section).map((f) => [labels[f.key], form[f.key]]),
  }));
  const riskRows = registry.fields
    .filter((f) => f.section === registry.riskSection && !RISK_SKIP.has(f.key))
    .map((f) => [labels[f.key], form[f.key]]);

  return createPortal(
    <div className="print-overlay" role="dialog" aria-modal="true" aria-label="Print preview">
      <div className="print-toolbar">
        <div>
          <b>Print preview</b>
          <span>Check the report, then print it or choose “Save as PDF” as the printer to share it.</span>
        </div>
        <div className="print-toolbar-actions">
          <button className="btn btn-secondary" onClick={onClose}>Close</button>
          <button className="btn btn-primary" onClick={print}>Print / Save as PDF</button>
        </div>
      </div>

      <article className="print-sheet">
        {/* ---------- header ---------- */}
        <header className="pr-header">
          <div className="pr-brand">
            <span className="pr-logo">A</span>
            <div>
              <div className="pr-org">AIVOA QMS</div>
              <div className="pr-doc">Deviation Report</div>
            </div>
          </div>
          <div className="pr-id">
            <div className="pr-id-number">{currentId || "Draft (not saved)"}</div>
            <div className="pr-id-meta">Status: <b>{show(form.status)}</b></div>
            <div className="pr-id-meta">Printed {printedAt}</div>
          </div>
        </header>

        <h1 className="pr-title">{show(form.title)}</h1>
        {!currentId && <p className="pr-banner">This report has not been saved yet. Values may still change.</p>}
        {currentId && dirty && <p className="pr-banner">This printout includes changes that are not saved yet.</p>}

        {/* ---------- summary ---------- */}
        <section className="pr-summary" aria-label="Summary">
          <div className="pr-cell">
            <span className="pr-cell-label">Severity level</span>
            <span className={`pr-sev pr-sev-${(cls || "none").toLowerCase()}`}>{show(cls)}</span>
          </div>
          <div className="pr-cell">
            <span className="pr-cell-label">Risk score (RPN)</span>
            <span className="pr-cell-value">{show(form.rpn)}<small> / 125</small></span>
            <span className="pr-cell-sub">
              {isSet(form.rpn) ? `${form.severity_score} × ${form.occurrence_score} × ${form.detectability_score}` : ""}
            </span>
          </div>
          <div className="pr-cell">
            <span className="pr-cell-label">Corrective action (CAPA)</span>
            <span className="pr-cell-value">{show(form.capa_required)}</span>
          </div>
          <div className="pr-cell">
            <span className="pr-cell-label">Investigation deadline</span>
            <span className="pr-cell-value">{show(form.investigation_due_date)}</span>
          </div>
        </section>

        {/* ---------- record sections ---------- */}
        {sections.map((s) => (
          <section key={s.title} className="pr-section">
            <h2><span>{s.num}</span>{s.title}</h2>
            <KV rows={s.rows} />
          </section>
        ))}

        {/* ---------- risk check ---------- */}
        <section className="pr-section">
          <h2><span>R</span>Risk check</h2>
          <div className="pr-fmea">
            <span>Severity <b>{show(form.severity_score)}</b></span>
            <span className="pr-op">×</span>
            <span>Likelihood <b>{show(form.occurrence_score)}</b></span>
            <span className="pr-op">×</span>
            <span>Hard to detect <b>{show(form.detectability_score)}</b></span>
            <span className="pr-op">=</span>
            <span>Risk score <b>{show(form.rpn)}</b></span>
            {rule && <span className="pr-rule">{rule}</span>}
          </div>
          <KV rows={riskRows} />
          {userOverrides?.severity_classification?.reason && (
            <p className="pr-note">Severity level set by a person: “{userOverrides.severity_classification.reason}”</p>
          )}
        </section>

        {/* ---------- change history ---------- */}
        <section className="pr-section pr-history-section">
          <h2><span>H</span>Change history</h2>
          {historyError && <p className="pr-banner">The saved change history could not be loaded: {historyError}</p>}
          {auditRows?.length ? (
            <History rows={auditRows} labels={labels} />
          ) : (
            <p className="pr-muted">No saved history yet. The permanent history starts when the report is saved.</p>
          )}
          {pending.length > 0 && (
            <>
              <h3 className="pr-subhead">Changes not yet saved ({pending.length})</h3>
              <History rows={pending.map((c) => ({ ...c, changed_by: "—" }))} labels={labels} />
            </>
          )}
        </section>

        {/* ---------- sign-off ---------- */}
        <section className="pr-signoff" aria-label="Sign-off">
          {["Reported by", "Reviewed by (QA)", "Approved by"].map((role) => (
            <div key={role} className="pr-sign">
              <div className="pr-sign-line" />
              <div className="pr-sign-role">{role}</div>
              <div className="pr-sign-meta">Name, signature and date</div>
            </div>
          ))}
        </section>

        <footer className="pr-footer">
          Generated by AIVOA QMS. “From the report” values were taken by the AI only from the source document;
          calculated values come from fixed rules; every change is recorded in the change history.
        </footer>
      </article>
    </div>,
    document.body
  );
}
