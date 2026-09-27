/**
 * In-page confirmation (no window.confirm): used before an action would discard uncommitted changes.
 * Focus lands on Cancel, the safe choice; Escape is handled by App like every other overlay.
 */
import { useEffect, useRef } from "react";

export default function ConfirmDialog({ title, body, confirmLabel, onConfirm, onCancel }) {
  const cancelRef = useRef(null);
  useEffect(() => {
    cancelRef.current?.focus();
  }, []);
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"
           onClick={(e) => e.stopPropagation()}>
        <h3 id="confirm-title">{title}</h3>
        <p>{body}</p>
        <div className="dialog-actions">
          <button ref={cancelRef} className="btn btn-secondary" onClick={onCancel}>Keep editing</button>
          <button className="btn btn-danger" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}
