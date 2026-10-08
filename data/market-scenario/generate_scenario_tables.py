"""Build the governed scenario tables for Fabric IQ from data/market-scenario/.

    scenario_sensitivity.csv  one row per client: factor betas + business model
    market_scenarios.csv      one row per (scenario, factor): the preset library

beta_oil is solved, not authored: for every client it is set so the "oil-shock"
preset reproduces that client's agreed EBITDA impact in scenario.json exactly. That
keeps the Scenarios tab, the Dashboard triage and the Foundry house view (CP-015)
in agreement by construction.

    python generate_scenario_tables.py           # write the CSVs
    python generate_scenario_tables.py --check   # fail if stale
"""

from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

HERE = Path(__file__).parent
FABRIC = HERE.parent / "fabric-iq"


def build() -> tuple[list[dict], list[dict]]:
    sens = json.loads((HERE / "sensitivities.json").read_text(encoding="utf-8"))
    scn = json.loads((HERE / "scenario.json").read_text(encoding="utf-8"))
    with (FABRIC / "clients.csv").open(encoding="utf-8-sig", newline="") as stream:
        clients = {r["client_id"]: r for r in csv.DictReader(stream)}
    preset = next(p for p in sens["presets"] if p["id"] == "oil-shock")["factors"]

    rows = []
    for cid, s in sens["clients"].items():
        target = float(scn["clients"][cid]["ebitda_shock_pct"])
        rest = (s["beta_gas"] * preset["gas_pct"] + s["beta_fx"] * preset["usdcad_pct"]
                + s["beta_demand"] * preset["demand_pct"] + s.get("beta_tariff", 0.0) * preset.get("tariff_pct", 0.0))
        beta_oil = (target - rest) / preset["oil_pct"]
        rows.append({
            "client_id": cid, "client_name": clients[cid]["client_name"],
            "beta_oil": round(beta_oil, 6), "beta_gas": s["beta_gas"], "beta_fx": s["beta_fx"],
            "beta_demand": s["beta_demand"], "beta_tariff": s.get("beta_tariff", 0.0),
            "floating_debt_share": s["floating_debt_share"],
            "business_model": s["model"], "oil_shock_ebitda_pct": target, "as_of_date": scn["as_of"],
        })

    lib = []
    for p in sens["presets"]:
        for fid, val in p["factors"].items():
            lib.append({"scenario_id": p["id"], "scenario_name": p["name"], "factor": fid,
                        "value": val, "note": p["note"], "as_of_date": scn["as_of"]})
    return rows, lib


def to_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    sens_rows, lib_rows = build()
    out = {FABRIC / "scenario_sensitivity.csv": to_csv(sens_rows),
           FABRIC / "market_scenarios.csv": to_csv(lib_rows)}
    if args.check:
        stale = [p.name for p, c in out.items() if not p.exists() or p.read_text(encoding="utf-8") != c]
        print("FAIL stale: " + ", ".join(stale) if stale else "OK   scenario tables match the source")
        return 1 if stale else 0
    for p, c in out.items():
        p.write_text(c, encoding="utf-8", newline="")
        print(f"wrote {p.name}")
    for r in sens_rows:
        print(f"  {r['client_id']} beta_oil={r['beta_oil']:+.4f}  oil-shock EBITDA {r['oil_shock_ebitda_pct']:+.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
