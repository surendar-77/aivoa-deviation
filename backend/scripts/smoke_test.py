"""End-to-end smoke test against a RUNNING backend (python scripts/smoke_test.py).

log (pasted text) -> 5 edit commands -> assess -> save -> load -> edit -> update -> audit.
Works in both mock mode and Groq mode; prints each step so it doubles as a demo.
"""
import json
import sys

import httpx

API = "http://localhost:8000/api"
EMAIL = """\nFrom: Ravi Kumar <ravi.kumar@apiplant.example>
To: QA Deviation Desk <qa.deviations@apiplant.example>
Date: 14 September 2026 09:42
Subject: Temperature excursion in Reactor R-201 - Metoprolol Succinate batch MS-2609-017

Dear QA Team,

This is to report a process deviation observed in Production Block B (Crystallization Area) during the night shift.

On 14/09/2026 at approximately 02:15 hrs, during the cooling crystallization stage of Metoprolol Succinate batch MS-2609-017 in glass-lined reactor R-201, the reactor mass temperature rose to 71 °C. The approved range for this step as per the BMR is 60-65 °C. The excursion lasted about 25 minutes before the temperature was brought back within range.

The DCS alarm was acknowledged by the shift operator. Preliminary check indicates that the chilled water supply valve (TCV-201) to the reactor jacket was sticking, which reduced cooling flow.

Immediate action taken:
- Crystallization hold-time was extended and the batch was brought back to 62 °C.
- Batch MS-2609-017 has been put on hold in the reactor pending QA evaluation.
- Maintenance has been informed to inspect valve TCV-201.

This is an unplanned deviation. The higher temperature may affect crystal form / particle size and impurity profile, so GMP impact is potential until the in-process test results are reviewed.

Regards,
Ravi Kumar
Production Officer, Production Department
"""


def chat(message, state, file=None):
    data = {"message": message, "form": json.dumps(state["form"]), "history": json.dumps(state["history"]),
            "user_overrides": json.dumps(state["overrides"])}
    r = httpx.post(f"{API}/ai/chat", data=data, files=file, timeout=120)
    r.raise_for_status()
    res = r.json()
    state.update(form=res["form"], overrides=res["user_overrides"])
    state["changes"] += res["changes"]
    state["history"] += [{"role": "user", "content": message}, {"role": "assistant", "content": res["reply"]}]
    print(f"\n>> {message[:70]!r}\n   intent={res['intent']} action={res['action']}")
    print("   " + res["reply"].replace("\n", "\n   "))
    for c in res["changes"]:
        print(f"   · {c['field']}: {c['old']!r} -> {c['new']!r} [{c['source']}]")
    return res


def main():
    s = {"form": {}, "overrides": {}, "changes": [], "history": []}
    chat("Please log this deviation:\n" + EMAIL, s)
    for cmd in ["change batch number to B-2026-114",
                "clear the equipment ID",
                "assign Dr. Priya Rao as investigator",
                "set HA notification to To be evaluated",
                "severity should be Critical because product was quarantined",
                "status to Open",
                "set rpn to 5"]:  # must be rejected: rule-derived field
        chat(cmd, s)
    chat("re-assess the risk", s)
    assert chat("save it", s)["action"] == "save"

    saved = httpx.post(f"{API}/deviations", json={"form": s["form"], "user_overrides": s["overrides"],
                                                   "changes": s["changes"]}).json()
    dev_id = saved["form"]["deviation_id"]
    print(f"\nSAVED {dev_id}: class={saved['form']['severity_classification']} rpn={saved['form']['rpn']}")

    loaded = httpx.get(f"{API}/deviations/{dev_id}").json()
    s2 = {"form": loaded["form"], "overrides": loaded["user_overrides"], "changes": [], "history": []}
    chat("set quarantine reference to QR-2026-077", s2)
    httpx.put(f"{API}/deviations/{dev_id}", json={"form": s2["form"], "user_overrides": s2["overrides"],
                                                   "changes": s2["changes"]}).raise_for_status()
    audit = httpx.get(f"{API}/deviations/{dev_id}/audit").json()
    print(f"\nAUDIT {dev_id}: {len(audit)} rows (last 8):")
    for a in audit[-8:]:
        print(f"   {a['field']:<26} {str(a['old_value'])[:20]!r:>24} -> {str(a['new_value'])[:30]!r:<32} "
              f"{a['source']:<17} {str(a['instruction'])[:45]!r}")
    print("\nAll deviations:", [d["deviation_id"] for d in httpx.get(f"{API}/deviations").json()])


if __name__ == "__main__":
    try:
        main()
    except httpx.HTTPError as exc:
        sys.exit(f"Backend not reachable or returned an error: {exc}")
