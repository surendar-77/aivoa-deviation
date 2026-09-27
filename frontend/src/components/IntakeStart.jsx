/**
 * "Report a new quality problem" card, shown inside the Copilot panel while no deviation is loaded.
 * It lives next to the message box on purpose: uploading and pasting are Copilot actions, and the
 * Copilot is the only way to fill the form.
 */
import { FileIcon, MailIcon, ShieldIcon, UploadIcon } from "./Icons";

/** Other parts of the app (e.g. "New deviation" in the sidebar) ask the Copilot to focus its message box. */
export const COMPOSE_EVENT = "aivoa:compose";

export default function IntakeStart({ onUpload, onPaste }) {
  return (
    <section className="intake-start in-copilot" aria-labelledby="intake-title">
      <div className="intake-text">
        <h2 id="intake-title">Report a new quality problem</h2>
        <p>Upload the original report or paste it below. I'll fill in the form, check the risk, and leave blank
          anything the report does not say, so nothing is made up.</p>
      </div>
      <div className="intake-actions">
        <button className="intake-tile primary" onClick={onUpload}>
          <span className="tile-icon"><UploadIcon size={18} /></span>
          <span className="tile-text"><b>Upload a document</b><span>PDF, JPG, PNG, EML or TXT</span></span>
        </button>
        <button className="intake-tile" onClick={onPaste}>
          <span className="tile-icon"><MailIcon size={18} /></span>
          <span className="tile-text"><b>Paste an email or report</b><span>Type or paste it in the box below</span></span>
        </button>
      </div>
      <ul className="intake-facts">
        <li><FileIcon size={14} /> Scanned PDFs and photos can be read too</li>
        <li><ShieldIcon size={14} /> Every change is kept in a change history when you save</li>
      </ul>
    </section>
  );
}
