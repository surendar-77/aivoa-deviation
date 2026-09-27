/**
 * "Recent Deviations" drawer (saved rows from PostgreSQL). Click one to load it back into the
 * form for further chat edits; "Audit" shows its audit trail (who/what/why for every change).
 */
import { fieldLabel, sourceLabel } from "../plainLanguage";
import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { TrashIcon, XIcon } from "./Icons";
import { closeAudit, deleteDeviation, fetchAudit } from "../features/deviationSlice";

const LEVEL = { Critical: "critical", Major: "major", Minor: "minor" };

export function AuditModal() {
  const dispatch = useDispatch();
  const { audit, registry } = useSelector((s) => s.deviation);
  if (!audit.open) return null;
  const labels = Object.fromEntries((registry?.fields || []).map((f) => [f.key, fieldLabel(f.key, f.label)]));
  return (
    <div className="overlay" onClick={() => dispatch(closeAudit())}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={`Change history for ${audit.id}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Change history for {audit.id}</h3>
          <button className="icon-btn" onClick={() => dispatch(closeAudit())} aria-label="Close"><XIcon size={16} /></button>
        </div>
        <div className="modal-body">
          {audit.rows.length === 0 ? <p className="modal-empty">No changes have been recorded for this report yet.</p> : (
          <table>
            <thead>
              <tr><th>When</th><th>Field</th><th>Before</th><th>After</th><th>Came from</th><th>Request</th><th>Changed by</th></tr>
            </thead>
            <tbody>
              {audit.rows.map((a) => (
                <tr key={a.id}>
                  <td>{new Date(a.changed_at).toLocaleString()}</td>
                  <td><b>{labels[a.field] || a.field}</b></td>
                  {a.old_value == null ? <td><span className="none">empty</span></td> : <td className="old">{a.old_value}</td>}
                  <td>{a.new_value ?? <span className="none">empty</span>}</td>
                  <td><span className="src">{sourceLabel(a.source)}</span></td>
                  <td className="muted">{a.instruction}</td>
                  <td>{a.changed_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DeviationList({ onClose, onOpen, busy }) {
  const dispatch = useDispatch();
  const { savedList, currentId } = useSelector((s) => s.deviation);
  // Inline confirmation instead of window.confirm(): no blocking browser dialog, and testable.
  const [confirming, setConfirming] = useState(null);

  return (
    <div className="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div className="drawer-head">
        <h3 id="drawer-title">Saved reports <span className="count">{savedList.length}</span></h3>
        <button className="icon-btn" onClick={onClose} aria-label="Close"><XIcon size={16} /></button>
      </div>
      {busy && <p className="drawer-note">Opening another report is paused while the AI assistant is working.</p>}
      {savedList.length === 0 ? (
        <div className="drawer-empty">
          <b>No saved reports yet</b>
          <span>Give the AI assistant a report and save it. It will appear here with its change history.</span>
        </div>
      ) : (
        <ul>
          {savedList.map((d) => (
            <li key={d.deviation_id} className={d.deviation_id === currentId ? "active" : ""}>
              <button className="dl-open" onClick={() => onOpen(d.deviation_id)} disabled={busy}
                      aria-current={d.deviation_id === currentId ? "true" : undefined}>
                <span className="row1">
                  <b>{d.deviation_id}</b>
                  {d.severity_classification && (
                    <span className={`sev-badge sm sev-${LEVEL[d.severity_classification]}`}>{d.severity_classification}</span>
                  )}
                  <span className="status">{d.status}</span>
                </span>
                <span className="row2">{d.title || "Untitled deviation"}</span>
              </button>
              <div className="row3">
                <span className="muted">{d.batch_number ? `Batch ${d.batch_number}` : "No batch"}, RPN {d.rpn ?? "–"}</span>
                {confirming === d.deviation_id ? (
                  <span className="confirm">
                    Delete this report and its history?
                    <button className="link danger" onClick={() => { dispatch(deleteDeviation(d.deviation_id)); setConfirming(null); }}>
                      Delete
                    </button>
                    <button className="link" onClick={() => setConfirming(null)}>Cancel</button>
                  </span>
                ) : (
                  <span className="row-actions">
                    <button className="link" onClick={() => dispatch(fetchAudit(d.deviation_id))}>Change history</button>
                    <button className="link danger" onClick={() => setConfirming(d.deviation_id)} disabled={busy}>
                      <TrashIcon size={12} /> Delete
                    </button>
                  </span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
