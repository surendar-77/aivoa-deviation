// Small presentational helpers: the tier tag on each field and the "just changed" flash wrapper.
import { TIER_LABELS } from "../plainLanguage";

const TAG_CLASS = { A: "tag-a", B: "tag-b", C: "tag-c" };
const TIER_HELP = {
  A: "Filled by the AI only with facts written in the report - never guessed",
  B: "Calculated by the AI risk check or by fixed rules",
  C: "Set by the system or by a person's instruction - never by the AI on its own",
};

/** "AI-extracted" / "AI-computed" / "Human/System", plus markers for user edits and overrides. */
export function FieldTag({ field, userEdited, overridden }) {
  return (
    <span className="tags">
      {overridden && <span className="tag tag-override" title="Explicit human decision - AI/rules will not overwrite it">Override</span>}
      {userEdited && !overridden && <span className="tag tag-user" title="Changed by a chat instruction">Edited</span>}
      <span className={`tag ${TAG_CLASS[field.tier]}`} title={TIER_HELP[field.tier]}>{TIER_LABELS[field.tier] || field.tier_label}</span>
    </span>
  );
}

/**
 * Wraps a field; when `active` the input flashes. `token` is used as the React key so the
 * CSS animation restarts every time the same field changes again.
 */
export function ChangeHighlight({ active, token, order = 0, children, className = "" }) {
  // `order` staggers the flash top-to-bottom when many fields change at once (reads as the AI filling the form).
  return (
    <div key={active ? token : "static"} className={`input-wrap ${active ? "flash" : ""} ${className}`}
         style={active ? { "--i": Math.min(order, 24) } : undefined}>
      {children}
    </div>
  );
}
