"""The three named @tool functions, invoked standalone (mock mode) and through the graph."""
import base64
from pathlib import Path

import pytest

from app.ai.graph import run_agent
from app.ai.tools import TOOLS, edit_interaction_tool, log_interaction_tool, pdf_extraction_tool
from app.config import settings

SAMPLES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    monkeypatch.setattr(type(settings), "GROQ_API_KEY", "")


def test_tools_are_registered_with_exact_names():
    assert [t.name for t in TOOLS] == ["pdf_extraction_tool", "log_interaction_tool", "edit_interaction_tool"]
    assert all(t.description for t in TOOLS)


def test_pdf_extraction_tool():
    b64 = base64.b64encode((SAMPLES / "deviation_report.pdf").read_bytes()).decode()
    out = pdf_extraction_tool.invoke({"file_name": "deviation_report.pdf", "file_b64": b64})
    assert out["method"] == "PDF text layer (pypdf)" and "AC-2609-042" in out["text"]
    assert "error" in pdf_extraction_tool.invoke({"file_name": "x.docx", "file_b64": b64})


def test_log_interaction_tool_never_sets_tier_c_beyond_system_defaults():
    text = (SAMPLES / "deviation_email.txt").read_text(encoding="utf-8")
    out = log_interaction_tool.invoke({"text": text, "method": "plain text", "file_name": "mail.txt"})
    form = out["form"]
    assert form["batch_number"] == "MS-2609-017"
    assert form["assigned_investigator"] is None and form["quarantine_reference"] is None
    assert form["status"] == "Draft" and form["source_document"] == "mail.txt"


def test_edit_interaction_tool_casual_multi_field_correction():
    form = {"batch_number": "MS-2609-017", "observed_value": "70 °C"}
    out = edit_interaction_tool.invoke({
        "instruction": "ah sorry the batch number is BMX240602 and observed value is 71 °C",
        "form": form, "user_overrides": {}})
    assert out["form"]["batch_number"] == "BMX240602" and out["form"]["observed_value"] == "71 °C"
    assert out["reply"] == ('Got it. I have updated the batch number to "BMX240602" and '
                            'the actual value to "71 °C" in the form.')


def test_graph_routes_through_named_tools():
    data = (SAMPLES / "deviation_report.pdf").read_bytes()
    r = run_agent("", {}, [], {}, "deviation_report.pdf", data)
    assert r["tools_used"] == ["pdf_extraction_tool", "log_interaction_tool"]
    assert r["form"]["suggested_next_action"]
    r2 = run_agent("clear the equipment ID", r["form"], [], r["user_overrides"])
    assert r2["tools_used"] == ["edit_interaction_tool"] and r2["form"]["equipment_id"] is None


def test_setting_a_calculated_field_explains_why_it_cannot_be_typed_in():
    from app.ai.operations import computed_field_hint

    assert "calculated automatically" in computed_field_hint("set rpn to 5")
    assert "calculated automatically" in computed_field_hint("change the risk score to 20")
    assert computed_field_hint("set the batch number to B-1") is None


def test_a_corrected_value_is_also_corrected_in_the_title_and_description():
    from app.ai.operations import apply_operations

    form = {"title": "pH out of range - batch PC-2609-045", "batch_number": "PC-2609-045", "observed_value": "8.9",
            "description": "pH was 8.9 in batch PC-2609-045; limit 18.9 was not involved."}
    ops = [{"field": "batch_number", "action": "set", "value": "PC-2609-046"},
           {"field": "observed_value", "action": "set", "value": "9.1"}]
    new, _, sources, applied, _ = apply_operations(form, {}, ops, "batch is PC-2609-046 and pH 9.1")
    assert new["title"] == "pH out of range - batch PC-2609-046"
    assert new["description"] == "pH was 9.1 in batch PC-2609-046; limit 18.9 was not involved."
    assert sources["title"][0] == "User instruction" and len(applied) == 2


def test_changing_a_status_or_select_value_never_rewrites_the_narrative():
    from app.ai.operations import apply_operations

    form = {"title": "Draft note", "status": "Draft", "gmp_impact": "Potential",
            "description": "Potential impact on the Draft batch record."}
    ops = [{"field": "status", "action": "set", "value": "Open"},
           {"field": "gmp_impact", "action": "set", "value": "Yes"}]
    new, _, _, applied, _ = apply_operations(form, {}, ops, "status open, gmp impact yes")
    assert new["description"] == "Potential impact on the Draft batch record." and new["title"] == "Draft note"
    assert len(applied) == 2
