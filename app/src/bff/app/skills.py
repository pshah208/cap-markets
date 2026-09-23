"""Chat skills - the actions offered under an agent answer.

WHY THE MATHS LIVES HERE AND NOT IN THE UI
------------------------------------------
CP-005 makes the pro-forma covenant test a *control*, not a presentation:

    "Before any of the following is presented to a client, Credit Risk must
    produce a pro-forma covenant calculation..."
    "The pro-forma test assumes the facility is fully drawn at the test date."
    "Coverage may request it; coverage may not perform it, waive it, or
    pre-empt it."

So the number has to be computed deterministically from the governed figures,
and it has to be able to come back "no". That rules out asking the model to
compute it, and it rules out doing it in the browser where it would sit next to
the presentation layer. It is arithmetic over two facts from
`data/scenario_facts.py`, and it either clears the threshold or it does not.

The three skills:

  * `proforma`  - CP-005 test. Given an incremental commitment, fully drawn,
                  what does Total Net Debt / Adjusted EBITDA become, and what is
                  the largest commitment that still clears?
  * `roomcard`  - the meeting brief the demo's own persona goal asks for:
                  what we can say, what we cannot, and who may not be asked.
  * `radar`     - the same covenant test across the whole book, because Gibson
                  is not the tightest name in it.
"""

from __future__ import annotations

from typing import Any

from .skill_data import SKILL_DATA


# --------------------------------------------------------------------------- #
# CP-005 pro-forma
# --------------------------------------------------------------------------- #

def proforma(incremental_m: float) -> dict[str, Any]:
    """Pro-forma leverage for an incremental commitment, assumed fully drawn.

    `incremental_m` is the increase in COMMITTED capacity at the client level
    (1,100 -> 1,350 is 250), not the firm's own hold. The covenant tests the
    borrower's total net debt, which is why routing the exposure to a different
    facility changes nothing - a point CP-001 and CP-005 both make and the agent
    is instructed to repeat.
    """
    fin = SKILL_DATA["financials"]
    cov = SKILL_DATA["covenant"]

    ebitda = float(fin["adjusted_ebitda_ltm_m"])
    net_debt = float(fin["total_net_debt_m"])
    threshold = float(cov["threshold"])

    inc = max(0.0, float(incremental_m))
    pro_forma = (net_debt + inc) / ebitda
    headroom = threshold - pro_forma

    # Largest incremental commitment that still clears, fully drawn.
    max_clearing = threshold * ebitda - net_debt

    # CP-005 headroom bands, in turns.
    if headroom <= 0:
        band, tone = "Breach", "bad"
    elif headroom < 0.35:
        band, tone = "Tight", "warn"
    elif headroom <= 0.75:
        band, tone = "Monitor", "warn"
    else:
        band, tone = "Comfortable", "ok"

    return {
        "incremental_m": round(inc, 1),
        "ebitda_m": ebitda,
        "net_debt_m": net_debt,
        "pro_forma_net_debt_m": round(net_debt + inc, 1),
        "current_leverage": round(net_debt / ebitda, 2),
        "pro_forma_leverage": round(pro_forma, 2),
        "threshold": threshold,
        "headroom_turns": round(headroom, 2),
        "band": band,
        "tone": tone,
        "clears": headroom > 0,
        "max_clearing_m": round(max_clearing, 1),
        "shrink_required_m": round(max(0.0, inc - max_clearing), 1),
    }


def proforma_verdict(result: dict[str, Any]) -> str:
    """One sentence a banker can paste into a credit note."""
    if result["clears"]:
        return (
            f"Pro-forma {result['pro_forma_leverage']}x against a "
            f"{result['threshold']}x maximum - clears with "
            f"{result['headroom_turns']} turns ({result['band']}). "
            f"Fully-drawn basis per CP-005."
        )
    return (
        f"Pro-forma {result['pro_forma_leverage']}x against a "
        f"{result['threshold']}x maximum - DOES NOT CLEAR. The largest "
        f"incremental commitment that clears fully drawn is CAD "
        f"{result['max_clearing_m']}m, so the request must reduce by CAD "
        f"{result['shrink_required_m']}m. Pro-forma test required before the "
        f"pitch under CP-005; owned by the sector Credit Risk director."
    )


# --------------------------------------------------------------------------- #
# Room card
# --------------------------------------------------------------------------- #

def roomcard() -> dict[str, Any]:
    """The meeting brief: what may be said, what may not, and by whom."""
    d = SKILL_DATA
    limits = d["limits"]
    sector = d["sector_limit"]
    cov = d["covenant"]
    pf = proforma(
        d["opportunities"]["revolver_upsize"]["proposed_commitment_total_m"]
        - d["opportunities"]["revolver_upsize"]["current_commitment_total_m"]
    )

    binding = []
    lev = next((c for c in d["covenants_all"]
                if "Total Net Debt" in c["covenant"]), None)
    if lev:
        binding.append({
            "what": lev["covenant"],
            "position": f"{lev['actual']}{lev['unit']} of {lev['threshold']}"
                        f"{lev['unit']} - {lev['headroom']}{lev['unit']} headroom",
            "trend": f"was {lev['prior']}{lev['unit']} last quarter",
            "status": lev["status"],
            "owner": "Credit Risk - sector director (CP-005)",
        })
    if sector and sector["status"] in ("Amber", "Breach"):
        binding.append({
            "what": sector["name"],
            "position": f"{sector['utilisation_pct']}% used - "
                        f"CAD {sector['headroom']}m left",
            "trend": "",
            "status": sector["status"],
            "owner": f"{sector['owner']} (CP-002)",
        })
    for lim in limits:
        if lim["status"] in ("Amber", "Breach"):
            binding.append({
                "what": lim["type"],
                "position": f"{lim['utilisation_pct']}% used - "
                            f"CAD {lim['headroom']}m left",
                "trend": "",
                "status": lim["status"],
                "owner": lim["owner"],
            })

    say = [
        "Relationship history, public filings and publicly reported results.",
        "Existing facilities and their administration - business as usual.",
        "Indicative appetite framed as subject to credit approval, with no number.",
        "Anything already in the public domain, cited and dated.",
    ]
    do_not_say = [
        f"Any committed number on the revolver upsize before the CP-005 "
        f"pro-forma test is signed - it currently comes back "
        f"{pf['pro_forma_leverage']}x against a {pf['threshold']}x maximum.",
        "Internal limits, utilisation, covenant headroom, sector capacity, "
        "wallet share or the internal risk rating - confidential under CP-014.",
        "Any solicitation of the hedging overlay, formal or informal, until the "
        f"Control Room clears {d['restriction']['id']} - CP-008 has no informal "
        "exemption.",
        "The existence of a wall-crossing, who is crossed, or the underlying "
        "subject matter - CP-008 and CP-009.",
        "Internal 'indicative' public ratings - quote the agency, from the web.",
    ]

    return {
        "client": d["client"],
        "meeting": d["meeting"],
        "asks": [
            {"id": o["id"], "name": o["name"],
             "size": o.get("proposed_commitment_total_m")
                     or o.get("notional_m") or o.get("indicative_size_m"),
             "decision_by": o.get("decision_needed_by", "")}
            for o in d["opportunities"].values()
        ],
        "binding": binding,
        "restriction": d["restriction"],
        "proforma": pf,
        "verdict": proforma_verdict(pf),
        "say": say,
        "do_not_say": do_not_say,
        "confidential": (
            "INTERNAL - contains limit, covenant and restricted-list "
            "information. Not for disclosure to the client (CP-014)."
        ),
    }


# --------------------------------------------------------------------------- #
# Portfolio radar
# --------------------------------------------------------------------------- #

def radar() -> dict[str, Any]:
    """The leverage covenant across the whole book, tightest first."""
    entries = []
    for r in SKILL_DATA["radar"]:
        moved = round(r["actual"] - r["prior"], 2)
        entries.append({
            **r,
            "moved": moved,
            "deteriorating": moved > 0,
            "tone": ("bad" if r["status"] == "Breach"
                     else "warn" if r["status"] == "Amber" else "ok"),
        })
    tight = [e for e in entries if e["headroom"] < 0.35]
    return {
        "as_of": SKILL_DATA["client"]["as_of"],
        "entries": entries,
        "tight_count": len(tight),
        "hero_id": SKILL_DATA["client"]["id"],
        "note": (
            f"{len(tight)} of {len(entries)} names sit inside the CP-005 "
            f"'Tight' band of 0.35 turns. Tight requires monthly monitoring, a "
            f"four-quarter projection and notification to the relationship "
            f"owner."
        ),
    }


def catalogue() -> dict[str, Any]:
    """Everything the SPA needs to render the skill bar and its artifacts."""
    return {
        "client": SKILL_DATA["client"],
        "covenant": SKILL_DATA["covenant"],
        "financials": {
            # The basis is shown to the user; the raw figures drive the slider.
            "adjusted_ebitda_ltm_m": SKILL_DATA["financials"]["adjusted_ebitda_ltm_m"],
            "total_net_debt_m": SKILL_DATA["financials"]["total_net_debt_m"],
            "as_of": SKILL_DATA["financials"]["as_of"],
            "basis": SKILL_DATA["financials"]["basis"],
        },
        "leverage_history": SKILL_DATA["leverage_history"],
        "opportunities": SKILL_DATA["opportunities"],
        "roomcard": roomcard(),
        "radar": radar(),
    }
