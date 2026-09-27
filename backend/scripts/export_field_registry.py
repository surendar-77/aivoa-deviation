"""Export the deviation field registry to an Excel workbook (docs/field_registry.xlsx).

Why generated, not hand-written: app/fields.py is the single source of truth for every field (form, AI
prompts, database columns, audit trail). This script turns it into a readable, filterable sheet for QA,
HR and reviewers, and can be re-run whenever a field changes so the sheet never drifts from the code.
The "Owner" and "Notes" columns are for people: their contents are carried over on every regeneration.

Run from backend/:  .venv\\Scripts\\python scripts\\export_field_registry.py [output.xlsx]
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from app.ai.wording import PLAIN_LABELS as CHAT_LABELS  # noqa: E402
from app.fields import FIELDS, RISK_SECTION, SECTIONS, TIER_LABELS  # noqa: E402
from app.rules import DUE_DAYS  # noqa: E402

UI_LABELS_FILE = ROOT / "frontend" / "src" / "plainLanguage.js"
DEFAULT_OUT = ROOT / "docs" / "field_registry.xlsx"

FONT = "Arial"
HEADER_FILL = PatternFill("solid", start_color="171717")
TIER_FILL = {"A": "EFF6FF", "B": "F4F3FF", "C": "ECFDF3"}
TIER_MEANING = {
    "A": ("From the report", "The AI fills it ONLY with facts written in the source report; left blank if absent."),
    "B": ("Calculated", "The AI risk check (scores, reasoning) or fixed Python rules (RPN, class, CAPA, deadline)."),
    "C": ("Set by a person", "Set by the system or by an explicit user instruction. The AI never invents it."),
}
THIN = Side(style="thin", color="E5E5E5")


def ui_labels() -> dict[str, str]:
    """Screen labels from the frontend's plainLanguage.js (FIELD_LABELS object)."""
    if not UI_LABELS_FILE.exists():
        return {}
    text = UI_LABELS_FILE.read_text(encoding="utf-8")
    block = re.search(r"FIELD_LABELS\s*=\s*\{(.*?)\n\};", text, re.S)
    return dict(re.findall(r'^\s*(\w+):\s*"([^"]*)"', block.group(1), re.M)) if block else {}


def carried_notes(path: Path) -> dict[str, tuple[str, str]]:
    """Owner/Notes typed by people in a previous version of the workbook, keyed by field key."""
    if not path.exists():
        return {}
    ws = load_workbook(path)["Fields"]
    head = [c.value for c in ws[1]]
    try:
        k, o, n = head.index("Field key"), head.index("Owner"), head.index("Notes")
    except ValueError:
        return {}
    return {r[k]: (r[o] or "", r[n] or "") for r in ws.iter_rows(min_row=2, values_only=True) if r[k]}


def style_header(ws, row: int = 1) -> None:
    for c in ws[row]:
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30


def body_font(ws, first_row: int = 2) -> None:
    for row in ws.iter_rows(min_row=first_row):
        for c in row:
            if c.font is None or c.font.name != FONT or not c.font.bold:
                c.font = Font(name=FONT, size=10, bold=c.font.bold if c.font else False, color=c.font.color if c.font else None)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = Border(bottom=THIN)


def widths(ws, cols: dict[str, int]) -> None:
    for letter, w in cols.items():
        ws.column_dimensions[letter].width = w


def build(out: Path) -> dict:
    notes = carried_notes(out)
    screen = ui_labels()
    wb = Workbook()

    # ------------------------------------------------------------ Fields
    ws = wb.active
    ws.title = "Fields"
    headers = ["#", "Field key", "Screen label (plain)", "Regulatory label", "Section", "Tier", "Filled by",
               "Type", "Allowed options", "Change by chat?", "Re-checks risk?", "Description / help",
               "Chat wording", "Owner", "Notes"]
    ws.append(headers)
    order = {s: i for i, s in enumerate(SECTIONS + [RISK_SECTION])}
    fields = sorted(FIELDS, key=lambda f: order.get(f.section, 99))
    for i, f in enumerate(fields, start=1):
        owner, note = notes.get(f.key, ("", ""))
        ws.append([
            i, f.key, screen.get(f.key, f.label), f.label, f.section, f"{f.tier} · {TIER_LABELS[f.tier]}",
            TIER_MEANING[f.tier][0], f.type, " | ".join(f.options), "Yes" if f.chat_editable else "No",
            "Yes" if f.risk_driving else "No", f.help, CHAT_LABELS.get(f.key, ""), owner, note,
        ])
        fill = PatternFill("solid", start_color=TIER_FILL[f.tier])
        for col in (6, 7):
            ws.cell(row=i + 1, column=col).fill = fill
    style_header(ws)
    body_font(ws)
    for r in range(2, len(fields) + 2):  # people-maintained columns stand out
        for col in (14, 15):
            ws.cell(row=r, column=col).fill = PatternFill("solid", start_color="FFFBEB")
    widths(ws, {"A": 5, "B": 28, "C": 30, "D": 30, "E": 24, "F": 18, "G": 16, "H": 10, "I": 36, "J": 11,
                "K": 11, "L": 48, "M": 30, "N": 16, "O": 36})
    last = len(fields) + 1
    table = Table(displayName="FieldRegistry", ref=f"A1:O{last}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=False)
    ws.add_table(table)
    ws.freeze_panes = "C2"
    ws["N1"].comment = Comment("Maintained by people. Kept when the sheet is regenerated.", "export_field_registry.py")
    ws["O1"].comment = Comment("Maintained by people. Kept when the sheet is regenerated.", "export_field_registry.py")

    # ------------------------------------------------------------ Sections (formulas over Fields)
    ss = wb.create_sheet("Sections")
    ss.append(["Section", "Fields", "From the report (A)", "Calculated (B)", "Set by a person (C)", "Change by chat"])
    rng = f"Fields!$E$2:$E${last}"
    tiers = f"Fields!$F$2:$F${last}"
    chat = f"Fields!$J$2:$J${last}"
    for r, sec in enumerate(SECTIONS + [RISK_SECTION], start=2):
        ss.append([sec, f"=COUNTIF({rng},A{r})", f'=COUNTIFS({rng},A{r},{tiers},"A*")',
                   f'=COUNTIFS({rng},A{r},{tiers},"B*")', f'=COUNTIFS({rng},A{r},{tiers},"C*")',
                   f'=COUNTIFS({rng},A{r},{chat},"Yes")'])
    total = len(SECTIONS) + 2
    ss.append(["Total"] + [f"=SUM({get_column_letter(c)}2:{get_column_letter(c)}{total})" for c in range(2, 7)])
    style_header(ss)
    body_font(ss)
    for c in ss[total + 1]:
        c.font = Font(name=FONT, size=10, bold=True)
    widths(ss, {"A": 28, "B": 10, "C": 20, "D": 16, "E": 20, "F": 16})

    # ------------------------------------------------------------ Tiers legend
    ts = wb.create_sheet("Tiers")
    ts.append(["Tier", "Name on screen", "Who fills it", "Fields"])
    for r, t in enumerate(("A", "B", "C"), start=2):
        ts.append([f"{t} · {TIER_LABELS[t]}", TIER_MEANING[t][0], TIER_MEANING[t][1], f'=COUNTIF({tiers},"{t}*")'])
        ts.cell(row=r, column=1).fill = PatternFill("solid", start_color=TIER_FILL[t])
    style_header(ts)
    body_font(ts)
    widths(ts, {"A": 22, "B": 20, "C": 70, "D": 10})

    # ------------------------------------------------------------ Rules (read from app/rules.py)
    rs = wb.create_sheet("Rules")
    rs.append(["Rule", "Definition", "Source"])
    rules = [
        ("Risk score (RPN)", "Severity × Likelihood (occurrence) × Hard to detect (detectability); each 1-5, so 1-125.", "app/rules.py"),
        ("Severity level: Critical", "Severity 5, or RPN 100 or more (unless a person overrides it with a reason).", "app/rules.py classify_severity"),
        ("Severity level: Major", "Severity 3 or more, or RPN 40 or more.", "app/rules.py classify_severity"),
        ("Severity level: Minor", "Otherwise.", "app/rules.py classify_severity"),
        ("Corrective action (CAPA) needed", "Critical or Major, or RPN 60 or more. A person may override with a reason.", "app/rules.py"),
        ("Investigation deadline", "Date found + " + ", ".join(f"{k} {v} days" for k, v in DUE_DAYS.items()) + ".", "app/rules.py DUE_DAYS"),
        ("How far outside the limit", "Parsed from allowed range vs actual value, e.g. '+6 °C above upper limit 65 °C (9.2% over)'.", "app/rules.py"),
        ("Happened before?", "Earlier record on the same machine, or same product + measurement (database lookup).", "app/crud.py find_related"),
        ("Record number", "DEV-YYYY-NNNN, restarts each year, never reused after a deletion.", "app/crud.py next_deviation_id"),
    ]
    for row in rules:
        rs.append(list(row))
    style_header(rs)
    body_font(rs)
    widths(rs, {"A": 30, "B": 80, "C": 30})

    # ------------------------------------------------------------ Read me
    rm = wb.create_sheet("Read me", 0)
    lines = [
        ("AIVOA Deviation Intake: field registry", True),
        (f"Generated {datetime.now():%Y-%m-%d %H:%M} from app/fields.py (single source of truth).", False),
        ("", False),
        ("How to use", True),
        ("• Fields: one row per field, filterable. Tier colours: blue = from the report, purple = calculated, green = set by a person.", False),
        ("• Owner and Notes (yellow columns) are for people to fill in. They are kept when the sheet is regenerated.", False),
        ("• Every other column comes from the code. Change fields in backend/app/fields.py, then regenerate; do not edit them here.", False),
        ("• Sections, Tiers: counts are live formulas over the Fields sheet.", False),
        ("• Rules: how the calculated fields are worked out.", False),
        ("", False),
        ("Regenerate", True),
        ("cd backend  →  .venv\\Scripts\\python scripts\\export_field_registry.py", False),
    ]
    for text, bold in lines:
        rm.append([text])
        rm.cell(row=rm.max_row, column=1).font = Font(name=FONT, size=14 if rm.max_row == 1 else 10, bold=bold)
    rm.column_dimensions["A"].width = 120

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    by_section = {s: sum(f.section == s for f in FIELDS) for s in SECTIONS + [RISK_SECTION]}
    by_tier = {t: sum(f.tier == t for f in FIELDS) for t in ("A", "B", "C")}
    return {"path": str(out), "fields": len(FIELDS), "by_section": by_section, "by_tier": by_tier,
            "notes_carried": sum(1 for v in notes.values() if any(v)),
            "missing_screen_labels": [f.key for f in FIELDS if f.key not in screen]}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    import json
    print(json.dumps(build(target), indent=2))
