"""Covenant stress test and credit papers for ANY company in the book.

The Guided story's skills are built around Gibson's live deal: an incremental
commitment, Gibson's own net debt and EBITDA, and a Control Room restriction.
The other nine relationships have no deal on the table and no absolute balance
sheet in the dataset - so nothing here invents one. Instead:

  * Stress - an EBITDA shock is applied directly to each EBITDA-linked covenant
    ratio. Net debt and interest do not move with EBITDA, so for a maximum
    leverage covenant the stressed ratio is actual / (1 + shock) and for a
    minimum coverage covenant actual x (1 + shock). That is exact, and needs no
    figure the dataset does not hold. Debt capacity is expressed in turns of
    EBITDA, not CAD.
  * Papers - a credit review memo built from the company's own limits,
    covenants, rating, KYC and the dashboard's opportunity / risk / data-quality
    findings, with rule-based actions citing the policy. A sector note is added
    only where the company's sector envelope is Amber; a Control Room request
    only where a restriction applies.

Gibson keeps the deal papers (papers.py) so the dashboard and the Guided story
never disagree about it.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .papers import FABRIC, FOUNDRY, WORK
from .papers import build as build_deal_papers
from .skill_data import SKILL_DATA
from .skills import STRESS_SHOCKS

HERO = SKILL_DATA["client"]["id"]


def _client(cid: str) -> dict[str, Any]:
    c = SKILL_DATA["clients"].get(cid)
    if not c:
        raise KeyError(f"Unknown client {cid}")
    return c


def _band(headroom: float) -> tuple[str, str]:
    """CP-005 headroom bands, in turns."""
    if headroom <= 0:
        return "Breach", "bad"
    if headroom < 0.35:
        return "Tight", "warn"
    if headroom <= 0.75:
        return "Monitor", "warn"
    return "Comfortable", "ok"


def _ebitda_linked(cov: dict[str, Any]) -> str | None:
    name = cov["covenant"]
    if cov["unit"] != "x" or "EBITDA" not in name:
        return None
    return "leverage" if cov["test"] == "maximum" else "coverage"


def _stressed(cov: dict[str, Any], shock: float) -> float:
    k = 1 + shock / 100
    return cov["actual"] / k if _ebitda_linked(cov) == "leverage" else cov["actual"] * k


def _headroom(cov: dict[str, Any], value: float) -> float:
    return cov["threshold"] - value if cov["test"] == "maximum" else value - cov["threshold"]


def _cushion(cov: dict[str, Any]) -> float:
    """% fall in EBITDA that takes this covenant to its threshold."""
    if _ebitda_linked(cov) == "leverage":
        return (1 - cov["actual"] / cov["threshold"]) * 100
    return (1 - cov["threshold"] / cov["actual"]) * 100


def stress(cid: str) -> dict[str, Any]:
    c = _client(cid)
    rows = []
    for cov in c["covenants"]:
        kind = _ebitda_linked(cov)
        if not kind:
            continue
        cells = []
        for s in STRESS_SHOCKS:
            v = _stressed(cov, s)
            h = _headroom(cov, v)
            band, tone = _band(h)
            cells.append({"shock": s, "value": round(v, 2), "headroom": round(h, 2),
                          "band": band, "tone": tone})
        rows.append({
            "covenant": cov["covenant"], "kind": kind, "test": cov["test"],
            "threshold": cov["threshold"], "actual": cov["actual"], "prior": cov["prior"],
            "trend": ("deteriorating" if (cov["actual"] > cov["prior"]) == (kind == "leverage")
                      and cov["actual"] != cov["prior"] else
                      "improving" if cov["actual"] != cov["prior"] else "flat"),
            "cushion_pct": round(_cushion(cov), 1),
            "cells": cells,
        })
    if not rows:
        return {"client": c["name"], "id": cid, "rows": [], "shocks": STRESS_SHOCKS,
                "headline": "No EBITDA-linked covenant on record for this company."}

    binding = min(rows, key=lambda r: r["cushion_pct"])
    lev = next((r for r in rows if r["kind"] == "leverage"), None)
    capacity = round(lev["threshold"] - lev["actual"], 2) if lev else None
    breaches_at = next((cell["shock"] for cell in binding["cells"] if cell["band"] == "Breach"), None)
    headline = (
        f"{binding['covenant']} binds first: Adjusted EBITDA can fall "
        f"{binding['cushion_pct']}% before it breaches"
        + (f" - a {abs(breaches_at):.0f}% miss breaches it." if breaches_at is not None
           else ", and it survives every shock tested.")
    )
    return {
        "client": c["name"], "id": cid, "shocks": STRESS_SHOCKS, "rows": rows,
        "binding": binding["covenant"], "binding_cushion_pct": binding["cushion_pct"],
        "debt_capacity_turns": capacity,
        "headline": headline,
        "basis": ("Net debt and interest held constant; Adjusted EBITDA shocked. For a "
                  "maximum leverage covenant the stressed ratio is actual / (1 + shock); "
                  "for a minimum coverage covenant actual x (1 + shock). Debt capacity is in "
                  "turns of EBITDA - absolute net debt and EBITDA are not held for this client."),
        "hero": cid == HERO,
    }


def _days_to(d: str) -> int | None:
    try:
        return (date.fromisoformat(d) - date.fromisoformat(SKILL_DATA["client"]["as_of"])).days
    except ValueError:
        return None


def _actions(c: dict[str, Any], st: dict[str, Any]) -> list[list[str]]:
    out: list[list[str]] = []
    sn = next((l for l in c["limits"] if l["type"].startswith("Single-name")), None)
    for r in st["rows"]:
        h = _headroom(r, r["actual"])
        band, _ = _band(h)
        if band == "Breach":
            out.append([f"{r['covenant']} is in breach: escalate immediately; no new exposure.", f"{FOUNDRY} - CP-005 / CP-001"])
        elif band == "Tight":
            out.append([f"{r['covenant']} is Tight ({h:.2f} turns): monthly monitoring, a four-quarter projection, and notify the relationship owner; any incremental commitment needs a fully drawn pro-forma before it is offered.", f"{FOUNDRY} - CP-005"])
        elif band == "Monitor":
            out.append([f"{r['covenant']} is in the Monitor band ({h:.2f} turns): quarterly commentary in the portfolio report.", f"{FOUNDRY} - CP-005"])
    if st["rows"] and st["binding_cushion_pct"] < 10:
        out.append([f"Thin EBITDA cushion: {st['binding']} breaches on a {st['binding_cushion_pct']}% fall in Adjusted EBITDA - stress the next forecast before any new commitment.", "computed"])
    if sn and sn["utilisation_pct"] >= 85:
        out.append([f"Single-name limit {sn['utilisation_pct']}% used ({sn['status']}): new exposure needs the limit owner's written concurrence and a two-quarter utilisation forecast.", f"{FOUNDRY} - CP-001"])
    if c["watchlist"]:
        out.append(["On the watchlist: no new exposure without Credit Committee; keep the review cycle quarterly.", f"{FOUNDRY} - CP-001"])
    if c["trend"] == "deteriorating":
        moved = (f"{c['rating_prior']} -> {c['rating']}" if c["rating_prior"] != c["rating"]
                 else f"{c['rating']}, outlook negative")
        out.append([f"Rating trend deteriorating ({moved}): bring the annual credit review forward.", FABRIC])
    days = _days_to(c["kyc_refresh_due"])
    if days is not None and days <= 90:
        out.append([f"KYC refresh due {c['kyc_refresh_due']} ({days} days): no facility increase may be documented after that date until it completes.", f"{FOUNDRY} - CP-006"])
    if c["data_quality"]:
        out.append(["Reconcile the recorded source mismatches before relying on utilisation or wallet figures (see section 5).", FABRIC])
    if not out:
        out.append(["No policy trigger on current figures: business as usual, next scheduled review.", "computed"])
    return out


def papers(cid: str) -> dict[str, Any]:
    if cid == HERO:
        bundle = build_deal_papers()
        return {**bundle, "kind": "deal"}

    c = _client(cid)
    st = stress(cid)
    as_of = SKILL_DATA["client"]["as_of"]
    sector = SKILL_DATA["sector_limit"]
    sector_applies = bool(sector) and c["sector"].lower() in sector["name"].lower()
    sn = next((l for l in c["limits"] if l["type"].startswith("Single-name")), None)

    stress_table = {
        "head": ["Covenant", "Today"] + [("Base" if s == 0 else f"EBITDA {s:+.0f}%") for s in STRESS_SHOCKS[1:]],
        "rows": [[r["covenant"], f"{r['actual']}x vs {r['threshold']}x"]
                 + [f"{cell['value']}x {cell['band']}" for cell in r["cells"][1:]]
                 for r in st["rows"]],
    }

    review = {
        "id": "cc",
        "title": f"Credit review memo - {c['name']}",
        "addressee": "Credit Committee" if (c["watchlist"] or any(
            _band(_headroom(r, r["actual"]))[0] in ("Tight", "Breach") for r in st["rows"])
            or (sn and sn["utilisation_pct"] >= 85)) else "Credit Risk (sector director)",
        "policies": ["CP-001", "CP-005", "CP-006"] + (["CP-002"] if sector_applies else []),
        "sections": [
            {"heading": "1. Relationship", "rows": [
                ["Obligor", f"{c['name']} ({c['ticker']}) - {c['sector']} / {c['sub_sector']}", FABRIC],
                ["Coverage tier", c["tier"], FABRIC],
                ["Internal rating", f"{c['rating']} (prior {c['rating_prior']}), trend {c['trend']}"
                 + (" - WATCHLIST" if c["watchlist"] else ""), FABRIC],
                ["KYC refresh due", c["kyc_refresh_due"], f"{FABRIC} / {FOUNDRY} - CP-006"],
                ["Last coverage meeting", c["last_meeting"], FABRIC],
            ]},
            {"heading": "2. Limits", "rows": [
                [l["type"], f"CAD {l['utilised']:,.1f}m of {l['limit']:,.1f}m - {l['utilisation_pct']}%, {l['status']} (owner: {l['owner']})", f"{FABRIC} / {FOUNDRY} - CP-001"]
                for l in c["limits"]
            ] + ([["Sector envelope", f"{sector['name']}: {sector['utilisation_pct']}% used, {sector['status']} (owner: {sector['owner']})", f"{FABRIC} / {FOUNDRY} - CP-002"]] if sector_applies else [])},
            {"heading": "3. Covenants", "rows": [
                [v["covenant"], f"{v['actual']}{v['unit']} vs {v['test']} {v['threshold']}{v['unit']} "
                 f"(prior {v['prior']}{v['unit']}) - {v['headroom']}{v['unit']} headroom, {v['status']}; next test {v['next_test']}", FABRIC]
                for v in c["covenants"]
            ]},
            {"heading": "4. EBITDA stress", "table": stress_table,
             "source": "computed - " + st["basis"]},
            {"heading": "5. Findings from the dashboard", "lines": [
                [f"Opportunity (analytical lead, not approval): {c['opportunity']}", FABRIC],
                [f"Risk: {c['risk']}", f"{FABRIC} / {FOUNDRY}"],
            ] + [[f"Data quality: {q}", FABRIC] for q in c["data_quality"]]},
            {"heading": "6. Recommended actions", "lines": _actions(c, st)},
            {"heading": "7. Not decided here", "lines": [
                ["Limit changes, new commitments and watchlist decisions rest with the approval authority named in CP-001 / CP-003; this memo prepares the decision.", f"{FOUNDRY} - CP-001 / CP-003"],
            ]},
        ],
        "signoff": [{"role": r, "decision": "", "name": "", "date": ""}
                    for r in ("Sector Credit Risk director", "Credit Committee chair")],
    }
    out = [review]

    if sector_applies and sector["status"] in ("Amber", "Breach"):
        share = round(sn["utilised"] / sector["utilised"] * 100, 1) if sn and sector["utilised"] else None
        out.append({
            "id": "pm",
            "title": f"Portfolio Management - sector envelope note, {c['name']}",
            "addressee": "Portfolio Management / Chief Risk Officer",
            "policies": ["CP-002"],
            "sections": [
                {"heading": "1. Sector position", "rows": [
                    ["Envelope", f"{sector['name']}: CAD {sector['utilised']:,.0f}m of {sector['limit']:,.0f}m - {sector['utilisation_pct']}%, {sector['status']}", FABRIC],
                    ["This obligor", f"CAD {sn['utilised']:,.1f}m single-name utilisation" + (f" - {share}% of the sector" if share is not None else ""), FABRIC] if sn else ["This obligor", "No single-name limit recorded", FABRIC],
                ]},
                {"heading": "2. Rule", "lines": [
                    ["While the sector is Amber, any new commitment to this obligor needs Portfolio Management sign-off and an identified offset (syndication, sell-down, maturing facility or approved distribution plan).", f"{FOUNDRY} - CP-002"],
                    ["Allocation between competing requests in the sector is reserved to the Chief Risk Officer.", f"{FOUNDRY} - CP-002"],
                ]},
            ],
            "signoff": [{"role": r, "decision": "", "name": "", "date": ""}
                        for r in ("Portfolio Management", "Chief Risk Officer")],
        })

    return {
        "kind": "review",
        "as_of": as_of,
        "inputs": {"client_id": cid},
        "status": "DRAFT - prepared by the agent from governed data. Not approved. "
                  "Requires the human sign-offs below.",
        "confidential": "INTERNAL - confidential under CP-014. Not for disclosure to the client.",
        "papers": out,
        "notes": ["No Control Room paper: no restriction is recorded for this company."],
    }
