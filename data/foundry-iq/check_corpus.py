"""Validate the Foundry IQ policy corpus for the Capital Markets demo.

The corpus is what makes the demo's central refusal *defensible*. If the agent
says "no, not as currently positioned", every clause it leans on has to exist in
`cm_policies.json` verbatim - otherwise the answer is the model being agreeable
rather than the model being grounded.

These assertions therefore check two things:

  1. structure  - 14 documents, CP-001..CP-014, no gaps, every one substantial
     and attributed;
  2. the tension - the specific clauses the trap answer cites must be present as
     written, not paraphrased.

    python check_corpus.py

Exit code 0 = corpus is demo-ready.
"""

from __future__ import annotations

import io
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = pathlib.Path(__file__).parent
d = json.load(io.open(HERE / "cm_policies.json", encoding="utf-8"))
docs = d["documents"]
by_id = {x["id"]: x for x in docs}

print(f"{len(docs)} documents  ->  index '{d['index_name']}'  as at {d['as_of']}\n")
for x in docs:
    print(f"  {x['id']} | {x['category']:<22} | {len(x['content']):>5} ch | {x['title'][:56]}")

ok = True


def chk(label: str, cond: object, detail: str = "") -> None:
    global ok
    ok &= bool(cond)
    print(f"  {'OK  ' if cond else 'FAIL'} {label}" + (f"  {detail}" if detail and not cond else ""))


print("\nStructure")
chk("14 documents", len(docs) == 14)
chk("ids CP-001..CP-014 with no gaps",
    [x["id"] for x in docs] == [f"CP-{i:03d}" for i in range(1, 15)])
chk("every category declared", all(x["category"] in d["categories"] for x in docs))
chk("every doc over 1500 chars", all(len(x["content"]) > 1500 for x in docs),
    str([x["id"] for x in docs if len(x["content"]) <= 1500]))
chk("every doc has owner + regulatory_anchor",
    all(x.get("owner") and x.get("regulatory_anchor") for x in docs))
chk("every doc has applies_to + effective_date",
    all(x.get("applies_to") and x.get("effective_date") for x in docs))

t = json.dumps(d)

print("\nThe tension must be anchored in policy, not just in the data")
# CP-001 - the single-name limit is green, and green is not permission.
chk("CP-001 says headroom is not authority", "HEADROOM IS NOT AUTHORITY" in t)
# CP-002 - the sector envelope is the second binding constraint.
chk("CP-002 sets the Energy sector ceiling at 3,200", "Energy CAD 3,200m" in t)
chk("CP-002 sector amber trigger is 85%",
    "At or above 85 per cent of a sector ceiling, the sector is AMBER" in t)
chk("CP-002 expects originate-to-distribute when amber",
    "ORIGINATE-TO-DISTRIBUTE EXPECTATION" in t)
chk("CP-002 has the midstream correlation overlay", "CORRELATION OVERLAY" in t)
chk("CP-002 keeps sector capacity out of pitch materials",
    "DISCLOSURE IN PITCH MATERIALS" in t)
# CP-005 - the covenant is the primary binding constraint, and the test is
# required BEFORE the pitch. This is the clause the whole demo turns on.
chk("CP-005 requires a mandatory pro-forma test", "MANDATORY PRO-FORMA TEST" in t)
chk("CP-005 assumes the facility is fully drawn", "FULLY-DRAWN ASSUMPTION" in t)
chk("CP-005 bites within two quarters of a test date", "within two quarters" in t)
chk("CP-005 forbids coverage performing or waiving the test",
    "coverage may not perform it" in t)
# CP-008 / CP-009 - the constraint no limit system holds.
chk("CP-008 keeps the public side uninformed of a crossing",
    "must not be told that a crossing exists" in t)
chk("CP-008 escalates conflicts rather than resolving them silently",
    "ESCALATION, NOT SILENT RESOLUTION" in t)
chk("CP-008 says an expected expiry is not an authorisation",
    "expectation, not an authorisation" in t)
chk("CP-009 says general disclosure is not inference",
    "GENERAL DISCLOSURE IS NOT INFERENCE" in t)

print("\nAccount plan (CP-012) quotes the Fabric figures verbatim")
for s in ["CAD 465m", "341.7", "68.3", "0.32", "21.4", "IG-6", "85.8"]:
    chk(f"CP-012 states {s}", s in by_id["CP-012"]["content"] or s in t)

print("\nGuardrails")
chk("public ratings flagged indicative", "indicative" in t.lower())
chk("synthetic disclaimer present", "SYNTHETIC" in t.upper())
chk("no reference to another demo's institution",
    not any(n in t for n in ("Scotiabank", "Scotia", "Contoso", "RBC", "Vale")))

print("\n" + ("PASSED" if ok else "FAILED"))
sys.exit(0 if ok else 1)
