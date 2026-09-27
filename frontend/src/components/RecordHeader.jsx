/**
 * Record header (title, status, key risk figures, workflow stepper) and the sticky section index.
 * Everything here is derived from the form + registry, so it can never disagree with the fields below.
 */
import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { AlertTriangleIcon, CalendarIcon, CheckIcon, ClipboardIcon, FileIcon, GaugeIcon } from "./Icons";
import { useCountUp } from "../hooks/useCountUp";

const LEVEL = { Critical: "critical", Major: "major", Minor: "minor" };
const isSet = (v) => v !== null && v !== undefined && v !== "";

/** Section heading "1. Event Details" -> DOM id used by the section index. */
export const sectionId = (section) => `sec-${section.match(/^(\d+)/)?.[1] ?? section}`;

function Kpi({ label, icon: Icon, tone = "", children, sub, title }) {
  return (
    <div className={`kpi ${tone}`} title={title}>
      <span className="kpi-icon" aria-hidden="true"><Icon size={16} /></span>
      <div className="kpi-body">
        <span className="kpi-label">{label}</span>
        <span className="kpi-value">{children}</span>
        {sub && <span className="kpi-sub">{sub}</span>}
      </div>
    </div>
  );
}

/** "in 29 days" / "today" / "3 days overdue" for a YYYY-MM-DD date. */
function relativeDays(iso) {
  const due = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(due.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const days = Math.round((due - today) / 86400000);
  if (days === 0) return { text: "Due today", late: false };
  if (days < 0) return { text: `${-days} day${days === -1 ? "" : "s"} overdue`, late: true };
  return { text: `In ${days} day${days === 1 ? "" : "s"}`, late: false };
}

function Ring({ pct }) {
  const r = 15, c = 2 * Math.PI * r;
  return (
    <svg className="donut" width="36" height="36" viewBox="0 0 36 36" aria-hidden="true">
      <circle cx="18" cy="18" r={r} className="donut-track" />
      {pct > 0 && <circle cx="18" cy="18" r={r} className="donut-fill" strokeDasharray={`${(pct / 100) * c} ${c}`} transform="rotate(-90 18 18)" />}
    </svg>
  );
}

export function RecordHeader() {
  const { form, registry, currentId, dirty } = useSelector((s) => s.deviation);
  const hasForm = Object.values(form).some(isSet);
  const statuses = registry?.fields.find((f) => f.key === "status")?.options || [];
  const current = Math.max(0, statuses.indexOf(form.status || "Draft"));
  const tierA = (registry?.fields || []).filter((f) => f.tier === "A");
  const filled = tierA.filter((f) => isSet(form[f.key])).length;
  const pct = tierA.length ? Math.round((filled / tierA.length) * 100) : 0;
  const cls = form.severity_classification;
  const rpnShown = useCountUp(isSet(form.rpn) ? form.rpn : null);
  const filledShown = useCountUp(filled);
  const due = form.investigation_due_date ? relativeDays(form.investigation_due_date) : null;

  return (
    <section className="record-header">
      <div className="rh-top">
        <div className="rh-title">
          <h1>Log Deviation</h1>
          <p className="rh-sub">Record and risk-check a quality problem (a “deviation”) found during manufacturing</p>
        </div>
        <div className="rh-status">
          {!hasForm ? (
            <span className="status-pill pending">Waiting for a report</span>
          ) : currentId && !dirty ? (
            <span className="status-pill saved"><i aria-hidden="true" /> Saved</span>
          ) : (
            <span className="status-pill ready"><i aria-hidden="true" /> Ready to save</span>
          )}
        </div>
      </div>

      <div className="rh-record">
        {currentId && <span className="rh-id">{currentId}</span>}
        <span className={`rh-subject ${form.title ? "" : "empty"}`}>
          {form.title || (hasForm ? "Untitled deviation" : "Nothing loaded yet. Give the AI assistant a report to start.")}
        </span>
        {dirty && currentId && <span className="unsaved">Unsaved changes</span>}
      </div>

      <div className="kpis">
        <Kpi label="Severity" icon={AlertTriangleIcon} tone={cls ? `tone-${LEVEL[cls]}` : ""}
             sub={isSet(form.severity_score) ? `Severity score ${form.severity_score} of 5` : null}>
          {cls ? <span key={cls} className="pop">{cls}</span> : <span className="dash">—</span>}
        </Kpi>
        <Kpi label="Risk score" icon={GaugeIcon} title="Risk Priority Number (RPN) = severity × likelihood × how hard it is to detect. Major from 40, Critical from 100"
             sub={isSet(form.rpn) ? <span className="rpn-mini"><span style={{ width: `${Math.min(100, (form.rpn / 125) * 100)}%` }} /></span> : null}>
          {isSet(form.rpn) ? <><span className="num">{rpnShown}</span><span className="of">of 125</span></> : <span className="dash">—</span>}
        </Kpi>
        <Kpi label="Corrective action" icon={ClipboardIcon} title="CAPA: Corrective And Preventive Action" tone={form.capa_required === "Yes" ? "tone-accent" : ""}
             sub={form.capa_required === "Yes" ? "Needed" : form.capa_required === "No" ? "Not needed" : null}>
          {form.capa_required || <span className="dash">—</span>}
        </Kpi>
        <Kpi label="Investigation deadline" icon={CalendarIcon} tone={due?.late ? "tone-critical" : ""}
             sub={due ? due.text : null}>
          {form.investigation_due_date ? <span className="num">{form.investigation_due_date}</span> : <span className="dash">—</span>}
        </Kpi>
        <Kpi label="Received from" icon={FileIcon} sub={form.date_reported ? `Reported ${form.date_reported}` : null}>
          {form.source_document ? <span className="trunc">{form.source_document}</span> : <span className="dash">—</span>}
        </Kpi>
        <div className="kpi kpi-ring" title={`${filled} of ${tierA.length} report details found by the AI`}>
          <Ring pct={pct} />
          <div className="kpi-body">
            <span className="kpi-label">Details found by AI</span>
            <span className="kpi-value"><span className="num">{filledShown}</span><span className="of">of {tierA.length}</span></span>
            {filled > 0 && <span className="kpi-sub">{pct}% filled from the report</span>}
          </div>
        </div>
      </div>

      {statuses.length > 0 && (
        <ol className="stepper" aria-label="Workflow status">
          {statuses.map((s, i) => (
            <li key={i === current && hasForm ? `${s}-current` : s} className={i < current ? "done" : i === current && hasForm ? "current" : ""}
                aria-current={i === current && hasForm ? "step" : undefined}>
              <span className="step-dot" aria-hidden="true">{i < current ? <CheckIcon size={11} strokeWidth={3} /> : i + 1}</span>
              <span className="step-label">{s}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** Sticky index of form sections with fill counts; highlights the section in view (scroll-spy). */
export function SectionNav({ scrollRoot }) {
  const { registry, form } = useSelector((s) => s.deviation);
  const [active, setActive] = useState(null);
  const items = registry
    ? [
        ...registry.sections.map((sec) => {
          const fields = registry.fields.filter((f) => f.section === sec);
          return { id: sectionId(sec), label: sec.replace(/^\d+\.\s*/, ""), num: sec.match(/^(\d+)/)?.[1],
                   filled: fields.filter((f) => isSet(form[f.key])).length, total: fields.length };
        }),
        { id: "sec-risk", label: "Risk check", num: "R", filled: null },
      ]
    : [];

  // Scroll-spy: the active section is the last one whose top has passed the upper part of the viewport.
  useEffect(() => {
    const root = scrollRoot?.current;
    if (!root || !items.length) return;
    const onScroll = () => {
      const limit = root.getBoundingClientRect().top + 120;
      let current = items[0].id;
      for (const it of items) {
        const el = document.getElementById(it.id);
        if (el && el.getBoundingClientRect().top <= limit) current = it.id;
      }
      // At the very bottom the last section may never reach the top: select it anyway.
      if (root.scrollTop + root.clientHeight >= root.scrollHeight - 4) current = items[items.length - 1].id;
      setActive(current);
    };
    onScroll();
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
    // Re-attach only when the set of sections changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registry, scrollRoot]);

  const go = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });

  return (
    <nav className="section-nav" aria-label="Form sections">
      <div className="section-nav-title">Sections</div>
      {items.map((it) => (
        <button key={it.id} className={active === it.id ? "on" : ""} onClick={() => go(it.id)}>
          <span className="sn-num">{it.num}</span>
          <span className="sn-label">{it.label}</span>
          {it.filled !== null && (
            <span className={`sn-count ${it.filled === it.total ? "full" : ""}`}>{it.filled}/{it.total}</span>
          )}
        </button>
      ))}
    </nav>
  );
}
