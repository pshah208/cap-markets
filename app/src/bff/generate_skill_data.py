"""Generate `app/skill_data.py` from the real demo data.

WHY A GENERATOR RATHER THAN A TRANSCRIPTION
-------------------------------------------
The BFF container image only copies `src/bff`, so it cannot read
`data/fabric-iq/*.csv` at runtime. Hand-transcribing a catalogue into the BFF
works only until someone edits the source and forgets the copy.

This does the transcription mechanically instead: it reads `scenario_facts.py`
and the generated CSVs, and writes a Python module the BFF imports. Re-run it
after any change to the dataset and the drift cannot happen silently -- and
`validate_dataset.py` re-checks the same figures independently.

    python generate_skill_data.py            # rewrite app/skill_data.py
    python generate_skill_data.py --check    # fail if it is stale (CI)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parents[2] / "data"
FABRIC = DATA / "fabric-iq"
OUT = HERE / "app" / "skill_data.py"

sys.path.insert(0, str(DATA))
from scenario_facts import FACTS, PEOPLE  # noqa: E402


def rows(name: str) -> list[dict[str, str]]:
    with (FABRIC / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def f(v: str | None) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def build() -> dict:
    hero = FACTS["hero_client_id"]
    fin = FACTS["client_financials"]
    cov_t = FACTS["covenant_tension"]
    mnpi = FACTS["mnpi_tension"]
    meeting = FACTS["meeting"]

    covenants = rows("covenants.csv")
    limits = rows("limits_utilization.csv")
    ratings = rows("risk_ratings.csv")
    team = rows("coverage_team.csv")
    facilities = rows("credit_facilities.csv")

    hero_cov = [c for c in covenants if c["client_id"] == hero]
    hero_lim = [r for r in limits if r["client_id"] == hero]
    sector = next(
        (r for r in limits if r["limit_type"] == "Sector concentration limit"), None,
    )

    # Leverage history, oldest first -- the sparkline behind the pro-forma.
    history = [
        {"as_of": r["as_of_date"], "leverage": f(r["net_debt_to_ebitda"]),
         "rating": r["internal_risk_rating"]}
        for r in ratings if r["client_id"] == hero
    ]
    history.sort(key=lambda r: r["as_of"])

    # Portfolio radar -- the leverage covenant for every client in the book.
    radar = []
    for c in covenants:
        if "Total Net Debt" not in c["covenant"]:
            continue
        radar.append({
            "client_id": c["client_id"],
            "client": c["client_name"],
            "threshold": f(c["threshold"]),
            "actual": f(c["actual"]),
            "prior": f(c["prior_quarter_actual"]),
            "headroom": f(c["headroom"]),
            "utilisation_pct": f(c["utilisation_pct"]),
            "status": c["status"],
            "next_test": c["next_test_date"],
        })
    radar.sort(key=lambda r: -r["utilisation_pct"])

    # Every client in the book, for the dashboard's per-company stress test and
    # credit papers. Only figures that exist for that client are carried - no
    # client other than the hero has absolute net debt or EBITDA, so none is
    # invented here.
    clients_csv = rows("clients.csv")
    snapshot_path = HERE.parent / "web" / "src" / "dashboard" / "snapshot.json"
    snap = {c["id"]: c for c in json.loads(snapshot_path.read_text(encoding="utf-8"))["companies"]}
    clients: dict[str, dict] = {}
    for c in clients_csv:
        cid = c["client_id"]
        s = snap.get(cid, {})
        clients[cid] = {
            "id": cid, "name": c["client_name"], "ticker": c["ticker"],
            "sector": c["sector"], "sub_sector": c["sub_sector"],
            "tier": c["coverage_tier"], "rating": c["internal_risk_rating"],
            "rating_prior": c["internal_risk_rating_prior"], "trend": c["risk_trend"],
            "watchlist": c["watchlist_flag"] == "Y",
            "kyc_refresh_due": c["kyc_refresh_due"], "last_meeting": c["last_meeting_date"],
            "covenants": [
                {"covenant": v["covenant"], "test": v["test_type"],
                 "threshold": f(v["threshold"]), "actual": f(v["actual"]),
                 "prior": f(v["prior_quarter_actual"]), "unit": v["unit"],
                 "headroom": f(v["headroom"]), "status": v["status"],
                 "last_tested": v["last_tested_date"], "next_test": v["next_test_date"]}
                for v in covenants if v["client_id"] == cid
            ],
            "limits": [
                {"id": r["limit_id"], "type": r["limit_type"],
                 "limit": f(r["limit_cad_m"]), "utilised": f(r["utilised_cad_m"]),
                 "headroom": f(r["headroom_cad_m"]),
                 "utilisation_pct": f(r["utilisation_pct"]),
                 "status": r["status"], "owner": r["limit_owner"]}
                for r in limits if r["client_id"] == cid
            ],
            "facilities": [
                {"id": r["facility_id"], "type": r["facility_type"],
                 "commitment": f(r["commitment_cad_m"]), "drawn": f(r["drawn_cad_m"]),
                 "maturity": r["maturity_date"]}
                for r in facilities if r["client_id"] == cid
            ],
            "opportunity": s.get("opportunity", ""),
            "risk": s.get("risk", ""),
            "data_quality": s.get("dataQuality", []),
        }

    by_alias = {p["alias"]: p for p in PEOPLE}
    attendees = []
    for alias in meeting["bank_attendees"]:
        p = by_alias.get(alias, {})
        row = next((t for t in team
                    if t["client_id"] == hero and t["alias"] == alias), {})
        attendees.append({
            "alias": alias,
            "name": p.get("displayName", alias),
            "title": p.get("title", ""),
            "department": p.get("department", ""),
            # wall_status is an internal control field. It is included so the
            # room card can mark who may not be asked about the restriction --
            # the card is an INTERNAL artifact and never leaves the firm.
            "wall_status": row.get("wall_status") or p.get("wall_status", ""),
            "restricted": alias in mnpi["restricted_persons"],
        })

    return {
        "client": {
            "id": hero,
            "name": FACTS["hero_client_name"],
            "ticker": FACTS["hero_ticker"],
            "as_of": FACTS["as_of"],
            "currency": FACTS["currency"],
        },
        "financials": {
            "adjusted_ebitda_ltm_m": fin["adjusted_ebitda_ltm_m"],
            "total_net_debt_m": fin["total_net_debt_m"],
            "as_of": fin["as_of"],
            "basis": fin["basis"],
        },
        "covenant": {
            "name": cov_t["covenant"],
            "threshold": cov_t["threshold"],
            "actual": cov_t["actual"],
            "prior": cov_t["prior_quarter_actual"],
            "headroom_turns": cov_t["headroom_turns"],
            "next_test": next((c["next_test_date"] for c in hero_cov
                               if "Total Net Debt" in c["covenant"]), ""),
            "source_facility": next((c["source_facility"] for c in hero_cov
                                     if "Total Net Debt" in c["covenant"]), ""),
        },
        "covenants_all": [
            {"covenant": c["covenant"], "test": c["test_type"],
             "threshold": f(c["threshold"]), "actual": f(c["actual"]),
             "prior": f(c["prior_quarter_actual"]), "unit": c["unit"],
             "headroom": f(c["headroom"]),
             "utilisation_pct": f(c["utilisation_pct"]), "status": c["status"]}
            for c in hero_cov
        ],
        "limits": [
            {"id": r["limit_id"], "type": r["limit_type"],
             "limit": f(r["limit_cad_m"]), "utilised": f(r["utilised_cad_m"]),
             "headroom": f(r["headroom_cad_m"]),
             "utilisation_pct": f(r["utilisation_pct"]),
             "status": r["status"], "owner": r["limit_owner"]}
            for r in hero_lim
        ],
        "sector_limit": {
            "name": sector["client_name"], "limit": f(sector["limit_cad_m"]),
            "utilised": f(sector["utilised_cad_m"]),
            "headroom": f(sector["headroom_cad_m"]),
            "utilisation_pct": f(sector["utilisation_pct"]),
            "status": sector["status"], "owner": sector["limit_owner"],
        } if sector else None,
        "facilities": [
            {"id": r["facility_id"], "type": r["facility_type"],
             "commitment": f(r["commitment_cad_m"]), "drawn": f(r["drawn_cad_m"]),
              "maturity": r["maturity_date"], "role": r["bank_role"]}
            for r in facilities if r["client_id"] == hero
        ],
        "leverage_history": history,
        "opportunities": FACTS["opportunities"],
        "meeting": {
            "id": meeting["id"], "date": meeting["date"],
            "time_local": meeting["time_local"], "location": meeting["location"],
            "title": meeting["title"], "agenda": meeting["agenda"],
            "client_attendees": meeting["client_attendees"],
            "attendees": attendees,
        },
        "restriction": {
            "id": mnpi["id"], "raised_by": mnpi["raised_by"],
            "raised_on": mnpi["raised_on"], "expires": mnpi["expires"],
            "effect": mnpi["effect"],
        },
        "radar": radar,
        "clients": clients,
        "metrics": FACTS["hero_metrics"],
    }


TEMPLATE = '''"""Demo facts the chat skills render. GENERATED -- do not edit by hand.

Produced by `generate_skill_data.py` from `data/scenario_facts.py` and
`data/fabric-iq/*.csv`. The BFF image copies only `src/bff`, so the figures are
baked in here rather than read from the dataset at runtime. Re-run the generator
after any dataset change.

Generated {stamp}.
"""

from __future__ import annotations

from typing import Any

SKILL_DATA: dict[str, Any] = {payload}
'''


def render() -> str:
    payload = json.dumps(build(), indent=4, ensure_ascii=False)
    # json.dumps emits JS literals; Python needs its own.
    payload = (payload.replace(": true", ": True")
                      .replace(": false", ": False")
                      .replace(": null", ": None"))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return TEMPLATE.format(stamp=stamp, payload=payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the generated file is stale")
    args = ap.parse_args()

    new = render()
    if args.check:
        if not OUT.exists():
            print(f"FAIL {OUT.name} does not exist - run the generator")
            return 1
        # The date stamp changes every day and is not a drift signal.
        strip = lambda s: "\n".join(  # noqa: E731
            l for l in s.splitlines() if not l.startswith("Generated "))
        if strip(OUT.read_text(encoding="utf-8")) != strip(new):
            print(f"FAIL {OUT.name} is stale - re-run generate_skill_data.py")
            return 1
        print(f"OK   {OUT.name} matches the dataset")
        return 0

    OUT.write_text(new, encoding="utf-8")
    d = build()
    print(f"wrote {OUT.relative_to(HERE)}  ({len(new):,} chars)")
    print(f"  client            {d['client']['name']} ({d['client']['ticker']})")
    print(f"  leverage history  {len(d['leverage_history'])} quarters")
    print(f"  covenants         {len(d['covenants_all'])}")
    print(f"  limits            {len(d['limits'])}")
    print(f"  radar             {len(d['radar'])} clients")
    print(f"  clients           {len(d['clients'])} (stress + credit papers)")
    print(f"  meeting attendees {len(d['meeting']['attendees'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
