"""Generate `app/market_data.py` for the coverage workflow (overview, triage, outreach,
client workspace, call assist, wrap-up).

Like generate_skill_data.py: the BFF image copies only `src/bff`, so the scenario and the
extra per-client facts it needs are transcribed mechanically from the dataset.

    python generate_market_data.py            # rewrite app/market_data.py
    python generate_market_data.py --check    # fail if stale
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
DATA = HERE.parents[2] / "data"
FABRIC = DATA / "fabric-iq"
OUT = HERE / "app" / "market_data.py"

sys.path.insert(0, str(DATA))
from scenario_facts import PEOPLE  # noqa: E402


def rows(name: str) -> list[dict[str, str]]:
    with (FABRIC / name).open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def f(v: str | None) -> float:
    try:
        return float(v) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def build() -> dict:
    scenario = json.loads((DATA / "market-scenario" / "scenario.json").read_text(encoding="utf-8"))
    scenario.pop("$schema_note", None)

    clients = rows("clients.csv")
    ids = [c["client_id"] for c in clients]
    exposures, revenue, trades = rows("exposures.csv"), rows("revenue_by_product.csv"), rows("trades.csv")
    limits, wallet = rows("limits_utilization.csv"), rows("wallet_share.csv")
    emails = json.loads((DATA / "work-iq" / "emails.json").read_text(encoding="utf-8"))["emails"]
    meetings_dir = DATA / "work-iq" / "meetings"

    extra: dict[str, dict] = defaultdict(lambda: {"exposure_by_product": [], "trades": [], "engagement": []})
    for e in exposures:
        extra[e["client_id"]]["exposure_by_product"].append(
            {"product": e["product_name"], "business_line": e["business_line"],
             "type": e["exposure_type"], "current": f(e["current_exposure_cad_m"])})
    for cid in ids:
        rev = [r for r in revenue if r["client_id"] == cid]
        extra[cid]["revenue_ytd_m"] = round(sum(f(r["fy26_ytd_revenue_cad_k"]) for r in rev) / 1000, 3)
        extra[cid]["revenue_markets_ytd_m"] = round(sum(
            f(r["fy26_ytd_revenue_cad_k"]) for r in rev
            if r["business_line"] == "Global Markets") / 1000, 3)
        extra[cid]["revenue_prior_ytd_m"] = round(sum(f(r["fy25_same_period_revenue_cad_k"]) for r in rev) / 1000, 3)
        w = [r for r in wallet if r["client_id"] == cid]
        street = sum(f(r["estimated_street_wallet_cad_k"]) for r in w)
        ours = sum(f(r["bank_revenue_cad_k"]) for r in w)
        extra[cid]["wallet_share_pct"] = round(ours / street * 100, 1) if street else None
        extra[cid]["limit_reviews"] = [
            {"type": r["limit_type"], "next_review": r["next_review_date"]}
            for r in limits if r["client_id"] == cid]
        tr = sorted((t for t in trades if t["client_id"] == cid), key=lambda t: t["trade_date"], reverse=True)
        extra[cid]["trades"] = [
            {"date": t["trade_date"], "product": t["product_name"], "description": t["description"],
             "notional_m": f(t["notional_cad_m"]), "status": t["status"]} for t in tr[:6]]

    # Engagement history: Work IQ emails (subjects only - bodies stay in Work IQ) and
    # meeting records, plus the recorded last coverage meeting.
    for em in emails:
        cid = em.get("client_id", "CLI-1001")
        extra[cid]["engagement"].append(
            {"date": em["sentDateTime"][:10], "kind": "email", "title": em["subject"], "source": "Work IQ"})
    for path in sorted(meetings_dir.glob("*.md")):
        title = path.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip()
        extra["CLI-1001"]["engagement"].append(
            {"date": path.name[:10], "kind": "meeting", "title": title, "source": "Work IQ"})
    for c in clients:
        extra[c["client_id"]]["engagement"].append(
            {"date": c["last_meeting_date"], "kind": "meeting", "title": "Coverage meeting (last recorded)", "source": "Fabric IQ"})
    for cid in ids:
        extra[cid]["engagement"] = sorted(
            (e for e in extra[cid]["engagement"] if e["date"] <= scenario["as_of"]),
            key=lambda x: x["date"], reverse=True)[:8]

    people = {p["alias"]: {"name": p["displayName"], "title": p["title"],
                           "department": p["department"], "wall_status": p["wall_status"]} for p in PEOPLE}
    owners = {c["client_id"]: {"owner": c["relationship_owner_alias"], "banker": c["coverage_banker_alias"]}
              for c in clients}

    return {"scenario": scenario, "extra": {cid: extra[cid] for cid in ids},
            "people": people, "owners": owners, "sensitivity": _sensitivity()}


def _sensitivity() -> dict:
    """Scenario library + valuation assumptions + the governed per-client betas
    (scenario_sensitivity.csv - the same table Fabric IQ serves)."""
    sens = json.loads((DATA / "market-scenario" / "sensitivities.json").read_text(encoding="utf-8"))
    betas = {r["client_id"]: {k: (float(v) if k.startswith(("beta_", "floating", "oil_shock")) else v)
                               for k, v in r.items()}
             for r in rows("scenario_sensitivity.csv")}
    facilities = rows("credit_facilities.csv")
    undrawn = {}
    for f_ in facilities:
        if f_.get("revolving_flag", "").upper() in ("Y", "YES", "TRUE"):
            undrawn[f_["client_id"]] = undrawn.get(f_["client_id"], 0.0) + f(f_["undrawn_cad_m"])
    return {"factors": sens["factors"], "presets": sens["presets"], "valuation": sens["valuation"],
            "world_severity": {k: v for k, v in sens.get("world_severity", {}).items() if not k.startswith("$")},
            "betas": betas, "revolver_undrawn_m": undrawn}


TEMPLATE = '''"""Coverage-workflow data (market scenario + per-client extras). GENERATED - do not edit.

Produced by `generate_market_data.py` from `data/market-scenario/scenario.json`,
`data/fabric-iq/*.csv` and `data/work-iq/`. SYNTHETIC DEMO DATA.

Generated {stamp}.
"""

from __future__ import annotations

from typing import Any

MARKET_DATA: dict[str, Any] = {payload}
'''


def render() -> str:
    payload = json.dumps(build(), indent=4, ensure_ascii=False)
    payload = (payload.replace(": true", ": True").replace(": false", ": False")
                      .replace(": null", ": None"))
    return TEMPLATE.format(stamp=datetime.now(UTC).strftime("%Y-%m-%d"), payload=payload)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    new = render()
    if args.check:
        strip = lambda s: "\n".join(l for l in s.splitlines() if not l.startswith("Generated "))  # noqa: E731
        if not OUT.exists() or strip(OUT.read_text(encoding="utf-8")) != strip(new):
            print(f"FAIL {OUT.name} is stale - re-run generate_market_data.py")
            return 1
        print(f"OK   {OUT.name} matches the dataset")
        return 0
    OUT.write_text(new, encoding="utf-8")
    d = build()
    print(f"wrote {OUT.relative_to(HERE)}  ({len(new):,} chars) - "
          f"{len(d['extra'])} clients, scenario {d['scenario']['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
