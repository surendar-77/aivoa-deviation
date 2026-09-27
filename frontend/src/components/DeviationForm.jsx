/**
 * The Log Deviation form, rendered entirely from the backend field registry (GET /api/fields).
 * Every input is READ-ONLY by design: values change only through the AI Copilot, so each change
 * is traceable to a source document or a chat instruction (audit trail).
 */
import { fieldLabel } from "../plainLanguage";
import { useSelector } from "react-redux";
import { ChangeHighlight, FieldTag } from "./ChangeHighlight";
import { sectionId } from "./RecordHeader";
import { BriefcaseIcon, CalendarIcon, FlaskIcon, TagIcon, TextIcon } from "./Icons";

const SECTION_ICON = { 1: CalendarIcon, 2: FlaskIcon, 3: TextIcon, 4: TagIcon, 5: BriefcaseIcon };

/** Placeholder text depends on who is allowed to fill the field. */
function placeholder(f) {
  if (f.key === "description") return "The AI will write a clear summary of what happened...";
  if (f.tier === "C") return f.chat_editable ? "Set when you ask the assistant..." : "Filled in by the system...";
  if (f.type === "select") return "The AI will choose this from the report...";
  return "Filled in from the report...";
}

export function ReadOnlyInput({ field, value, flash, token }) {
  const order = useSelector((st) => st.deviation.highlight.fields.indexOf(field.key));
  const filled = value !== null && value !== undefined && value !== "";
  const cls = `input ${filled ? "filled" : ""} ${field.type === "select" ? "select" : ""}`;
  const shown = filled ? (field.type === "score" ? `${value} / 5` : String(value)) : "";
  return (
    <ChangeHighlight active={flash} token={token} order={Math.max(order, 0)}>
      {field.type === "textarea" || shown.length > 40 ? (
        // Long values (AI next action, SOP list, long titles) wrap and grow instead of being cut off.
        <textarea id={`f-${field.key}`} className={`${cls} grow`} readOnly value={shown} placeholder={placeholder(field)}
                  rows={field.type === "textarea" && field.key !== "title" ? 3 : 1} />
      ) : (
        <input id={`f-${field.key}`} className={cls} readOnly value={shown} placeholder={placeholder(field)} />
      )}
    </ChangeHighlight>
  );
}

export default function DeviationForm() {
  const { registry, form, highlight, changeLog, userOverrides } = useSelector((s) => s.deviation);
  if (!registry) return <p className="muted">Loading form definition…</p>;

  const edited = new Set(changeLog.filter((c) => c.source === "User instruction").map((c) => c.field));
  const flashing = new Set(highlight.fields);

  return registry.sections.map((section, i) => {
    const [, num, title] = section.match(/^(\d+)\.\s*(.*)$/) || [null, i + 1, section];
    const fields = registry.fields.filter((f) => f.section === section);
    const filled = fields.filter((f) => form[f.key] !== null && form[f.key] !== undefined && form[f.key] !== "").length;
    return (
    <section key={section} id={sectionId(section)} className="form-section card">
      <div className="section-head">
        <span className="section-icon" aria-hidden="true">{(() => { const Icon = SECTION_ICON[num] || TextIcon; return <Icon size={15} />; })()}</span>
        <h4 className="section-title"><span className="section-num">{num}</span>{title}</h4>
        <span className="section-meta">
          <span className={`section-bar ${filled === fields.length ? "full" : ""}`} aria-hidden="true">
            <span style={{ width: `${fields.length ? (filled / fields.length) * 100 : 0}%` }} />
          </span>
          {filled} of {fields.length} filled
        </span>
      </div>
      <div className="grid">
        {fields.map((f) => (
            <div key={f.key} className={`field ${f.type === "textarea" ? "wide" : ""}`}>
              <div className="field-head">
                <label htmlFor={`f-${f.key}`} title={f.help || f.label}>{fieldLabel(f.key, f.label)}</label>
                <FieldTag field={f} userEdited={edited.has(f.key)} overridden={f.key in userOverrides} />
              </div>
              <ReadOnlyInput field={f} value={form[f.key]} flash={flashing.has(f.key)} token={highlight.token} />
            </div>
          ))}
      </div>
    </section>
    );
  });
}
