"""Coverage agent missions - the part of the Dashboard an API cannot do, run through a visible harness.

The Dashboard's numbers (exposure, limits, covenants, the shocked covenant, pro-formas, wallet share)
are deterministic and stay that way. What no API returns is the *reconciliation*: DCM wants to pitch,
Credit holds, Markets proposes, the Control Room restricts, KYC or sanctions hold - and colleagues have
written things no table holds. A mission hands one client and one question to `cm-mission-agent` and
wraps it in a harness:

    1 plan        fixed in code: layers, policies, limits on what the agent may do
    2 packet      governed figures + every business line's stance (line_positions) + the rules view
    3 agent       cm-mission-agent with a per-call tool trace (Work, Foundry, Web, Fabric IQ)
    4 guardrails  deterministic: figures traced, policy ids exist, no autonomous action, layers used,
                  barrier/MNPI/internal-figure leakage and commitments in client copy, restricted subject
    5 review      cm-barrier-reviewer over the client message (skipped when there is none)
    6 human       the banker approves, sends back or escalates - written to the audit log

Every decision is logged as one `MISSION_AUDIT {json}` line, so the "agent changed the answer" KPI is
computed across replicas from Log Analytics (ContainerAppConsoleLogs_CL), not from one replica's memory.
SYNTHETIC demo data.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections import OrderedDict, deque
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import httpx

from . import coverage as C
from .agent_client import run_agent
from .auth import User
from .config import settings
from .iq import sse
from .line_data import LINE_POSITIONS
from .market_data import MARKET_DATA
from .skill_data import SKILL_DATA

logger = logging.getLogger("bff.missions")

CLIENTS = SKILL_DATA["clients"]
HERO = SKILL_DATA["client"]["id"]
SCN = MARKET_DATA["scenario"]
EXTRA = MARKET_DATA["extra"]
PEOPLE = MARKET_DATA["people"]
LINES: dict[str, list[dict]] = {}
for _r in LINE_POSITIONS:
    LINES.setdefault(_r["client_id"], []).append(_r)
KNOWN_POLICIES = {f"CP-{i:03d}" for i in range(1, 18)}
SELL = {"Pitch", "Propose"}
BIND = {"Hold", "Restricted", "Review"}
# CP-017 order of precedence - the deterministic "which line binds" used for the rules view.
PRECEDENCE = ["Control Room", "AML / KYC", "Credit Risk", "Global Markets", "Sustainable Finance", "Equity Research", "DCM / Coverage"]

RUNS: "OrderedDict[str, dict]" = OrderedDict()
AUDIT: deque = deque(maxlen=200)
# Latest live retrieval per client, by IQ layer - fills the Dashboard's evidence cards (this replica).
EVIDENCE: dict[str, dict] = {}


def _new_evidence() -> dict[str, dict]:
    return {iq: {"queries": [], "results": []} for iq in ("fabric", "work", "foundry", "web")}


def _add_call(ev: dict, data: dict, restricted: bool) -> None:
    iq = data.get("iq")
    if iq not in ev:
        return
    q = (data.get("detail") or "").strip()
    if q and q not in ev[iq]["queries"]:
        ev[iq]["queries"].append(q[:160])
    for r in data.get("results") or []:
        r = {"title": str(r.get("title", ""))[:200], "meta": "" if (restricted and iq == "work") else str(r.get("meta", ""))[:80]}
        if r["title"] and r not in ev[iq]["results"]:
            ev[iq]["results"].append(r)


def _add_citations(ev: dict, cites: list[dict]) -> None:
    for c in cites or []:
        url, title = c.get("url") or "", c.get("title") or ""
        m = re.search(r"\bCP-\d{3}\b", url + " " + title)
        if m:
            r = {"title": m.group(0), "meta": "cited"}
            if r not in ev["foundry"]["results"] and not any(x["title"].startswith(m.group(0)) for x in ev["foundry"]["results"]):
                ev["foundry"]["results"].append(r)
        elif url.startswith("http"):
            r = {"title": title or url, "meta": url}
            if r not in ev["web"]["results"]:
                ev["web"]["results"].append(r)


def evidence(cid: str) -> dict | None:
    return EVIDENCE.get(cid)

HARNESS = [
    ("plan", "Plan", "Fixed in code: which layers to use, which policies apply, what the agent may not do."),
    ("packet", "Governed packet", "Governed figures and every business line's stance. This is what an API returns."),
    ("agent", "Agent investigation", "cm-mission-agent calls Work IQ, Foundry IQ, Web IQ and Fabric IQ, then reconciles."),
    ("guardrails", "Guardrails", "Deterministic checks over the agent's output. Can block, never approve."),
    ("review", "Barrier review", "cm-barrier-reviewer over the client message, if there is one."),
    ("human", "Banker decision", "You approve, send back or escalate. Nothing is sent from here."),
]
HEADINGS = ["Decision", "What changed the decision", "Lines reconciled", "What we will not do", "Banker brief", "Client message", "Evidence"]

KINDS: dict[str, dict[str, Any]] = {
    "briefing": {
        "label": "Prepare briefing", "title": "Pre-contact briefing: what to say, what not to, who leads",
        "question": "{name} is affected by this morning's move. Before anyone contacts the client today, what does the banker need to know, which line's position binds, and what must not be said?",
        "deliverable": "Pre-call banker brief + a barrier-safe client note",
        "api": ["Exposure, limits, covenant headroom and the shocked covenant", "A triage score and a templated outreach message",
                "Each desk's own proposal, unreconciled"],
        "agent": ["Reads the colleague threads on this client (call reports, escalations, Control Room notes)",
                  "Applies CP-017 to decide which line binds when DCM, Credit, Markets, KYC and the Control Room disagree",
                  "Adds the dated public picture (news, ratings, the market move) as context only",
                  "Writes one brief and a client note that passes the barrier review - or says not to write one"],
        "work": "this client's call reports, escalations, Control Room or compliance notes, and anything the client said recently",
        "web": "the client's latest public news and credit ratings this month, plus today's crude oil move (dated, sourced)",
    },
    "opportunities": {
        "label": "Explore opportunities", "title": "Opportunity: pitch now, sequence it, or hold?",
        "question": "The origination data shows a wallet gap and a desk wants to pitch {name}. Should we take an opportunity to the client now, in what order with the other lines, and with what conditions?",
        "deliverable": "Opportunity call (go / sequence / hold) + banker talking points",
        "api": ["Wallet share and the largest gap to the 25% target", "The desk's proposal (Pitch / Propose)",
                "Pro-forma leverage for a facility size (hero client)"],
        "agent": ["Checks every binding line first: Control Room, KYC and sanctions, Credit, appropriateness, SLL commitments",
                  "Finds colleague context that changes the order, such as a complaint, a KPI miss or a possible-MNPI remark",
                  "Proposes a sequence (fix X, then pitch Y) rather than a yes or no",
                  "Never trades a covenant, KPI or KYC exception for a mandate (CP-017)"],
        "work": "this client's pitches, proposals, complaints, KYC or sanctions notes and anything that changes whether to pitch now",
        "web": "the client's public announcements and financing news this quarter (dated, sourced)",
    },
    "risks": {
        "label": "Review risks", "title": "Risk review: what is the real risk today, and who acts?",
        "question": "What is the real risk on {name} today - credit, conduct, barrier, KYC or reputational - and which owner needs to act first?",
        "deliverable": "Risk note for the owners + an action list",
        "api": ["Covenant bands before and after the shock", "Limit utilisation, rating trend and watchlist flag",
                "A severity score"],
        "agent": ["Adds the non-numeric risks (possible MNPI, sanctions, a complaint, an SLL KPI miss) from colleague mail",
                  "Ranks them and names the owner (Credit Risk, Control Room, Compliance, the desk)",
                  "Separates what the client may be told from what stays internal",
                  "Flags when the numbers look fine but the case is not, or the other way round"],
        "work": "this client's risk, credit, compliance, sanctions, KYC or Control Room notes and any client complaints",
        "web": "the client's credit ratings and any rating actions, plus public news that bears on credit risk (dated, sourced)",
    },
}
POLICIES = ["CP-001", "CP-003", "CP-005", "CP-006", "CP-007", "CP-008", "CP-009", "CP-010", "CP-011", "CP-014", "CP-016", "CP-017"]


# --------------------------------------------------------------------------- #
# Deterministic layer
# --------------------------------------------------------------------------- #
def lines(cid: str) -> list[dict]:
    return sorted(LINES.get(cid, []), key=lambda r: PRECEDENCE.index(r["business_line"]) if r["business_line"] in PRECEDENCE else 99)


def lines_conflict(cid: str) -> bool:
    st = {r["stance"] for r in LINES.get(cid, [])}
    return bool(st & SELL) and bool(st & BIND)


def rules_view(kind: str, cid: str) -> str:
    """What a rules engine / API would recommend on its own - the baseline the agent is compared to."""
    ls = LINES.get(cid, [])
    sell = [r for r in ls if r["stance"] in SELL]
    if kind == "opportunities":
        return (f"{sell[0]['business_line']}: {sell[0]['stance']} - {sell[0]['proposed_action']}" if sell
                else "No desk proposal - no opportunity to take.")
    if kind == "risks":
        s = C.severity(cid)
        top = max(s["parts"], key=lambda p: p["points"])
        return f"Severity score {s['score']}: top factor {top['factor']} ({top['detail']})."
    o = next((i for i in C.outreach()["items"] if i["id"] == cid), None)
    if not o:
        return "Not on today's outreach list - no contact."
    return f"Contact the {o['contact_role']} via {o['channel_detail']} at {o['slot']} with the templated outreach message."


def packet(cid: str) -> list[dict]:
    c, x, imp = CLIENTS[cid], EXTRA[cid], C.impact(cid)
    s = SCN["clients"][cid]
    own = MARKET_DATA["owners"][cid]
    out = [
        {"source": "Fabric IQ · client_360 / risk_ratings", "facts": {
            k: c[k] for k in ("id", "name", "ticker", "sector", "sub_sector", "tier", "rating", "rating_prior", "trend", "watchlist",
                              "kyc_refresh_due", "last_meeting")}},
        {"source": "Fabric IQ · covenants + scenario (shocked)", "facts": {
            "scenario": SCN["headline"], "as_of": SCN["as_of"], "ebitda_shock_pct": imp["ebitda_shock_pct"], "driver": imp["driver"],
            "covenants": [{k: v for k, v in cv.items() if k != "tone"} for cv in imp["covenants"]],
            **({"deal": imp["deal"]} if imp.get("deal") else {})}},
        {"source": "Fabric IQ · limits_utilization / credit_facilities", "facts": {
            "limits": [{k: l[k] for k in ("type", "limit", "utilised", "utilisation_pct", "status")} for l in c["limits"]],
            "facilities": [{k: f[k] for k in ("type", "commitment", "drawn", "maturity")} for f in c["facilities"]]}},
        {"source": "Fabric IQ · revenue / wallet (INTERNAL)", "facts": {
            "revenue_ytd_m": x["revenue_ytd_m"], "wallet_share_pct": x["wallet_share_pct"], "opportunity": c["opportunity"]}},
        {"source": "Fabric IQ · coverage_team", "facts": {
            "owner": PEOPLE[own["owner"]]["name"], "banker": PEOPLE[own["banker"]]["name"],
            "wall_crossed": [p["name"] for p in PEOPLE.values() if p.get("wall_status") == "wall_crossed"] if cid == HERO else [],
            "contact_role": s["contact_role"], "channel": s["channel_detail"], "slot": s["slot"]}},
        {"source": "Foundry IQ · CP-015 house view", "facts": {"positions": SCN["house_view"]["positions"]}},
    ]
    return out


def _client_for_name(cid: str) -> str:
    return CLIENTS[cid]["name"]


# --------------------------------------------------------------------------- #
# Prompt
# --------------------------------------------------------------------------- #
def prompt(kind: str, cid: str, pk: list[dict], ls: list[dict], rv: str) -> str:
    k = KINDS[kind]
    name = _client_for_name(cid)
    line_txt = "\n".join(f"- [{r['business_line']}] {r['stance']}: {r['proposed_action']} - {r['rationale']} ({r['policy_ref']}, {r['status_date']})"
                         for r in ls) or "- (no line positions)"
    return (
        f"MISSION ({k['label']}): {k['title']}\n{k['question'].format(name=name)}\n\n"
        f"CLIENT: {name} ({cid}, {CLIENTS[cid]['ticker']}). As of {SCN['as_of']} {SCN['time_local']}. Deliverable: {k['deliverable']}.\n\n"
        "You run inside the Bank's agent harness (CP-016). The harness has already assembled the GOVERNED PACKET below "
        "(authoritative - never recompute or contradict it) and the BUSINESS-LINE POSITIONS, each correct on its own terms. The "
        "RULES VIEW is what an API returns without you. After you answer, deterministic guardrails check your output and the "
        "barrier reviewer reviews any client message; then the banker decides. You never send, commit, size, price, approve, "
        "wall-cross or contact anyone.\n\n"
        "Do this, in order:\n"
        f"1. Work IQ - search mail, Teams and files for {k['work']}. Search narrowly: first \"{name}\" in quotes, then one topic at a "
        "time; 3-5 results, subjects and previews only (a broad search exceeds the tool's size cap and fails). Quote briefly. If "
        "nothing is found, say so.\n"
        "2. Foundry IQ - retrieve and cite by id the policies that decide this case (start with CP-017 and the policies on the "
        "line positions).\n"
        f"3. Web IQ - {k['web']}. Context only: dated, sourced, never a client-facing number.\n"
        "4. Fabric IQ - run at least one query that verifies a key figure from the packet (line_positions holds each line's stance).\n"
        "5. Reconcile - apply CP-017 and make one call.\n\n"
        "OUTPUT - markdown, exactly these level-2 headings in this order, under ~500 words:\n"
        "## Decision\nFirst line exactly `RULES VIEW: AGREE` or `RULES VIEW: CHANGED - <short reason>` comparing your call with the "
        "RULES VIEW. Then one short paragraph: the call, the owner and by when.\n"
        "## What changed the decision\n3-5 bullets the rules alone would miss, each tagged [Work IQ], [Foundry IQ CP-0xx], "
        "[Web IQ <date>] or [Fabric IQ].\n"
        "## Lines reconciled\nTable | Line | Position | Binds? | Why | covering every business line.\n"
        "## What we will not do\nBullets.\n"
        "## Banker brief\n3-6 bullets the banker says or asks; internal language is fine here.\n"
        "## Client message\nEither 'SUBJECT: ...' then 'BODY:' and a short email signed by the relationship owner, or "
        "'NONE - <reason>' when no written contact is appropriate. Client text never mentions restrictions, inquiries, alerts, "
        "wall-crossing, internal ratings, limits, utilisation, wallet share, pro-forma or shocked covenant figures, and never "
        "commits, sizes, prices or solicits.\n"
        "## Evidence\nBullets: every figure you used that is NOT in the governed packet (or is computed from it), with its source.\n\n"
        "Always call the firm 'the Bank'. Synthetic demo data.\n\n"
        f"RULES VIEW (what an API returns): {rv}\n\n"
        f"BUSINESS-LINE POSITIONS (Fabric IQ line_positions):\n{line_txt}\n\n"
        f"GOVERNED PACKET (JSON):\n{json.dumps(pk, separators=(',', ':'), default=str)}\n"
    )


# --------------------------------------------------------------------------- #
# Guardrails
# --------------------------------------------------------------------------- #
def sections(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    parts = re.split(r"^#{2,3}\s*(.+?)\s*#*\s*$", text, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        head = re.sub(r"[*_`]", "", parts[i]).strip().lower()
        for h in HEADINGS:
            if head.startswith(h.lower()[:12]):
                out.setdefault(h, parts[i + 1].strip())
                break
    return out


def client_message(secs: dict[str, str]) -> dict | None:
    raw = re.sub(r"^```\w*\s*|\s*```$", "", secs.get("Client message", "").strip()).strip()
    if not raw or re.match(r"^\**\s*none\b", raw, re.I):
        return None
    sm = re.search(r"SUBJECT\**\s*:\s*\**\s*(.+)", raw, re.I)
    bm = re.search(r"BODY\**\s*:\s*\**\s*(.*)", raw, re.I | re.S)
    body = (bm.group(1) if bm else re.sub(r".*SUBJECT\**\s*:.*\n?", "", raw, flags=re.I)).strip()
    return {"subject": (sm.group(1).strip().strip("*") if sm else ""), "body": re.sub(r"^```\w*\s*|\s*```$", "", body).strip()}


def none_reason(secs: dict[str, str]) -> str:
    m = re.match(r"^\**\s*none\b\**\s*[-–—:]*\s*(.*)", secs.get("Client message", "").strip(), re.I | re.S)
    return (m.group(1).strip() if m else "").split("\n")[0][:240]


def rules_flag(secs: dict[str, str]) -> tuple[str, str]:
    m = re.search(r"RULES VIEW\**[ \t]*:[ \t]*\**[ \t]*(AGREE|CHANGED)\b\**[ \t]*[-–—:]*[ \t]*([^\n]*)", secs.get("Decision", ""), re.I)
    return (m.group(1).upper(), m.group(2).strip()[:200]) if m else ("", "")


FIG = re.compile(r"(?<![\w.])(?:CAD|USD|\$)\s?(\d[\d,]*(?:\.\d+)?)\s?(bn|m|k)?\b|(?<![\w.$-])(\d+(?:\.\d+)?)\s?(%|x\b|bps\b|bp\b|turns?\b)")


def _figures(text: str) -> list[tuple[str, float]]:
    out = []
    for m in FIG.finditer(text):
        if m.group(1):
            v = float(m.group(1).replace(",", ""))
            if (m.group(2) or "").lower() == "bn":
                v *= 1000
            out.append((m.group(0).strip(), v))
        else:
            out.append((m.group(0).strip(), float(m.group(3))))
    return out


def _numbers(obj: Any, acc: list[float]) -> list[float]:
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.append(float(obj))
    elif isinstance(obj, str):
        for n in re.findall(r"-?\d[\d,]*(?:\.\d+)?", obj):
            try:
                acc.append(float(n.replace(",", "")))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            _numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _numbers(v, acc)
    return acc


def _traced(v: float, nums: list[float]) -> bool:
    for p in nums:
        tol = max(0.051, abs(p) * 0.005)
        if v == int(v) and abs(p) >= 10:
            tol = max(tol, 0.5)
        if abs(abs(p) - v) <= tol or abs(abs(p) * 1000 - v) <= tol:
            return True
    return False


AUTONOMY = re.compile(r"\bI(?:\s+have|'ve)?\s+(sent|emailed|approved|committed|wall-?crossed|called|contacted|submitted|booked|priced)\b", re.I)
COMMIT = re.compile(r"\b(we (will|can|are able to) (provide|commit|lend|underwrite|offer you|extend|increase)|is approved|has been approved|"
                    r"pre-?approved|guarantee|we are committed to providing)\b", re.I)
INTERNAL = re.compile(r"\b(control room|restrict\w*|wall[- ]?cross\w*|inquiry|screening|sanction\w*|alert|watchlist|watch list|"
                      r"wallet share|utilis\w*|utiliz\w*|pro-?forma|headroom|internal rating|IG-\d+|CR-20\d\d-\d+|CRI-\d+|SA-20\d\d-\d+|"
                      r"OPP-\d+|LIM-\d+|FAC-\d+|CP-0\d\d|single[- ]name limit|credit risk)\b", re.I)
INTERNAL_FIG = re.compile(r"\b\d+(\.\d+)?\s?x\b")
HEDGE = re.compile(r"\b(hedg\w*|differential|overlay|derivative\w*|collar\w*)\b", re.I)
FORWARD = re.compile(r"\b(will (rise|fall|recover|retrace|widen|narrow)|expect\w* .{0,30}(price|spread|rate)s?)\b", re.I)
DISCLAIM = re.compile(r"not a forecast|not advice|forward-looking|illustrative", re.I)


def guardrails(cid: str, text: str, secs: dict[str, str], msg: dict | None, pk: list[dict], used: set[str]) -> list[dict]:
    out: list[dict] = []

    def add(rule: str, name: str, ok: bool, detail: str, sev: str = "block") -> None:
        out.append({"rule": rule, "name": name, "status": "pass" if ok else sev, "detail": detail})

    missing = [h for h in HEADINGS if h not in secs]
    add("Harness", "Output contract (7 sections)", not missing, "All sections present." if not missing else "Missing: " + ", ".join(missing), "warn")
    flag, why = rules_flag(secs)
    add("Harness", "Compared with the rules view", bool(flag), f"{flag}{' - ' + why if why else ''}." if flag else "No RULES VIEW line.", "warn")
    for iq, name, reason in (("work", "Colleague correspondence searched (Work IQ)", "colleague context must be checked"),
                             ("foundry", "Policy retrieved (Foundry IQ)", "policy must be retrieved, not recalled"),
                             ("fabric", "Governed figure verified (Fabric IQ)", "at least one packet figure must be re-verified")):
        add("CP-016", name, iq in used, "Called during the run." if iq in used else f"Not called - {reason}.", "warn")
    nums = _numbers(pk, [])
    evidence = re.sub(r"(?<=\d),(?=\d)", "", secs.get("Evidence", ""))
    body = "\n".join(v for k, v in secs.items() if k != "Evidence") or text
    traced = sourced = 0
    unsourced: list[str] = []
    for raw, v in _figures(body):
        if _traced(v, nums):
            traced += 1
        elif re.search(re.escape(re.sub(r"[^\d.]", "", raw) or raw), evidence):
            sourced += 1
        else:
            unsourced.append(raw)
    uniq = list(dict.fromkeys(unsourced))
    add("CP-016", "Every figure traced to governed data or a cited source", not uniq,
        f"{traced} traced to the packet, {sourced} cited in Evidence." + (f" Unsourced: {', '.join(uniq[:6])}." if uniq else ""), "warn")
    cited = set(re.findall(r"\bCP-\d{3}\b", text))
    bogus = sorted(cited - KNOWN_POLICIES)
    add("CP-016", "Policy citations exist in Foundry IQ", bool(cited) and not bogus,
        f"Cited {', '.join(sorted(cited)) or 'none'}." + (f" Unknown: {', '.join(bogus)}." if bogus else ""), "block" if bogus else "warn")
    m = AUTONOMY.search(text)
    add("CP-016", "No autonomous action claimed", not m, f"Found: \"{m.group(0)}\"." if m else "Prepares only.")
    if not msg:
        add("CP-014", "Client message", True, "None - the agent chose no written contact (" + (none_reason(secs) or "reason not given") + ").")
        return out
    copy = f"{msg['subject']}\n{msg['body']}"
    m = INTERNAL.search(copy)
    add("CP-008", "No barrier, compliance or internal-process content", not m, f"Found: \"{m.group(0)}\"." if m else "None found.")
    m = INTERNAL_FIG.search(copy)
    add("CP-014", "No internal figures (leverage multiples, limits)", not m, f"Found: \"{m.group(0)}\"." if m else "None found.")
    m = COMMIT.search(copy)
    add("CP-003", "No commitment, approval, size or price", not m, f"Found: \"{m.group(0)}\"." if m else "None found.")
    wall = [p["name"] for p in PEOPLE.values() if p.get("wall_status") == "wall_crossed"]
    m = next((n for n in wall if n.split()[0].lower() in copy.lower()), None)
    add("CP-008", "No wall-crossed colleague named", not m, f"Found: \"{m}\"." if m else "None found.")
    if cid == HERO:
        m = HEDGE.search(copy)
        add("CP-008", "Restricted subject matter (CR-2026-0184)", not m, f"Found: \"{m.group(0)}\" while the restriction is live." if m else "None found.")
    if FORWARD.search(copy):
        ok = bool(DISCLAIM.search(copy))
        add("CP-014", "Forward-looking view carries a disclaimer", ok, "Disclaimer present." if ok else "Market view without a not-a-forecast disclaimer.", "warn")
    return out


def review_prompt(cid: str, msg: dict, cks: list[dict]) -> str:
    ls = "; ".join(f"{r['business_line']}={r['stance']}" for r in lines(cid))
    det = "\n".join(f"- {k['rule']} {k['name']}: {k['status'].upper()} - {k['detail']}" for k in cks)
    return (
        f"Review this client communication for {_client_for_name(cid)} drafted by the mission agent before the banker can use it. "
        f"Internal context (do NOT repeat to the client): business-line positions {ls}; "
        f"{'Control Room restriction CR-2026-0184 is live (public information only, no hedging solicitation)' if cid == HERO else 'no restriction on file'}.\n"
        f"Deterministic harness checks already run (authoritative):\n{det}\n\n"
        f"DRAFT SUBJECT: {msg['subject']}\nDRAFT BODY:\n{msg['body']}\n\n"
        "Return 'VERDICT: PASS', 'VERDICT: NEEDS FIXES' or 'VERDICT: BLOCKED' first (never weaker than the checks), then a findings "
        "table (exact text, policy CP-008 / CP-009 / CP-010 / CP-014 / CP-017, why), then a corrected draft in a ```text block if "
        "fixable. Refer to the firm as 'the Bank'. You review; you never send or approve."
    )


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
def board() -> dict:
    rows = []
    for cid, c in CLIENTS.items():
        ls = lines(cid)
        rows.append({"id": cid, "name": c["name"], "conflict": lines_conflict(cid),
                     "lines": [{"line": r["business_line"], "stance": r["stance"], "action": r["proposed_action"]} for r in ls]})
    return {"as_of": SCN["as_of"], "clients": rows}


def mission(kind: str, cid: str) -> dict:
    k = KINDS[kind]
    ls = lines(cid)
    return {"kind": kind, "clientId": cid, "client": _client_for_name(cid), "asOf": SCN["as_of"],
            "agentName": settings.mission_agent_name, "reviewer": settings.barrier_agent_name,
            "title": k["title"], "question": k["question"].format(name=_client_for_name(cid)), "deliverable": k["deliverable"],
            "api": k["api"], "agentCan": k["agent"], "rulesView": rules_view(kind, cid), "conflict": lines_conflict(cid),
            "lines": [{"line": r["business_line"], "stance": r["stance"], "action": r["proposed_action"], "rationale": r["rationale"],
                       "policy": r["policy_ref"]} for r in ls],
            "harness": [{"step": s, "title": t, "detail": d} for s, t, d in HARNESS]}


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def _parse(frame: str) -> tuple[str, dict]:
    ev, data = "message", {}
    for line in frame.splitlines():
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            try:
                data = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                data = {}
    return ev, data


RETRY_HINT = ("\n\nHARNESS RETRY: your previous run failed because a Work IQ search returned more than the tool's size cap. Search "
              "mail ONLY with the client's name in quotes, at most 3 results, subject and preview fields only.")


async def _mock_agent(kind: str, cid: str) -> AsyncGenerator[str, None]:
    from .iq import iq_event, message_event, token_event
    for iq in ("work", "foundry", "web", "fabric"):
        await asyncio.sleep(0.2)
        yield sse("tool_call", {"iq": iq, "tool": f"mock-{iq}", "detail": f'"{_client_for_name(cid)}"', "error": "",
                                "results": [{"title": f"Mock {iq} result for {_client_for_name(cid)}", "meta": "mock"}]})
        yield iq_event(iq, "active", "mock")
    rows = "\n".join(f"| {r['business_line']} | {r['stance']} | ? | mock |" for r in lines(cid))
    text = (f"## Decision\nRULES VIEW: AGREE\nMOCK MODE - no agent ran.\n\n## What changed the decision\n- [Fabric IQ] mock\n\n"
            f"## Lines reconciled\n| Line | Position | Binds? | Why |\n|---|---|---|---|\n{rows}\n\n## What we will not do\n- Anything.\n\n"
            "## Banker brief\n- Configure Foundry.\n\n## Client message\nNONE - mock mode.\n\n## Evidence\n- none")
    for chunk in re.findall(r".{1,80}", text, re.S):
        yield token_event(chunk)
    yield message_event(text, [])
    yield sse("done", {"ok": True, "layers": ["work", "foundry", "web", "fabric"]})


async def run(user: User, kind: str, cid: str) -> AsyncGenerator[str, None]:
    run_id = uuid.uuid4().hex[:12]
    t0 = time.perf_counter()

    def h(step: str, state: str, title: str, detail: str = "", **data: Any) -> str:
        return sse("harness", {"runId": run_id, "step": step, "state": state, "title": title, "detail": detail,
                               "ms": round((time.perf_counter() - t0) * 1000), "data": data})

    logger.info("AUDIT mission %s run %s by %s for %s", kind, run_id, user.upn, cid)
    yield h("plan", "done", "Plan fixed in code", f"Agent {settings.mission_agent_name} · Work, Foundry, Web, Fabric IQ · CP-016 / CP-017 · "
            "prepares, never acts", limits=["No sending, committing, sizing, pricing, approving, wall-crossing or contacting",
                                            "Governed figures are authoritative", "Web IQ is context only",
                                            "Client copy passes guardrails and the barrier reviewer", "The banker decides"])
    pk, ls, rv = packet(cid), lines(cid), rules_view(kind, cid)
    yield h("packet", "done", f"{sum(len(s['facts']) for s in pk)} governed fact groups · {len(ls)} business-line positions",
            "Deterministic. This is everything an API can return.", packet=pk,
            lines=[{"line": r["business_line"], "stance": r["stance"], "action": r["proposed_action"], "rationale": r["rationale"],
                    "policy": r["policy_ref"]} for r in ls], rulesView=rv, conflict=lines_conflict(cid))

    yield h("agent", "running", "Agent investigating", f"{settings.mission_agent_name} - Work IQ, Foundry IQ, Web IQ, Fabric IQ")
    text, layers, tool_errors, calls, used = "", [], [], 0, set()
    ev = _new_evidence()
    base, hint = prompt(kind, cid, pk, ls, rv), ""
    for attempt in (1, 2):
        held: list[str] = []
        src = _mock_agent(kind, cid) if settings.mock_mode else run_agent(user, base + hint, None, settings.mission_agent_name, trace=True)
        async for frame in src:
            ev_name, data = _parse(frame)
            if ev_name == "done":
                layers = data.get("layers", []) or []
                tool_errors += data.get("toolErrors", []) or []
                continue
            if ev_name == "error":
                held.append(frame)
                tool_errors.append(f"{data.get('text', '')} {data.get('detail', '')}".strip())
                continue
            if ev_name == "message":
                text = data.get("text", "")
                _add_citations(ev, data.get("citations") or [])
            if ev_name == "tool_call":
                calls += 1
                if data.get("iq"):
                    used.add(data["iq"])
                _add_call(ev, data, cid == HERO)
            yield frame
        too_big = any(re.search(r"maximum allowed size|exceeds", e, re.I) for e in tool_errors)
        throttled = any(re.search(r"\b429\b|rate.?limit", e, re.I) for e in tool_errors)
        if text or attempt == 2 or not (too_big or throttled):
            for f in held if not text else []:
                yield f
            break
        if throttled:
            yield h("agent", "running", "Harness recovery: model rate limit - waiting 20s, then retrying once", tool_errors[-1][:240])
            await asyncio.sleep(20)
        else:
            yield h("agent", "running", "Harness recovery: a Work IQ search was too large - retrying with narrower searches", tool_errors[-1][:240])
            hint = RETRY_HINT
        tool_errors = []
    if not text:
        yield h("agent", "failed", "The agent returned no answer", "; ".join(tool_errors)[:400])
        yield sse("done", {"ok": False, "runId": run_id})
        return
    used |= set(layers)
    snap = {"clientId": cid, "kind": kind, "runId": run_id, "agent": settings.mission_agent_name,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "restricted": cid == HERO,
            "layers": {k: {"queries": v["queries"][:6], "results": v["results"][:8], "used": k in used} for k, v in ev.items()}}
    EVIDENCE[cid] = snap
    yield h("agent", "done", f"{calls or len(layers)} tool call(s) across {len(used)} IQ layer(s)",
            ("Tool errors: " + "; ".join(tool_errors))[:400] if tool_errors else "", layers=sorted(used), calls=calls, evidence=snap)

    secs = sections(text)
    msg = client_message(secs)
    cks = guardrails(cid, text, secs, msg, pk, used)
    v = "blocked" if any(c["status"] == "block" for c in cks) else "needs_approval" if any(c["status"] == "warn" for c in cks) else "pass"
    flag, why = rules_flag(secs)
    nb, nw = sum(c["status"] == "block" for c in cks), sum(c["status"] == "warn" for c in cks)
    yield h("guardrails", "done", {"pass": "All guardrails passed", "needs_approval": f"{nw} warning(s) - banker attention",
                                   "blocked": f"{nb} block(s) - client copy cannot be used"}[v], "",
            checks=cks, verdict=v, clientMessage=msg, rulesFlag=flag, rulesReason=why)

    review_verdict = ""
    if not msg:
        yield h("review", "skipped", "No client message to review", none_reason(secs) or "The agent chose no written contact.")
    elif v == "blocked":
        yield h("review", "skipped", "Blocked before review", "The guardrails blocked the client copy, so the reviewer is not asked to polish it.")
    else:
        yield h("review", "running", "Barrier reviewer reading the client message", settings.barrier_agent_name)
        review = ""
        if settings.mock_mode:
            from .iq import message_event
            rsrc = _one(message_event("VERDICT: NEEDS FIXES\n\nMock mode - the reviewer did not run.", []))
        else:
            rsrc = run_agent(user, review_prompt(cid, msg, cks), None, settings.barrier_agent_name)
        async for frame in rsrc:
            rev, data = _parse(frame)
            if rev in ("token", "message", "error"):
                if rev == "message":
                    review = data.get("text", "")
                yield sse(f"review_{rev}", data)
        mv = re.search(r"VERDICT:\s*(PASS|NEEDS FIXES|BLOCKED)", review, re.I)
        review_verdict = mv.group(1).upper() if mv else ""
        yield h("review", "done" if review else "failed", f"Reviewer verdict: {review_verdict or 'none returned'}", verdict=review_verdict)

    RUNS[run_id] = {"kind": kind, "clientId": cid, "guardrails": v, "review": review_verdict, "rulesFlag": flag, "rulesReason": why,
                    "layers": sorted(used), "calls": calls}
    while len(RUNS) > 200:
        RUNS.popitem(last=False)
    yield h("human", "waiting", "Awaiting your decision", "Approve, send back or escalate")
    yield sse("done", {"ok": True, "runId": run_id})


async def _one(frame: str) -> AsyncGenerator[str, None]:
    yield frame


# --------------------------------------------------------------------------- #
# Decisions, audit and the "agent changed the answer" KPI
# --------------------------------------------------------------------------- #
def decide(user: User, kind: str, cid: str, run_id: str, decision: str, note: str, client_view: dict) -> dict:
    r = RUNS.get(run_id)
    if r and (r["kind"] != kind or r["clientId"] != cid):
        raise ValueError("Run does not match this mission and client.")
    src = r or {k: client_view.get(k, "") for k in ("guardrails", "review", "rulesFlag", "rulesReason")}
    rec = {"runId": run_id, "kind": kind, "clientId": cid, "client": _client_for_name(cid), "decision": decision, "note": note[:400],
           "by": user.upn, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "guardrails": src.get("guardrails", ""), "review": src.get("review", ""),
           "rulesFlag": src.get("rulesFlag", ""), "rulesReason": src.get("rulesReason", ""), "runFound": bool(r)}
    AUDIT.appendleft(rec)
    # One structured line per decision: Container Apps ships stdout to Log Analytics, so every replica's
    # decisions are visible to stats() regardless of which replica served the run.
    print("MISSION_AUDIT " + json.dumps(rec), flush=True)
    logger.info("AUDIT mission decision %s %s %s by %s", kind, cid, decision, user.upn)
    return rec


_stats_cache: tuple[list[dict], float] | None = None


async def _logged() -> list[dict]:
    global _stats_cache
    if _stats_cache and _stats_cache[1] > time.time():
        return _stats_cache[0]
    rows: list[dict] = []
    if settings.log_analytics_workspace_id and not settings.mock_mode:
        try:
            from .telemetry import LOG_ANALYTICS_URL, _access_token
            q = ("ContainerAppConsoleLogs_CL | where TimeGenerated > ago(30d) | where ContainerAppName_s == 'ca-cmci-bff' "
                 "| where Log_s has 'MISSION_AUDIT ' | project Log_s | take 500")
            token = await _access_token()
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(LOG_ANALYTICS_URL.format(ws=settings.log_analytics_workspace_id), json={"query": q},
                                      headers={"Authorization": f"Bearer {token}"})
            if r.status_code < 400:
                for row in (r.json().get("tables") or [{}])[0].get("rows", []):
                    line = str(row[0])
                    try:
                        rows.append(json.loads(line[line.index("MISSION_AUDIT ") + 14:]))
                    except (ValueError, json.JSONDecodeError):
                        continue
            else:
                logger.warning("mission stats query %s: %s", r.status_code, r.text[:200])
        except Exception as exc:  # noqa: BLE001
            logger.warning("mission stats query failed: %s", exc)
    _stats_cache = (rows, time.time() + 60)
    return rows


async def stats() -> dict:
    seen: dict[str, dict] = {}
    for rec in list(await _logged()) + list(AUDIT):
        seen[rec.get("runId", "") + rec.get("at", "")] = rec
    recs = sorted(seen.values(), key=lambda r: r.get("at", ""), reverse=True)
    by_run: dict[str, dict] = {}
    for rec in recs:
        by_run.setdefault(rec.get("runId", ""), rec)
    runs = list(by_run.values())
    changed = [r for r in runs if r.get("rulesFlag") == "CHANGED"]
    return {"decided": len(runs), "changed": len(changed), "agreed": sum(r.get("rulesFlag") == "AGREE" for r in runs),
            "approved": sum(r.get("decision") == "approve" for r in runs),
            "blocked": sum(r.get("guardrails") == "blocked" for r in runs),
            "recent": [{k: r.get(k, "") for k in ("client", "kind", "rulesFlag", "rulesReason", "decision", "at", "by")} for r in runs[:8]]}
