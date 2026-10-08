"""Single source for the agent-mission data layer (SYNTHETIC).

Each product desk in Capital Markets keeps its own view of a client: DCM wants to pitch,
Credit Risk wants to hold, Global Markets has a hedge proposal, the Control Room may have a
restriction, AML/KYC may have a refresh or a screening alert. Each view is correct on its own
terms. No single system reconciles them. That gap is what the agent missions exist for.

This script writes the same facts to every layer that needs them, so the layers can never disagree:

    Fabric IQ    data/fabric-iq/line_positions.csv          (governed table, loaded by deploy_fabric.py)
    BFF bundle   app/src/bff/app/line_data.py                (the same rows, for the deterministic packet)
    Work IQ      data/work-iq/mission_emails.json            (the unstructured context no table holds)
    Foundry IQ   data/foundry-iq/cm_policies.json            (+ CP-016, CP-017)

    python data/mission_data.py          # writes all four, idempotent
    python data/mission_data.py --data-only  # only the Fabric CSV and Foundry JSON
    python data/mission_data.py --data-only --check  # read-only freshness check

Every client figure quoted here comes from the existing governed data (skill_data / market_data);
the new facts are business-line stances, a few dated events and colleague correspondence.
The Bank is a fictional institution; the issuers are real public companies used only so
live Web IQ returns genuine public news. Every internal fact is invented.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

from scenario_facts import FACTS

ROOT = Path(__file__).resolve().parent
AS_OF = FACTS["as_of"]

# client_id, business_line, stance, proposed_action, rationale, policy_ref, owner_alias, status_date
# stance: Pitch | Propose | Support | Clear | Review | Hold | Restricted
LINES: list[tuple[str, str, str, str, str, str, str, str]] = [
    # --- CLI-1001 Gibson Energy (hero) ------------------------------------------------------------
    ("CLI-1001", "DCM / Coverage", "Pitch", "Revolver upsize CAD 1.10bn -> 1.35bn + 1-year extension (OPP-4471)",
     "Client asked for the upsize ahead of the 2027 refinancing; CFO / Treasurer meeting 8 October.", "CP-003", "sasha.ouellet", "2026-10-02"),
    ("CLI-1001", "Credit Risk", "Hold", "Size to what clears the leverage covenant",
     "Full upsize pro-forma 4.59x vs 4.50x maximum (breach); largest increase that clears fully drawn is CAD 195.8m.", "CP-005", "vance.deleon", "2026-10-03"),
    ("CLI-1001", "Global Markets", "Propose", "Commodity + FX hedging overlay (OPP-4472)",
     "WCS differential and USD exposure on the Chauvin assets; proposal drafted.", "CP-010", "quinn.campbell", "2026-09-17"),
    ("CLI-1001", "Control Room", "Restricted", "CR-2026-0184 live until 2026-11-10",
     "Pitch on public information only; hedging solicitation needs Control Room clearance; research may not update the target.", "CP-008", "control.room", "2026-10-01"),
    ("CLI-1001", "AML / KYC", "Review", "Periodic KYC refresh due 2026-11-25",
     "Refresh file opened; no blocker yet.", "CP-006", "kyc.ops", "2026-09-30"),
    # --- CLI-1002 Keyera --------------------------------------------------------------------------
    ("CLI-1002", "DCM / Coverage", "Pitch", "Revolver increase to close the wallet gap",
     "Largest recorded gap to the 25% wallet target is on the revolver.", "CP-003", "sasha.ouellet", "2026-09-29"),
    ("CLI-1002", "Credit Risk", "Review", "Single-name limit 85.8% used (Amber)",
     "CAD 514.8m of 600.0m used; any increase needs a limit review first.", "CP-001", "vance.deleon", "2026-09-30"),
    ("CLI-1002", "Control Room", "Review", "Inquiry CRI-2026-0207 opened",
     "Possible material non-public information reported from a client call on 2026-09-30; under review.", "CP-009", "control.room", "2026-10-01"),
    # --- CLI-1003 Whitecap ------------------------------------------------------------------------
    ("CLI-1003", "DCM / Coverage", "Pitch", "Revolver extension and upsize",
     "Wallet gap on the revolver; client relationship strong.", "CP-003", "sasha.ouellet", "2026-09-26"),
    ("CLI-1003", "Credit Risk", "Hold", "Covenant conversation before any new money",
     "Leverage covenant 3.42x moves to 4.00x vs 4.00x maximum on the overnight oil shock (-14.5% EBITDA).", "CP-005", "vance.deleon", "2026-10-05"),
    ("CLI-1003", "Global Markets", "Propose", "Crude collar programme for 2027 production",
     "Hedging after a supply shock - appropriateness review required.", "CP-010", "quinn.campbell", "2026-10-05"),
    # --- CLI-1004 Secure Waste --------------------------------------------------------------------
    ("CLI-1004", "Global Markets", "Propose", "Commodity derivatives - new ISDA schedule",
     "Largest wallet gap is commodity derivatives.", "CP-010", "quinn.campbell", "2026-09-24"),
    ("CLI-1004", "AML / KYC", "Hold", "Beneficial-ownership refresh before any new product",
     "KYC refresh due 2026-11-25 and a new 10%+ shareholder reported; documents outstanding.", "CP-006", "kyc.ops", "2026-10-02"),
    ("CLI-1004", "Credit Risk", "Support", "Within limits (83.5%)", "Covenant comfortable under the shock.", "CP-001", "vance.deleon", "2026-09-30"),
    # --- CLI-1005 Stella-Jones --------------------------------------------------------------------
    ("CLI-1005", "DCM / Coverage", "Pitch", "Green bond underwriting mandate",
     "Wallet gap on DCM underwriting; client exploring a green bond.", "CP-003", "sasha.ouellet", "2026-09-25"),
    ("CLI-1005", "Credit Risk", "Hold", "Leverage covenant tight (3.96x vs 4.00x)",
     "Any incremental debt must be pro-formed first.", "CP-005", "vance.deleon", "2026-09-30"),
    ("CLI-1005", "Sustainable Finance", "Review", "SLL KPI verification late",
     "2025 sustainability-linked loan KPI verification not received; margin step-up and framework review before any green label.", "CP-011", "sf.desk", "2026-09-29"),
    # --- CLI-1006 Russel Metals -------------------------------------------------------------------
    ("CLI-1006", "DCM / Coverage", "Pitch", "Acquisition financing / bond underwriting",
     "Public announcement of an acquisition; wallet gap on DCM underwriting.", "CP-003", "sasha.ouellet", "2026-10-01"),
    ("CLI-1006", "Credit Risk", "Hold", "Shocked leverage 4.02x vs 4.00x maximum",
     "Breach under the scenario before any acquisition debt.", "CP-005", "vance.deleon", "2026-10-05"),
    ("CLI-1006", "Equity Research", "Clear", "Initiation note on the acquisition",
     "Public information only; publishing as scheduled.", "CP-008", "robin.kline", "2026-10-02"),
    # --- CLI-1007 Cascades ------------------------------------------------------------------------
    ("CLI-1007", "DCM / Coverage", "Pitch", "Revolver renewal and increase",
     "Wallet gap on the revolver.", "CP-003", "sasha.ouellet", "2026-09-22"),
    ("CLI-1007", "Credit Risk", "Hold", "Watchlist, rating IG-10 deteriorating",
     "No new money until the mill-closure plan and Q3 results are reviewed.", "CP-001", "vance.deleon", "2026-09-30"),
    ("CLI-1007", "Global Markets", "Propose", "USD/CAD forwards programme", "Wallet gap on FX.", "CP-010", "quinn.campbell", "2026-09-23"),
    ("CLI-1007", "Sustainable Finance", "Review", "SLL KPI missed (water intensity)",
     "Margin step-up applies; client asked to reset the KPI.", "CP-011", "sf.desk", "2026-09-18"),
    # --- CLI-1008 Ag Growth -----------------------------------------------------------------------
    ("CLI-1008", "Global Markets", "Propose", "Commodity derivatives (steel input hedges)",
     "Largest wallet gap is commodity derivatives.", "CP-010", "quinn.campbell", "2026-09-21"),
    ("CLI-1008", "Credit Risk", "Hold", "Watchlist; single-name 91.5% used (Amber)",
     "No new PSE without a limit review.", "CP-001", "vance.deleon", "2026-09-30"),
    ("CLI-1008", "AML / KYC", "Hold", "Sanctions screening alert SA-2026-077",
     "Payment counterparty flagged in screening; new products paused until disposition.", "CP-007", "kyc.ops", "2026-10-02"),
    # --- CLI-1009 North West Company (books agree) ------------------------------------------------
    ("CLI-1009", "Global Markets", "Propose", "Renew USD/CAD forward programme",
     "Routine annual renewal; client asked for it.", "CP-010", "quinn.campbell", "2026-09-28"),
    ("CLI-1009", "Credit Risk", "Support", "Within limits (45.6%)", "Interest coverage comfortable.", "CP-001", "vance.deleon", "2026-09-30"),
    ("CLI-1009", "AML / KYC", "Clear", "KYC current", "Next refresh 2027-03-26.", "CP-006", "kyc.ops", "2026-09-30"),
    # --- CLI-1010 Superior Plus -------------------------------------------------------------------
    ("CLI-1010", "DCM / Coverage", "Pitch", "Bond underwriting mandate",
     "Largest wallet gap is DCM underwriting.", "CP-003", "sasha.ouellet", "2026-09-27"),
    ("CLI-1010", "Credit Risk", "Support", "Within limits (66.8%)", "Covenant comfortable.", "CP-001", "vance.deleon", "2026-09-30"),
    ("CLI-1010", "Global Markets", "Review", "Propane hedge execution complaint",
     "Client raised a complaint about Q2 execution; review open.", "CP-010", "quinn.campbell", "2026-09-19"),
]

SELL = {"Pitch", "Propose"}
BLOCK = {"Hold", "Restricted"}


def conflicts() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for cid in {r[0] for r in LINES}:
        st = {r[2] for r in LINES if r[0] == cid}
        out[cid] = bool(st & SELL) and bool(st & (BLOCK | {"Review"}))
    return out


# --------------------------------------------------------------------------- Work IQ
PEOPLE_EXTRA = [{"alias": "admin", "displayName": "CM Operations (demo)", "title": "Demo operator", "role": "ops"}]


def em(i, cid, cat, frm, to, cc, when, subject, body, importance="normal"):
    return {"id": f"EM-M{i:02d}", "client_id": cid, "category": cat, "from": frm, "to": to, "cc": cc + ["admin"],
            "sentDateTime": when, "importance": importance, "subject": subject, "body": body}


EMAILS = [
    em(1, "CLI-1002", "compliance_and_control", "sasha.ouellet", ["sydney.mattos"], [], "2026-10-01T14:20:00Z",
       "Keyera - something their CFO said on Tuesday's call; I have gone to the Control Room",
       "Sydney,\n\nOn Tuesday's call Keyera's CFO said, unprompted, that they are 'looking at something much bigger in NGL in Q1' "
       "and would want us 'close to it'. That may be material non-public information, so I reported it to the Control Room the same "
       "afternoon (they opened inquiry CRI-2026-0207) and I have not written it down anywhere else.\n\nPractical effect: please do "
       "not use it in the revolver pitch, and do not repeat it in any client email. The pitch stays on the public numbers - the "
       "wallet gap on the revolver - and any limit question goes to Vance first because the single name is already Amber.\n\nSasha",
       "high"),
    em(2, "CLI-1003", "credit_and_limits", "vance.deleon", ["sasha.ouellet"], ["sydney.mattos"], "2026-10-05T12:05:00Z",
       "Whitecap - covenant first, not the upsize",
       "Sasha,\n\nOn this morning's oil move Whitecap's leverage covenant goes from 3.42x to the 4.00x maximum on our shocked "
       "EBITDA. Their treasurer already asked on last month's call whether we would 'look at a reset if crude rolls over' - so "
       "they are expecting the conversation.\n\nPlease lead with covenant headroom and a reset discussion with Credit in the room. "
       "No upsize or extension pitch until that is settled. Quinn's collar idea is sensible in principle but it goes through the "
       "appropriateness process, not into the same meeting as a covenant ask.\n\nVance", "high"),
    em(3, "CLI-1004", "compliance_and_control", "sydney.mattos", ["quinn.campbell"], ["vance.deleon"], "2026-10-02T15:40:00Z",
       "Secure Waste - hold the derivatives ISDA until KYC is done",
       "Quinn,\n\nKYC Ops tell me Secure Waste reported a new shareholder above 10% last month and the beneficial-ownership "
       "documents are still outstanding; the periodic refresh is due 25 November anyway.\n\nPlease park the commodity "
       "derivatives schedule until the refresh is complete. We can tell the client the paperwork is the gating item - that is "
       "true and it is not sensitive - but no product proposal before it clears.\n\nSydney"),
    em(4, "CLI-1005", "client_interaction", "sasha.ouellet", ["sydney.mattos"], [], "2026-09-29T18:10:00Z",
       "Stella-Jones - they want a green bond; their SLL KPI verification is still missing",
       "Sydney,\n\nStella-Jones' treasurer asked whether we would lead a green bond in Q1. Two problems before we pitch:\n\n"
       "1. Their sustainability-linked loan KPI verification for 2025 has not come in, so the margin step-up applies and the "
       "Sustainable Finance desk will not put a green label on anything until the framework is reviewed.\n2. Leverage is "
       "3.96x against a 4.00x covenant - any new debt has to be pro-formed with Credit first.\n\nI'd rather offer to help them "
       "fix the verification first. Thoughts?\n\nSasha"),
    em(5, "CLI-1006", "credit_and_limits", "vance.deleon", ["sydney.mattos"], ["robin.kline"], "2026-10-02T13:30:00Z",
       "Russel Metals - acquisition financing ask must come through Credit",
       "Sydney,\n\nThe acquisition is public now, so Robin can publish, and Sasha is keen to pitch the financing. Before anyone "
       "does: on today's scenario their leverage goes to 4.02x against a 4.00x maximum before a single dollar of acquisition "
       "debt. Any financing ask is a Credit conversation first, with an equity or asset-sale component on the table.\n\n"
       "Separately - please keep Research and the deal team apart on this one. Robin's note is public-side.\n\nVance"),
    em(6, "CLI-1007", "market_and_hedging", "quinn.campbell", ["sydney.mattos"], ["vance.deleon"], "2026-09-23T16:00:00Z",
       "Cascades - FX forwards, and the complaint from last year",
       "Sydney,\n\nCascades would benefit from a USD/CAD forwards programme. One caution: they complained last year that an "
       "option structure we sold them was more complex than they needed, so the appropriateness file needs to be clean and "
       "simple this time.\n\nAlso - they are on the credit watchlist and Vance does not want new money until the mill-closure "
       "plan is reviewed. FX forwards add PSE, so this may need to wait too.\n\nQuinn"),
    em(7, "CLI-1007", "client_interaction", "sasha.ouellet", ["sydney.mattos"], [], "2026-09-18T20:15:00Z",
       "Cascades - they missed the water-intensity KPI and want to reset it",
       "Sydney,\n\nCascades missed the water-intensity KPI on their sustainability-linked loan; the margin step-up kicks in. "
       "Their CFO asked whether we would 'just reset the KPI' as part of the revolver renewal. That is a Sustainable Finance "
       "framework decision, not something we can trade for a renewal - I said we'd come back.\n\nSasha"),
    em(8, "CLI-1008", "compliance_and_control", "sydney.mattos", ["quinn.campbell"], ["vance.deleon"], "2026-10-02T17:25:00Z",
       "Ag Growth - pause the commodity hedge proposal (screening alert)",
       "Quinn,\n\nSanctions screening raised alert SA-2026-077 on one of Ag Growth's payment counterparties - a dealer in a "
       "jurisdiction on the watch list. Compliance is working the disposition. Until it clears, no new products, and please do "
       "not mention the alert to the client - that is Compliance's call.\n\nOn top of that the single name is at 91.5% and they "
       "are on the watchlist, so the PSE would need a limit review anyway.\n\nSydney", "high"),
    em(9, "CLI-1009", "client_interaction", "quinn.campbell", ["sydney.mattos"], [], "2026-09-28T14:45:00Z",
       "North West Company - forwards renewal, all straightforward",
       "Sydney,\n\nNorth West asked us to renew their USD/CAD forward programme on the same terms as last year. Credit is fine "
       "with it (single name at 45.6%), KYC is current, and nothing else is going on with the name. I'll send the renewal "
       "through the usual appropriateness check.\n\nQuinn"),
    em(10, "CLI-1010", "client_interaction", "sydney.mattos", ["sasha.ouellet"], ["quinn.campbell"], "2026-09-19T19:30:00Z",
       "Superior Plus - fix the propane hedge complaint before we pitch the bond",
       "Sasha,\n\nSuperior Plus' CFO is unhappy about how we executed their propane hedges in Q2 and has asked for a pricing "
       "review. Quinn has the review open. I don't want us walking in with a bond mandate pitch while that is unresolved - "
       "close out the review, then talk about the bond.\n\nSydney"),
]

# --------------------------------------------------------------------------- Foundry IQ
POLICIES = [
    {"id": "CP-016", "title": "AI Agents in Coverage Decisions - Harness, Barrier Review and Human Approval",
     "category": "information_barrier", "effective_date": "2026-10-01", "owner": "Chief Data and AI Officer, Capital Markets",
     "applies_to": ["Corporate Banking", "Global Markets", "Research", "Credit Risk Management", "Compliance"],
     "regulatory_anchor": "OSFI Guideline E-23 (model risk); NI 31-103 conflicts provisions; CIRO record-keeping rules",
     "content": "PURPOSE. Sets the conditions under which an AI agent may prepare coverage work: briefings, opportunity "
                "assessments, risk reviews and client follow-ups.\n\nRULE 1 - PREPARE, NEVER ACT. An agent may research, reconcile and "
                "draft. It may never send a communication, commit capital, quote a price or size, approve a limit, wall-cross anyone, "
                "or contact a client.\n\nRULE 2 - GOVERNED FIGURES. Exposure, limits, covenants and pro-formas come from the governed "
                "data layer and the Bank's own calculations; the agent quotes them, never recomputes or replaces them. Every figure "
                "must be traceable to governed data or a cited source.\n\nRULE 3 - INFORMATION BARRIER. Any possible material "
                "non-public information an agent finds is routed to the Control Room and never used in a pitch or a client "
                "communication (CP-008, CP-009). Restricted-list subject matter and wall-crossing mechanics never appear in "
                "client copy. Client copy passes deterministic checks and the barrier reviewer before a banker sees it.\n\n"
                "RULE 4 - HUMAN DECISION AND AUDIT. A named banker approves, sends back or escalates every agent output; the run, "
                "the guardrail verdict and the reviewer verdict are retained under CP-014.\n\nRULE 5 - PUBLIC-SIDE DEFAULT. Agents run "
                "on behalf of the signed-in banker and see only what that banker may see. An agent never asks a colleague to share "
                "wall-crossed context, never infers the subject of a restriction, and treats the absence of information as absence - "
                "not as clearance.\n\nRULE 6 - TESTING AND CHANGE CONTROL. Agent instructions are versioned. Before a change goes "
                "live it is run against a fixed case set that includes a restricted name, a possible-MNPI disclosure, a covenant "
                "breach and a clean case; any regression in barrier or guardrail outcomes blocks the change."},
    {"id": "CP-017", "title": "Cross-Line Conflicts - Which Position Binds When Desks Disagree",
     "category": "approval_authority", "effective_date": "2026-10-01", "owner": "Head of Corporate Coverage",
     "applies_to": ["Corporate Banking", "Global Markets", "Research", "Credit Risk Management", "Compliance"],
     "regulatory_anchor": "OSFI Guideline B-20 principles applied to wholesale credit; NI 31-103 conflicts provisions",
     "content": "PURPOSE. Business lines hold different, individually valid positions on the same client. This policy sets the "
                "order in which they bind before anyone contacts the client.\n\nRULE 1 - ORDER OF PRECEDENCE. (1) Control Room "
                "restrictions and inquiries (CP-008, CP-009); (2) AML, KYC and sanctions holds (CP-006, CP-007); (3) Credit Risk "
                "holds on limits and covenants (CP-001, CP-005); (4) product appropriateness and open complaints (CP-010); "
                "(5) sustainability-linked commitments (CP-011); only then (6) origination and product proposals.\n\nRULE 2 - "
                "ONE CONVERSATION. Where lines conflict, the relationship owner leads one client conversation that respects every "
                "binding position, instead of separate desk calls.\n\nRULE 3 - NO TRADING OF CONDITIONS. A covenant reset, KPI "
                "reset, KYC exception or restriction clearance is never offered or traded in exchange for a mandate.\n\nRULE 4 - "
                "SAY WHAT IS TRUE AND NOT SENSITIVE. The client may be told that paperwork, an internal review or an approval is "
                "the gating item; never the existence of an inquiry, alert or restriction.\n\nRULE 5 - ESCALATION. If the binding "
                "position blocks a mandate the client has asked for, the relationship owner escalates to the Head of Corporate "
                "Coverage and the owner of the binding position within two business days, with a written note of the options (for "
                "example a smaller facility that clears the covenant, or a sequence: KYC first, then the product).\n\nRULE 6 - "
                "RECORD. The reconciliation - which positions were considered, which one bound and why - is recorded in the coverage "
                "memo (CP-014) so the next banker does not repeat the conflict."},
]


def build_outputs(data_only: bool = False) -> dict[Path, str]:
    with (ROOT / "fabric-iq" / "clients.csv").open(encoding="utf-8", newline="") as stream:
        names = {r["client_id"]: r["client_name"] for r in csv.DictReader(stream)}
    cols = ["client_id", "client_name", "business_line", "stance", "proposed_action", "rationale", "policy_ref", "owner_alias",
             "status_date", "lines_conflict"]
    flags = conflicts()
    rows = [dict(zip(cols, [r[0], names[r[0]], *r[1:], "Y" if flags[r[0]] else "N"])) for r in LINES]
    csv_text = io.StringIO(newline="")
    writer = csv.DictWriter(csv_text, fieldnames=cols)
    writer.writeheader()
    writer.writerows(rows)
    outputs = {ROOT / "fabric-iq" / "line_positions.csv": csv_text.getvalue()}

    pp = ROOT / "foundry-iq" / "cm_policies.json"
    pol = json.loads(pp.read_text(encoding="utf-8"))
    ids = {p["id"] for p in POLICIES}
    pol["documents"] = sorted([d for d in pol["documents"] if d["id"] not in ids] + POLICIES, key=lambda d: d["id"])
    outputs[pp] = json.dumps(pol, indent=2, ensure_ascii=False) + "\n"
    if not data_only:
        bundle = ROOT.parent / "app" / "src" / "bff" / "app" / "line_data.py"
        outputs[bundle] = (
            '"""Business-line positions per client (generated by data/mission_data.py - do not edit). SYNTHETIC."""\n\n'
            f"AS_OF = {AS_OF!r}\nLINE_POSITIONS = {json.dumps(rows, indent=1, ensure_ascii=False)}\n"
        )
        src = json.loads((ROOT / "work-iq" / "emails.json").read_text(encoding="utf-8"))
        mail = {
            "$schema_note": "Agent-mission correspondence for the nine non-hero clients. Same schema as emails.json; seed with "
                            "SEED_FILE=mission_emails.json python seed_work_iq.py --only mail.",
            "scenario": pol["scenario"], "as_of": AS_OF, "categories": src["categories"],
            "people": src["people"] + PEOPLE_EXTRA, "emails": EMAILS,
        }
        outputs[ROOT / "work-iq" / "mission_emails.json"] = json.dumps(mail, indent=2, ensure_ascii=False) + "\n"
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-only", action="store_true",
                        help="Only generate Fabric CSV and Foundry JSON; never read/write Work IQ or BFF outputs")
    parser.add_argument("--check", action="store_true",
                        help="Read-only: fail if any selected output is missing or stale")
    args = parser.parse_args()
    outputs = build_outputs(data_only=args.data_only)
    if args.check:
        stale = [
            str(path.relative_to(ROOT.parent))
            for path, text in outputs.items()
            if not path.exists() or path.read_text(encoding="utf-8") != text.replace("\r\n", "\n")
        ]
        print("FAIL stale: " + ", ".join(stale) if stale else "OK   mission outputs match the source")
        return 1 if stale else 0
    for path, text in outputs.items():
        path.write_text(text, encoding="utf-8", newline="")
        print(f"wrote {path.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
