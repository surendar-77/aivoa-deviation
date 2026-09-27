/**
 * Plain-language wording for everything the reviewer sees.
 * The backend keeps its precise regulatory labels (they drive the AI prompts and the audit trail);
 * this file only changes how they are *displayed*. The industry term stays in brackets where a
 * QA specialist would look for it.
 */

/** Field key -> label shown on screen. Keys not listed keep the backend label. */
export const FIELD_LABELS = {
  title: "Title",
  reported_by: "Reported by",
  department: "Department",
  site: "Site",
  product_name: "Product",
  batch_number: "Batch number",
  category: "Category",
  status: "Status",
  date_detected: "Date found",
  area_location: "Area / location",
  manufacturing_stage: "Production step",
  equipment_id: "Machine / equipment ID",
  process_parameter: "What was measured",
  approved_range: "Allowed range",
  observed_value: "Actual value",
  description: "What happened",
  immediate_action: "Immediate action taken",
  root_cause_hypothesis: "Likely cause",
  batch_disposition: "What happens to the batch",
  deviation_type: "Planned or unplanned",
  gmp_impact: "Affects product quality? (GMP)",
  root_cause_category: "Type of cause",
  deviation_id: "Record number",
  date_reported: "Date recorded",
  assigned_investigator: "Investigator",
  ha_notification_required: "Tell the health authority?",
  customer_notification_required: "Tell the customer?",
  quarantine_reference: "Hold / quarantine number",
  source_document: "Received from",
  last_updated_by: "Last changed by",
  severity_score: "Severity",
  occurrence_score: "Likelihood",
  detectability_score: "Hard to detect",
  rpn: "Risk score (RPN)",
  severity_classification: "Severity level",
  severity_reasoning: "Why this risk level",
  impact_assessment: "Possible impact",
  suggested_next_action: "Suggested next step",
  capa_required: "Corrective action (CAPA)",
  investigation_due_date: "Investigation deadline",
  deviation_magnitude: "How far outside the limit",
  repeat_deviation: "Happened before?",
  related_deviation_id: "Earlier similar record",
  applicable_sop: "Related procedures (SOP), please check",
};

/** Who is allowed to fill a field (the backend's three tiers). */
export const TIER_LABELS = { A: "From the report", B: "Calculated", C: "Set by a person" };

/** Where a change came from (audit trail + Copilot change lists). */
export const SOURCE_LABELS = {
  "AI-extracted": "From the report",
  "AI-computed": "Calculated",
  "User instruction": "Your request",
  "Human/System": "System",
};

/** Copilot tool names -> what the tool did. The code name stays available as a tooltip. */
export const TOOL_LABELS = {
  pdf_extraction_tool: "Read the document",
  log_interaction_tool: "Filled in the form",
  edit_interaction_tool: "Applied your change",
};

/** Text-extraction method -> plain description. */
export function methodLabel(method = "") {
  const m = method.toLowerCase();
  if (m.includes("ocr")) return m.includes("pdf") ? "Read a scanned PDF" : "Read text from an image";
  if (m.includes("pdf")) return "Read the PDF text";
  if (m.includes("email") || m.includes("eml")) return "Read the email";
  if (m.includes("chat")) return "Read your message";
  if (m.includes("plain text")) return "Read the text file";
  return method;
}

export const fieldLabel = (key, fallback) => FIELD_LABELS[key] || fallback || key;
export const sourceLabel = (s) => SOURCE_LABELS[s] || s;
