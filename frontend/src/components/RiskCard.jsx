/**
 * "AI copilot risk assessment" card. Shows the Tier-B fields: the LLM's judgement
 * (scores, reasoning, next action) and the rule engine's outputs (RPN, class, CAPA, due date...).
 * The S × O × D = RPN line is written out literally so a reviewer can check the arithmetic and the rule.
 */
import { fieldLabel } from "../plainLanguage";
import { useSelector } from "react-redux";
import { ReadOnlyInput } from "./DeviationForm";
import { ShieldIcon } from "./Icons";
import { useCountUp } from "../hooks/useCountUp";

/** The deterministic rule that produced the classification (mirrors backend/app/rules.py). */
export function ruleFired(form, overridden) {
  const { severity_score: s, rpn } = form;
  if (!form.severity_classification) return null;
  if (overridden) return "Set by a person, overriding the AI";
  if (s >= 5) return "Critical because severity is 5";
  if (rpn >= 100) return "Critical because the risk score is 100 or more";
  if (s >= 3) return "Major because severity is 3 or more";
  if (rpn >= 40) return "Major because the risk score is 40 or more";
  return "Minor because severity is below 3 and the risk score is below 40";
}

const LEVEL = { Critical: "critical", Major: "major", Minor: "minor" };

function Factor({ label, value, max, hint, total }) {
  const shown = useCountUp(value ?? null);
  return (
    <div className={`factor ${total ? "total" : ""}`} title={hint}>
      <span className="factor-value">{shown ?? "–"}<small>/{max}</small></span>
      <span className="factor-label">{label}</span>
    </div>
  );
}

/** Heat band for a Severity x Occurrence cell (the classic 5x5 risk matrix). */
const band = (v) => (v >= 20 ? "b5" : v >= 15 ? "b4" : v >= 10 ? "b3" : v >= 5 ? "b2" : "b1");

/** 5x5 Severity (rows, 5 at top) x Occurrence (columns) matrix with this deviation's cell marked. */
function RiskMatrix({ s, o }) {
  const rows = [5, 4, 3, 2, 1];
  const cols = [1, 2, 3, 4, 5];
  return (
    <div className={`matrix ${s && o ? "assessed" : ""}`} role="img"
         aria-label={s && o ? `Risk matrix: severity ${s}, occurrence ${o}` : "Risk matrix: not assessed"}>
      <span className="matrix-y">Severity</span>
      <div className="matrix-grid">
        {rows.map((r) => (
          <div className="matrix-row" key={r}>
            <span className="matrix-tick">{r}</span>
            {cols.map((c) => (
              <span key={c} className={`cell ${band(r * c)} ${r === s && c === o ? "here" : ""}`}
                    style={{ "--d": 5 - r + c }} />
            ))}
          </div>
        ))}
        <div className="matrix-row ticks">
          <span className="matrix-tick" />
          {cols.map((c) => <span key={c} className="matrix-tick">{c}</span>)}
        </div>
      </div>
      <span className="matrix-x">Likelihood</span>
    </div>
  );
}

export default function RiskCard() {
  const { registry, form, userOverrides, highlight } = useSelector((s) => s.deviation);
  if (!registry) return null;
  const byKey = Object.fromEntries(registry.fields.map((f) => [f.key, f]));
  const flash = new Set(highlight.fields);
  const cls = form.severity_classification;
  const overridden = "severity_classification" in userOverrides;
  const rule = ruleFired(form, overridden);

  const field = (key, label, wide = false) => (
    <div className={`field ${wide ? "wide" : ""}`}>
      <div className="field-head">
        <label htmlFor={`f-${key}`}>{label || fieldLabel(key, byKey[key].label)}</label>
        {key in userOverrides && <span className="tag tag-override">Override</span>}
      </div>
      <ReadOnlyInput field={byKey[key]} value={form[key]} flash={flash.has(key)} token={highlight.token} />
    </div>
  );

  return (
    <section className="risk-card" id="sec-risk" aria-labelledby="risk-title">
      <div className="risk-head">
        <h4 className="risk-title" id="risk-title"><ShieldIcon size={16} /> Risk check by the AI assistant</h4>
      </div>

      <div className={`fmea ${flash.has("rpn") ? "flash-chips" : ""}`} key={flash.has("rpn") ? highlight.token : "s"}
           aria-label={form.rpn ? `Severity ${form.severity_score} times occurrence ${form.occurrence_score} times detectability ${form.detectability_score} equals RPN ${form.rpn}` : "Risk scores not assessed yet"}>
        <div className="fmea-main">
        <div className="fmea-calc">
          <Factor label="Severity" value={form.severity_score} max={5} hint="Impact on product quality and patient safety" />
          <span className="op" aria-hidden="true">×</span>
          <Factor label="Likelihood" value={form.occurrence_score} max={5} hint="How likely it is to happen again" />
          <span className="op" aria-hidden="true">×</span>
          <Factor label="Hard to detect" value={form.detectability_score} max={5} hint="Detectability: 5 means the problem is hard to notice" />
          <span className="op" aria-hidden="true">=</span>
          <Factor label="Risk score" value={form.rpn} max={125} total hint="Risk Priority Number (RPN) = severity × likelihood × hard to detect. Major from 40, Critical from 100" />
        </div>
        <div className="fmea-result">
          {cls ? (
            <>
              <span key={cls} className={`sev-badge sev-${LEVEL[cls]} pop`}>{cls}</span>
              <span className="rule-note">{rule}</span>
            </>
          ) : (
            <span className="rule-note">Scores appear once the AI assistant has read a report.</span>
          )}
        </div>
        </div>
        <RiskMatrix key={`${form.severity_score}-${form.occurrence_score}`} s={form.severity_score} o={form.occurrence_score} />
      </div>

      <div className="risk-body">
        <div className="grid">
          {field("severity_classification")}
          {field("suggested_next_action")}
          <div className="field wide">
            <div className="field-head"><label htmlFor="f-severity_reasoning">{fieldLabel("severity_reasoning", "Initial Risk Assessment")}</label></div>
            <ReadOnlyInput field={{ ...byKey.severity_reasoning, key: "severity_reasoning" }} value={form.severity_reasoning}
                           flash={flash.has("severity_reasoning")} token={highlight.token} />
          </div>
        </div>
        <div className="grid grid-3">
          {field("capa_required")}
          {field("investigation_due_date")}
          {field("repeat_deviation", form.related_deviation_id ? `Repeat of ${form.related_deviation_id}` : undefined)}
        </div>
        <div className="grid">
          {field("deviation_magnitude", undefined, true)}
          {field("impact_assessment", undefined, true)}
          {field("applicable_sop", undefined, true)}
        </div>
        {userOverrides.severity_classification?.reason && (
          <p className="override-note">
            Severity was overridden by the user: “{userOverrides.severity_classification.reason}”
          </p>
        )}
      </div>
    </section>
  );
}
