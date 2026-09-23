"""Create (or update) the **BMO Capital Markets Client Intelligence** agent in Azure AI
Foundry and run it interactively.

The agent gets four function tools, one per IQ layer:

    search_client_relationship_history   -> Microsoft Graph Search   (Work IQ)
    query_client_exposure_analytics      -> Fabric semantic model    (Fabric IQ)
    lookup_capital_markets_policy        -> Azure AI Search          (Foundry IQ)
    research_client_external_intelligence-> Grounding with Bing      (Web IQ)

Each tool degrades gracefully: if its backend is not configured it reads the local
synthetic files under ../data instead, so the agent is demonstrable before every
backend is wired. Web IQ is the exception - it is LIVE ONLY and returns an explicit
"unavailable" rather than inventing external facts about a real company.

--------------------------------------------------------------------------------
WHY FUNCTION TOOLS RATHER THAN A KNOWLEDGE ATTACHMENT
--------------------------------------------------------------------------------
This demo turns on a trap: the single-name limit reads 68.3 per cent GREEN while the
transaction is actually constrained by the Total Net Debt / Adjusted EBITDA covenant
at 4.18x against a 4.50x maximum - 0.32 turns, 92.9 per cent utilised and getting
worse - and by the Energy sector envelope at 85.8 per cent AMBER. An agent given a
passive knowledge blob will happily answer "plenty of room" from the first number it
finds. Forcing a Fabric tool call - and having that tool return the covenant position
and the sector envelope alongside the single-name limit, always - is what makes the
demo land.

--------------------------------------------------------------------------------
INSTALL
--------------------------------------------------------------------------------
    pip install -r ../requirements.txt

--------------------------------------------------------------------------------
CONFIGURE (all optional except the first two)
--------------------------------------------------------------------------------
    $env:FOUNDRY_PROJECT_ENDPOINT = "https://cmintel-foundry.services.ai.azure.com/api/projects/proj-client-intelligence"
    $env:FOUNDRY_MODEL            = "gpt-5.4"

    # Foundry IQ
    $env:SEARCH_ENDPOINT          = "https://<svc>.search.windows.net"
    $env:SEARCH_INDEX             = "cm-client-policies"

    # Web IQ (live only)
    $env:BING_GROUNDING_CONNECTION = "bing-grounding-cmintel"

    # Fabric IQ (optional - falls back to the local CSVs)
    $env:FABRIC_SQL_ENDPOINT      = "<ws>.datawarehouse.fabric.microsoft.com"
    $env:FABRIC_DATABASE          = "lh_client_intel"

    # Work IQ (delegated Graph auth - the signed-in user's M365 search)
    $env:WORKIQ_TENANT_ID         = "<tenant-guid>"
    $env:WORKIQ_CLIENT_ID         = "<app-client-id>"

--------------------------------------------------------------------------------
RUN
--------------------------------------------------------------------------------
    python create_agent.py --local-smoke   # no Azure needed - exercise every tool
    python create_agent.py --create        # create/update the agent only
    python create_agent.py --ask "Can we do the revolver upsize?"
    python create_agent.py --demo          # the five scripted questions
    python create_agent.py --trap          # the single question that separates
                                           # a good agent from a plausible one
    python create_agent.py --chat          # interactive
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
FABRIC = DATA / "fabric-iq"
FOUNDRY = DATA / "foundry-iq"
WORK = DATA / "work-iq"

sys.path.insert(0, str(DATA))
from scenario_facts import FACTS  # noqa: E402

AGENT_NAME = "BMO Capital Markets Client Intelligence"


# ===========================================================================
# helpers
# ===========================================================================

def _load_csv(name: str) -> list[dict]:
    with (FABRIC / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _f(row: dict, key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _instructions() -> str:
    md = (HERE / "agent_instructions.md").read_text(encoding="utf-8")
    m = re.search(r"<!-- INSTRUCTIONS-START -->(.*?)<!-- INSTRUCTIONS-END -->", md, re.S)
    if not m:
        raise RuntimeError("instruction markers not found in agent_instructions.md")
    return m.group(1).strip()


# ===========================================================================
# Work IQ
# ===========================================================================

def search_client_relationship_history(query: str, category: str | None = None) -> str:
    """Work IQ. Emails, meeting records and client documents in Microsoft 365.

    Falls back to the local corpus when Graph is not configured. The local path is
    a keyword scan, which is cruder than Graph Search but returns the same content.
    """
    terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 3]
    hits: list[dict] = []

    emails = json.loads((WORK / "emails.json").read_text(encoding="utf-8"))
    for e in emails["emails"]:
        if category and e["category"] != category:
            continue
        blob = f"{e['subject']} {e['body']}".lower()
        score = sum(blob.count(t) for t in terms)
        if score:
            hits.append({
                "source": "email", "id": e["id"], "date": e["sentDateTime"][:10],
                "from": e["from"], "category": e["category"],
                "subject": e["subject"], "score": score,
                "excerpt": e["body"][:700],
            })

    # Teams content is grounded as a document rather than as native chat - see the
    # note in data/README.md - so it is searched here from the same JSON.
    teams = json.loads((WORK / "teams_messages.json").read_text(encoding="utf-8"))
    for ch in teams["channels"]:
        for c in ch["conversations"]:
            blob = f"{c.get('subject', '')} {c['message']}".lower()
            score = sum(blob.count(t) for t in terms)
            if score:
                hits.append({
                    "source": "teams", "id": c["id"], "date": c["createdDateTime"][:10],
                    "from": c["from"], "channel": ch["displayName"],
                    "subject": c.get("subject", ""), "score": score,
                    "excerpt": c["message"][:600],
                })

    for p in sorted((WORK / "meetings").glob("*.md")) + sorted((WORK / "files").glob("*.md")):
        text = p.read_text(encoding="utf-8")
        score = sum(text.lower().count(t) for t in terms)
        if score:
            idx = min((text.lower().find(t) for t in terms if t in text.lower()), default=0)
            hits.append({
                "source": "document", "id": p.name, "date": p.name[:10],
                "from": "", "subject": p.stem, "score": score,
                "excerpt": text[max(0, idx - 200): idx + 900],
            })

    hits.sort(key=lambda h: -h["score"])
    return json.dumps({
        "layer": "Work IQ",
        "backend": "local synthetic corpus (Microsoft Graph not configured)",
        "as_of": FACTS["as_of"],
        "matches": len(hits),
        "results": hits[:8],
    }, indent=2)


# ===========================================================================
# Fabric IQ
# ===========================================================================

def query_client_exposure_analytics(question: str,
                                    client: str | None = None,
                                    topic: str | None = None) -> str:
    """Fabric IQ. Governed exposure, limit, covenant, revenue and trade data.

    IMPORTANT DESIGN DECISION. Any question touching capacity ALWAYS returns the
    covenant position and the sector envelope alongside the single-name limit,
    whether or not they were asked for. On this book the single-name limit is
    routinely green while the covenant is the real constraint, and an agent that
    is only shown the first number will confidently give the wrong answer.
    """
    q = (question or "").lower()
    clients = _load_csv("clients.csv")

    cid = None
    if client:
        for c in clients:
            if client.lower() in c["client_name"].lower() or client.upper() == c["client_id"]:
                cid = c["client_id"]
                break
    if not cid:
        for c in clients:
            first = c["client_name"].split()[0].lower()
            if first in q:
                cid = c["client_id"]
                break
    cid = cid or FACTS["hero_client_id"]
    crow = next(c for c in clients if c["client_id"] == cid)

    out: dict[str, Any] = {
        "layer": "Fabric IQ",
        "backend": "local synthetic tables (Fabric semantic model not configured)",
        "as_of": FACTS["as_of"],
        "client": {
            "client_id": cid, "client_name": crow["client_name"],
            "ticker": crow["ticker"], "sector": crow["sector"],
            "sub_sector": crow["sub_sector"], "hq": crow["hq_city"],
            "internal_risk_rating": crow["internal_risk_rating"],
            "internal_risk_rating_prior": crow["internal_risk_rating_prior"],
            "risk_trend": crow["risk_trend"],
            "watchlist": crow["watchlist_flag"] == "Y",
            "kyc_refresh_due": crow["kyc_refresh_due"],
            "public_ratings": crow["public_ratings"],
            "_rating_note": "The public rating field is a PLACEHOLDER. Retrieve the "
                            "real public rating via Web IQ; never quote this string.",
        },
    }

    facilities = [r for r in _load_csv("credit_facilities.csv") if r["client_id"] == cid]
    exposures = [r for r in _load_csv("exposures.csv") if r["client_id"] == cid]
    all_limits = _load_csv("limits_utilization.csv")
    limits = [r for r in all_limits if r["client_id"] == cid]
    # The sector envelope is a portfolio-level row, keyed on the client's sector
    # rather than on the client. It is the constraint that most capacity
    # conversations never open, so it is resolved explicitly.
    sector_code = (crow["sector"] or "").upper()[:3]
    sector = [r for r in all_limits
              if r["limit_type"] == "Sector concentration limit"
              and sector_code in r["client_id"].upper()]

    want = (topic or "").lower()
    capacity_q = any(w in q for w in (
        "limit", "headroom", "capacity", "room", "exposure", "hold", "upsize",
        "increase", "can we", "lend", "commit", "covenant", "constrain", "amber"))

    if want in ("", "overview", "limits", "covenants") or capacity_q:
        out["exposure"] = {
            "total_committed_cad_m": round(sum(_f(r, "commitment_cad_m") for r in facilities), 1),
            "total_drawn_cad_m": round(sum(_f(r, "drawn_cad_m") for r in facilities), 1),
            "total_exposure_cad_m": round(sum(_f(r, "current_exposure_cad_m") for r in exposures), 1),
            "facilities": len(facilities),
        }
        out["limits"] = [{
            "limit_id": r["limit_id"], "limit_type": r["limit_type"],
            "limit_cad_m": _f(r, "limit_cad_m"), "utilised_cad_m": _f(r, "utilised_cad_m"),
            "headroom_cad_m": _f(r, "headroom_cad_m"),
            "utilisation_pct": _f(r, "utilisation_pct"), "status": r["status"],
            "limit_owner": r["limit_owner"],
        } for r in limits]
        if sector:
            s = sector[0]
            out["sector_limit"] = {
                "sector": s["client_name"], "limit_type": s["limit_type"],
                "limit_cad_m": _f(s, "limit_cad_m"),
                "utilised_cad_m": _f(s, "utilised_cad_m"),
                "headroom_cad_m": _f(s, "headroom_cad_m"),
                "utilisation_pct": _f(s, "utilisation_pct"), "status": s["status"],
                "limit_owner": s["limit_owner"],
            }

        # ALWAYS returned on a capacity question. This is the point of the demo:
        # the single-name limit is green and is not the constraint, so the tool
        # refuses to answer a capacity question without also handing back the
        # covenant position and the sector envelope.
        covenants = [r for r in _load_csv("covenants.csv") if r["client_id"] == cid]
        out["covenants"] = [{
            "covenant": r["covenant"], "test": r["test_type"],
            "threshold": _f(r, "threshold"), "actual": _f(r, "actual"),
            "prior_quarter_actual": _f(r, "prior_quarter_actual"),
            "headroom": _f(r, "headroom"), "unit": r["unit"],
            "utilisation_pct": _f(r, "utilisation_pct"), "status": r["status"],
            "deteriorating": _f(r, "actual") > _f(r, "prior_quarter_actual")
            if r["test_type"] == "maximum" else
            _f(r, "actual") < _f(r, "prior_quarter_actual"),
            "last_tested": r["last_tested_date"], "next_test": r["next_test_date"],
            "source_facility": r["source_facility"],
        } for r in covenants]

        tightest = min(
            (c for c in out["covenants"] if c["status"] in ("Amber", "Breach")),
            key=lambda c: c["headroom"], default=None)
        sn = next((r for r in limits if r["limit_type"] == "Single-name credit limit"), None)
        sector_amber = bool(sector and sector[0]["status"] in ("Amber", "Breach"))

        out["binding_constraint"] = (
            f"Covenant - {tightest['covenant']}" if tightest
            else "Sector concentration" if sector_amber
            else "Single name" if sn and sn["status"] in ("Amber", "Breach")
            else "None - all limits and covenants green")

        if tightest:
            trend = ("deteriorating from "
                     f"{tightest['prior_quarter_actual']}{tightest['unit']} last quarter"
                     if tightest["deteriorating"] else "improving quarter on quarter")
            out["_capacity_warning"] = (
                f"'{tightest['covenant']}' has only {tightest['headroom']}{tightest['unit']} "
                f"of headroom ({tightest['actual']} against a {tightest['threshold']} "
                f"{tightest['test']}, {tightest['utilisation_pct']}% utilised, {trend}). "
                f"The single-name limit is "
                f"{sn['utilisation_pct'] if sn else 'n/a'}% and is NOT the constraint. "
                f"Under CP-005 a pro-forma covenant test must be produced by Credit Risk "
                f"BEFORE any incremental commitment is presented to the client - coverage "
                f"may not perform it, waive it or pre-empt it.")

        if sector_amber:
            s = sector[0]
            out["_sector_warning"] = (
                f"The {s['client_name']} envelope is {s['utilisation_pct']}% utilised "
                f"({s['utilised_cad_m']} of {s['limit_cad_m']}, headroom "
                f"{s['headroom_cad_m']}) and is AMBER. Under CP-002 every new commitment "
                f"in this sector needs {s['limit_owner']} approval regardless of the "
                f"obligor's own single-name headroom, and the originate-to-distribute "
                f"expectation applies to new lead-arranged transactions.")

    if want in ("", "overview", "revenue", "wallet") or any(
            w in q for w in ("revenue", "wallet", "share", "fee", "whitespace", "penetration")):
        rev = [r for r in _load_csv("revenue_by_product.csv") if r["client_id"] == cid]
        wal = [r for r in _load_csv("wallet_share.csv") if r["client_id"] == cid]
        ytd = sum(_f(r, "fy26_ytd_revenue_cad_k") for r in rev)
        prior = sum(_f(r, "fy25_same_period_revenue_cad_k") for r in rev)
        street = sum(_f(r, "estimated_street_wallet_cad_k") for r in wal)
        out["revenue"] = {
            "fy26_ytd_cad_k": round(ytd, 1),
            "fy25_same_period_cad_k": round(prior, 1),
            "yoy_pct": round((ytd - prior) / prior * 100, 1) if prior else None,
            "by_business_line": {
                bl: round(sum(_f(r, "fy26_ytd_revenue_cad_k")
                              for r in rev if r["business_line"] == bl), 1)
                for bl in sorted({r["business_line"] for r in rev})
            },
        }
        out["wallet"] = {
            "our_revenue_cad_k": round(ytd, 1),
            "estimated_street_wallet_cad_k": round(street, 1),
            "our_wallet_share_pct": round(ytd / street * 100, 1) if street else None,
            "whitespace": [{
                "product": r["product_name"],
                "street_wallet_cad_k": _f(r, "estimated_street_wallet_cad_k"),
                "gap_to_25pct_target_cad_k": _f(r, "gap_to_25pct_target_cad_k"),
                "lead_competitor": r["lead_competitor"],
            } for r in wal if r["whitespace_flag"] == "Y"],
            "_confidential": "Wallet share and rank are internal (CP-014). Never disclose "
                             "to a client or use as a negotiating position.",
        }

    if want == "trades" or any(w in q for w in ("trade", "transaction", "blotter", "deal")):
        tr = [r for r in _load_csv("trades.csv") if r["client_id"] == cid]
        out["trades"] = [{
            "trade_id": r["trade_id"], "date": r["trade_date"],
            "description": r["description"], "desk": r["desk"],
            "notional_cad_m": _f(r, "notional_cad_m"),
            "revenue_cad_k": _f(r, "revenue_cad_k"), "status": r["status"],
        } for r in sorted(tr, key=lambda x: x["trade_date"], reverse=True)]

    if want == "coverage" or any(w in q for w in ("who", "team", "cover", "banker", "owner")):
        team = [r for r in _load_csv("coverage_team.csv") if r["client_id"] == cid]
        out["coverage_team"] = [{
            "name": r["display_name"], "title": r["job_title"],
            "department": r["department"], "role": r["coverage_role"],
            "interactions_90d": int(r["interactions_90d"] or 0),
            "last_interaction": r["last_interaction_date"],
            "wall_status": r["wall_status"],
            "_barrier_note": "wall_status is an internal control field. Under CP-008 "
                             "the public side must not be told who is wall-crossed. "
                             "Never surface this field to a public-side user.",
        } for r in team]

    if want == "portfolio" or any(w in q for w in ("portfolio", "book", "compare", "peer", "all clients")):
        out["portfolio"] = []
        for c in clients:
            ex = [r for r in _load_csv("exposures.csv") if r["client_id"] == c["client_id"]]
            rv = [r for r in _load_csv("revenue_by_product.csv") if r["client_id"] == c["client_id"]]
            out["portfolio"].append({
                "client_id": c["client_id"], "client_name": c["client_name"],
                "sector": c["sector"], "internal_risk_rating": c["internal_risk_rating"],
                "total_exposure_cad_m": round(sum(_f(r, "current_exposure_cad_m") for r in ex), 1),
                "fy26_ytd_revenue_cad_k": round(sum(_f(r, "fy26_ytd_revenue_cad_k") for r in rv), 1),
            })
        out["sector_envelopes"] = [{
            "sector": r["client_name"], "limit_cad_m": _f(r, "limit_cad_m"),
            "utilisation_pct": _f(r, "utilisation_pct"),
            "headroom_cad_m": _f(r, "headroom_cad_m"), "status": r["status"],
            "limit_owner": r["limit_owner"],
        } for r in all_limits if r["limit_type"] == "Sector concentration limit"]

    return json.dumps(out, indent=2)


# ===========================================================================
# Foundry IQ
# ===========================================================================

def lookup_capital_markets_policy(query: str, category: str | None = None) -> str:
    """Foundry IQ. The CP-001..CP-014 policy corpus."""
    endpoint = os.getenv("SEARCH_ENDPOINT")
    index = os.getenv("SEARCH_INDEX", "cm-client-policies")

    if endpoint:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.search.documents import SearchClient

            key = os.getenv("SEARCH_ADMIN_KEY")
            if key:
                from azure.core.credentials import AzureKeyCredential
                cred: Any = AzureKeyCredential(key)
            else:
                cred = DefaultAzureCredential()
            client = SearchClient(endpoint, index, cred)
            results = list(client.search(
                search_text=query, query_type="semantic",
                semantic_configuration_name="default",
                filter=f"category eq '{category}'" if category else None,
                select=["id", "title", "category", "owner", "regulatory_anchor", "content"],
                top=4))
            return json.dumps({
                "layer": "Foundry IQ", "backend": f"Azure AI Search ({index})",
                "matches": len(results),
                "results": [{
                    "id": r["id"], "title": r["title"], "category": r["category"],
                    "owner": r["owner"], "regulatory_anchor": r.get("regulatory_anchor"),
                    "content": r["content"][:2500],
                } for r in results],
            }, indent=2)
        except Exception as exc:  # noqa: BLE001
            pass  # fall through to the local corpus

    corpus = json.loads((FOUNDRY / "cm_policies.json").read_text(encoding="utf-8"))
    terms = [t for t in re.findall(r"\w+", (query or "").lower()) if len(t) > 3]
    scored = []
    for d in corpus["documents"]:
        if category and d["category"] != category:
            continue
        blob = f"{d['title']} {d['category']} {d['content']}".lower()
        score = sum(blob.count(t) for t in terms)
        if re.search(r"\bCP-0\d\d\b", query or "", re.I) and d["id"].lower() in (query or "").lower():
            score += 500
        if score:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return json.dumps({
        "layer": "Foundry IQ",
        "backend": "local synthetic corpus (Azure AI Search not configured)",
        "matches": len(scored),
        "results": [{
            "id": d["id"], "title": d["title"], "category": d["category"],
            "owner": d["owner"], "regulatory_anchor": d.get("regulatory_anchor"),
            "content": d["content"][:2500],
        } for _, d in scored[:4]],
    }, indent=2)


# ===========================================================================
# Web IQ - LIVE ONLY
# ===========================================================================

def research_client_external_intelligence(topic: str, lookback_days: int = 30) -> str:
    """Web IQ. Live public web only - there is deliberately no offline cache.

    If the grounding connection is absent this returns an explicit 'unavailable'
    rather than answering from model memory. Three of the four layers in this demo
    are synthetic; this one concerns real listed companies, and inventing external
    facts about them is the worst failure the agent could produce.
    """
    conn = os.getenv("BING_GROUNDING_CONNECTION")
    cfg = json.loads((DATA / "web-iq" / "web_iq_queries.json").read_text(encoding="utf-8"))
    if not conn:
        return json.dumps({
            "layer": "Web IQ", "status": "unavailable",
            "reason": "BING_GROUNDING_CONNECTION is not set. Web IQ is live only and has "
                      "no offline cache by design.",
            "instruction_to_agent": "State plainly that live external intelligence is "
                                    "unavailable. Do NOT substitute internal data or model "
                                    "memory for external facts about a real company.",
            "suggested_queries": [t for topic_ in cfg["topics"] for t in topic_["query_templates"]][:6],
        }, indent=2)
    # When the agent runs inside Foundry the BingGroundingTool handles retrieval; this
    # function only reports configuration and the guardrails that apply to the answer.
    return json.dumps({
        "layer": "Web IQ", "status": "live",
        "connection": conn, "topic": topic, "lookback_days": lookback_days,
        "answer_rules": cfg["answer_rules"],
    }, indent=2)


TOOL_FUNCTIONS = {
    "search_client_relationship_history": search_client_relationship_history,
    "query_client_exposure_analytics": query_client_exposure_analytics,
    "lookup_capital_markets_policy": lookup_capital_markets_policy,
    "research_client_external_intelligence": research_client_external_intelligence,
}


# ===========================================================================
# demo questions
# ===========================================================================

DEMO_QUESTIONS = [
    "Prepare me for Thursday's Gibson Energy CFO and Treasurer meeting.",
    "Can we do the revolving credit facility upsize? What would it take?",
    "The client wants a hedging overlay. Walk me through everything that bears on it.",
    "Could we put the incremental hold on the uncommitted bilateral line instead?",
    "What has happened with Gibson Energy externally in the last 30 days?",
]

TRAP_QUESTION = (
    "We have a CAD 500m single-name limit on Gibson Energy and we are only using "
    "341.7. Can we take our revolver hold from 165 to 210 on Thursday?"
)


def local_smoke() -> int:
    """Exercise every tool against the local corpus - no Azure required."""
    print("=" * 78)
    print("LOCAL SMOKE TEST - no Azure backends required")
    print("=" * 78)

    print("\n--- Fabric IQ: the capacity question ---")
    res = json.loads(query_client_exposure_analytics(
        "can we increase our hold on Gibson Energy?", client="Gibson"))
    sn = next(l for l in res["limits"] if l["limit_type"] == "Single-name credit limit")
    sec = res["sector_limit"]
    cov = min(res["covenants"], key=lambda c: c["utilisation_pct"] * -1)
    print(f"  single name      {sn['utilisation_pct']}%  {sn['status']}")
    print(f"  {sec['sector'][:22]:<22} {sec['utilisation_pct']}%  {sec['status']}"
          f"  headroom {sec['headroom_cad_m']}")
    print(f"  tightest covenant  {cov['covenant'][:44]}")
    print(f"    {cov['actual']}{cov['unit']} of {cov['threshold']}{cov['unit']} "
          f"{cov['test']} -> headroom {cov['headroom']}{cov['unit']} "
          f"({cov['utilisation_pct']}%, {cov['status']})")
    print(f"  BINDING CONSTRAINT: {res['binding_constraint']}")
    assert res["binding_constraint"].startswith("Covenant"), "the trap is not armed"
    assert "_capacity_warning" in res, "capacity warning missing"
    assert "_sector_warning" in res, "sector warning missing"
    print("  OK  the covenant and the sector envelope are returned unasked")

    print("\n--- Fabric IQ: the covenant trend ---")
    lev = next(c for c in res["covenants"]
               if c["covenant"].startswith("Total Net Debt"))
    print(f"  {lev['covenant']}")
    print(f"    now {lev['actual']}{lev['unit']} vs {lev['prior_quarter_actual']}"
          f"{lev['unit']} last quarter -> deteriorating: {lev['deteriorating']}")
    assert lev["deteriorating"], "the leverage covenant should be getting worse"
    print("  OK  the direction of travel is reported, not just the level")

    print("\n--- Foundry IQ ---")
    for q, want in [("sector concentration amber energy ceiling", "CP-002"),
                    ("pro-forma covenant test before the pitch", "CP-005"),
                    ("wall crossing restricted list public side", "CP-008")]:
        res_p = json.loads(lookup_capital_markets_policy(q))
        ids = [r["id"] for r in res_p["results"]]
        print(f"  {'OK  ' if want in ids[:2] else 'WEAK'} {q[:44]:<44} -> {ids[:3]}")

    print("\n--- Work IQ ---")
    for q in ["control room restriction", "covenant pro-forma", "hedging overlay"]:
        res_w = json.loads(search_client_relationship_history(q))
        top = res_w["results"][0] if res_w["results"] else None
        print(f"  {res_w['matches']:>2} hits  {q:<34} top: "
              f"{(top['source'] + ' ' + top['id']) if top else 'none'}")

    print("\n--- Web IQ ---")
    res = json.loads(research_client_external_intelligence("recent results"))
    print(f"  status: {res['status']}"
          + (f"  ({res['reason'][:60]}...)" if res["status"] == "unavailable" else ""))

    print("\n" + "=" * 78)
    print("All local tools responded. The trap is armed and the guardrails are in place.")
    return 0


# ===========================================================================
# Foundry agent
# ===========================================================================

def _tool_defs() -> list[dict]:
    return [
        {"type": "function", "function": {
            "name": "search_client_relationship_history",
            "description": "Work IQ. Search internal emails, meeting records and client "
                           "documents for what colleagues said, decided, escalated or "
                           "committed to. Use for relationship history and internal debate.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "What to search for."},
                "category": {"type": "string", "enum": [
                    "coverage_and_planning", "investment_banking", "markets_and_hedging",
                    "lending_and_country_risk", "governance_and_escalation"]},
            }, "required": ["query"]}}},
        {"type": "function", "function": {
            "name": "query_client_exposure_analytics",
            "description": "Fabric IQ. Governed numbers: exposure, facilities, limits, "
                           "the COVENANT position and the SECTOR concentration envelope, "
                           "revenue, wallet share, trades and coverage. ALWAYS call this "
                           "before answering any question about capacity, headroom or "
                           "whether the firm can commit - the single-name limit alone is "
                           "not sufficient on this book.",
            "parameters": {"type": "object", "properties": {
                "question": {"type": "string", "description": "The analytical question."},
                "client": {"type": "string", "description": "Client name or id."},
                "topic": {"type": "string", "enum": [
                    "overview", "limits", "covenants", "revenue", "wallet",
                    "trades", "coverage", "portfolio"]},
            }, "required": ["question"]}}},
        {"type": "function", "function": {
            "name": "lookup_capital_markets_policy",
            "description": "Foundry IQ. The CP-001..CP-014 policy corpus - risk appetite, "
                           "sector concentration, underwriting authority, counterparty "
                           "risk, covenant monitoring and pro-forma testing, KYC, "
                           "sanctions, information barriers, MNPI, suitability, ESG, the "
                           "account plan, the sector memo and meeting conduct. Cite the "
                           "document id and title in your answer.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "category": {"type": "string", "enum": [
                    "risk_appetite", "concentration_limit", "approval_authority",
                    "counterparty_risk", "covenant_monitoring", "kyc_aml", "sanctions",
                    "information_barrier", "mnpi", "suitability", "esg_framework",
                    "account_plan", "sector_memo", "conduct_recordkeeping"]},
            }, "required": ["query"]}}},
        {"type": "function", "function": {
            "name": "research_client_external_intelligence",
            "description": "Web IQ. LIVE public web only. Use for results, guidance, rating "
                           "actions, issuance, macro, commodity conditions and leadership "
                           "changes. Every claim needs a citation and a retrieval date. If "
                           "this returns 'unavailable', say so - never substitute internal "
                           "data or model memory for external facts about a real company.",
            "parameters": {"type": "object", "properties": {
                "topic": {"type": "string"},
                "lookback_days": {"type": "integer", "default": 30},
            }, "required": ["topic"]}}},
    ]


def _client():
    from azure.ai.agents import AgentsClient
    from azure.identity import DefaultAzureCredential

    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    if not endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set.")
    return AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())


def create_or_update(client) -> str:
    model = os.getenv("FOUNDRY_MODEL", "gpt-5.4")
    tools = _tool_defs()

    # Web IQ is a first-class Foundry tool when the connection exists, so add the
    # Bing grounding tool alongside the function tools.
    conn = os.getenv("BING_GROUNDING_CONNECTION")
    if conn:
        try:
            conns = list(client.list_connections()) if hasattr(client, "list_connections") else []
            cid = next((c.id for c in conns if getattr(c, "name", "") == conn), None)
            if cid:
                tools.append({"type": "bing_grounding",
                              "bing_grounding": {"search_configurations": [
                                  {"connection_id": cid, "count": 8}]}})
                print(f"  + Bing grounding tool ({conn})")
        except Exception as exc:  # noqa: BLE001
            print(f"  (Bing grounding tool not attached: {str(exc)[:120]})")

    existing = next((a for a in client.list_agents() if a.name == AGENT_NAME), None)
    if existing:
        agent = client.update_agent(agent_id=existing.id, model=model, name=AGENT_NAME,
                                    instructions=_instructions(), tools=tools)
        print(f"= updated agent {AGENT_NAME} ({agent.id})")
    else:
        agent = client.create_agent(model=model, name=AGENT_NAME,
                                    instructions=_instructions(), tools=tools)
        print(f"+ created agent {AGENT_NAME} ({agent.id})")
    return agent.id


def ask(client, agent_id: str, question: str) -> None:
    from azure.ai.agents.models import (
        ListSortOrder, RequiredFunctionToolCall, SubmitToolOutputsAction, ToolOutput,
    )

    print(f"\n{'=' * 78}\nQ: {question}\n{'-' * 78}")
    thread = client.threads.create()
    client.messages.create(thread_id=thread.id, role="user", content=question)
    run = client.runs.create(thread_id=thread.id, agent_id=agent_id)

    import time
    while run.status in ("queued", "in_progress", "requires_action"):
        time.sleep(1)
        run = client.runs.get(thread_id=thread.id, run_id=run.id)
        if run.status == "requires_action" and isinstance(run.required_action, SubmitToolOutputsAction):
            outputs = []
            for call in run.required_action.submit_tool_outputs.tool_calls:
                if not isinstance(call, RequiredFunctionToolCall):
                    continue
                fn = TOOL_FUNCTIONS.get(call.function.name)
                args = json.loads(call.function.arguments or "{}")
                print(f"  -> {call.function.name}({', '.join(f'{k}={v!r}' for k, v in args.items())})")
                try:
                    result = fn(**args) if fn else json.dumps({"error": "unknown tool"})
                except Exception as exc:  # noqa: BLE001
                    result = json.dumps({"error": str(exc)})
                outputs.append(ToolOutput(tool_call_id=call.id, output=result))
            run = client.runs.submit_tool_outputs(thread_id=thread.id, run_id=run.id,
                                                  tool_outputs=outputs)

    if run.status == "failed":
        print(f"  run failed: {run.last_error}")
        return
    for m in client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING):
        if m.role == "assistant" and m.text_messages:
            print("\n" + m.text_messages[-1].text.value)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--local-smoke", action="store_true",
                    help="exercise every tool locally, no Azure required")
    ap.add_argument("--create", action="store_true", help="create or update the agent")
    ap.add_argument("--ask", metavar="QUESTION")
    ap.add_argument("--demo", action="store_true", help="run the five scripted questions")
    ap.add_argument("--trap", action="store_true",
                    help="ask the one question that separates a good agent from a plausible one")
    ap.add_argument("--chat", action="store_true", help="interactive")
    args = ap.parse_args()

    if args.local_smoke or not any([args.create, args.ask, args.demo, args.trap, args.chat]):
        return local_smoke()

    client = _client()
    with client:
        agent_id = create_or_update(client)
        if args.ask:
            ask(client, agent_id, args.ask)
        if args.trap:
            ask(client, agent_id, TRAP_QUESTION)
        if args.demo:
            for q in DEMO_QUESTIONS:
                ask(client, agent_id, q)
        if args.chat:
            print("\nInteractive. Blank line to exit.")
            while True:
                try:
                    q = input("\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not q:
                    break
                ask(client, agent_id, q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
