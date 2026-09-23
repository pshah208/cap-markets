"""Build the offline dashboard cache; --check validates sources and exact output."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from scenario_facts import CLIENTS, FACTS

HERE = Path(__file__).resolve().parent
OUTPUT = HERE.parent / "app" / "src" / "web" / "src" / "dashboard" / "snapshot.json"
AS_OF = FACTS["as_of"]
D = Decimal
DISCLAIMER = (
    "SYNTHETIC DEMO ONLY: issuer names are labels; all internal figures and evidence "
    "are invented, not real client relationships, credit positions or investment advice. "
    "Offline cached scope only; no API calls, live retrieval or external facts."
)
UNITS = (
    "Source monetary values are CAD millions (revenue converted from CAD thousands). "
    "USD fields are unavailable: no CAD/USD conversion rate is supplied. "
    "Percentages are percentage points, not fractions."
)
MATURITY_BASIS = (
    "Facility commitment_cad_m grouped by maturity calendar year, including letters "
    "of credit, uncommitted and derivative lines where present; not drawn exposure, "
    "issuer-wide debt or the proposed refinancing pipeline. Facility rows are undated "
    "and treated as the scenario snapshot, not historical observations."
)
# Cached, per-company illustrative evidence: client_id -> (work email id, policy id,
# policy is company-specific). Matching is by the email's client_id field, never by
# a company name appearing somewhere in the text. Companies absent from this table
# keep the honest "unavailable" evidence text.
EVIDENCE_BY_CLIENT = {
    "CLI-1001": ("EM-003", "CP-012", True),
    "CLI-1002": ("EM-024", "CP-001", False),
    "CLI-1007": ("EM-027", "CP-005", False),
}
CLIENT_NAMES = [name for _, name, *_ in CLIENTS]


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def number(value: Decimal, places: str = "0.0001") -> float:
    return float(value.quantize(D(places), rounding=ROUND_HALF_UP))


def total(rows: list[dict], field: str) -> Decimal:
    values = [D(row[field]) for row in rows]
    require(all(v.is_finite() and v >= 0 for v in values), f"Invalid {field}")
    return sum(values, D(0))


def read_table(name: str, key: str, dated: bool = True) -> list[dict]:
    with (HERE / "fabric-iq" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if dated:
        # Never sum multiple snapshots or silently substitute stale observations.
        rows = [row for row in rows if row["as_of_date"] == AS_OF]
    keys = [(row["client_id"], row[key]) for row in rows]
    require(len(keys) == len(set(keys)), f"Duplicate snapshot rows: {name}")
    return rows


def build_snapshot() -> dict:
    clients = read_table("clients", "client_id", False)
    require(
        {r["client_id"]: r["client_name"] for r in clients}
        == {c[0]: c[1] for c in CLIENTS} and len(clients) == 10,
        "Expected the ten scenario clients",
    )
    tables = {
        "exposures": read_table("exposures", "product_id"),
        "credit_facilities": read_table("credit_facilities", "facility_id", False),
        "revenue_by_product": read_table("revenue_by_product", "product_id"),
        "wallet_share": read_table("wallet_share", "product_id"),
        "limits_utilization": read_table("limits_utilization", "limit_id"),
    }
    work = json.loads((HERE / "work-iq" / "emails.json").read_text(encoding="utf-8"))
    foundry = json.loads((HERE / "foundry-iq" / "cm_policies.json").read_text(encoding="utf-8"))
    web = json.loads((HERE / "web-iq" / "web_iq_queries.json").read_text(encoding="utf-8"))
    require(web["offline_cache"] is False, "Review changed Web cache contract")
    companies = []
    for client in sorted(clients, key=lambda row: row["client_id"]):
        cid = client["client_id"]
        scoped = {name: [r for r in rows if r["client_id"] == cid] for name, rows in tables.items()}
        require(all(scoped.values()), f"Missing current snapshot data for {cid}")
        exposures, facilities, revenues, wallets, limits = (
            scoped[name] for name in tables
        )
        require(all(r["fiscal_year"] == FACTS["fiscal_year"] for r in revenues), "Mixed fiscal years")
        single = [r for r in limits if r["limit_type"] == "Single-name credit limit"]
        require(len(single) == 1, f"Expected one single-name limit for {cid}")
        limit = single[0]
        exposure = total(exposures, "current_exposure_cad_m")
        commitment = total(facilities, "commitment_cad_m")
        revenue = total(revenues, "fy26_ytd_revenue_cad_k") / 1000
        wallet_revenue = total(wallets, "bmo_revenue_cad_k") / 1000
        street = total(wallets, "estimated_street_wallet_cad_k") / 1000
        ceiling = D(limit["limit_cad_m"])
        utilized = D(limit["utilised_cad_m"])
        require(ceiling > 0 and utilized >= 0, f"Invalid limit for {cid}")
        utilization = number(utilized / ceiling * 100, "0.1")
        require(abs(D(str(utilization)) - D(limit["utilisation_pct"])) <= D("0.1"),
                f"Limit percentage does not reconcile for {cid}")
        maturity: dict[str, Decimal] = defaultdict(Decimal)
        for row in facilities:
            require(row["status"] == "Active", f"Review inactive facility {row['facility_id']}")
            year = str(date.fromisoformat(row["maturity_date"]).year)
            maturity[year] += D(row["commitment_cad_m"])
        require(sum(maturity.values()) == commitment, f"Maturity does not reconcile for {cid}")
        issues = []
        if utilized != exposure:
            issues.append(
                f"Exposure rows total CAD {exposure}m, but the single-name limit reports "
                f"CAD {utilized}m utilised. The source mismatch is unresolved; utilization "
                "uses the limit row, not exposure divided by limit."
            )
        if wallet_revenue != revenue:
            issues.append(
                f"Wallet-table revenue CAD {wallet_revenue}m differs from FY26 YTD "
                f"revenue CAD {revenue}m. Wallet share uses only wallet-table numerator "
                "and estimated street denominator; these sources are not reconciled."
            )
        ranked_wallet = sorted(
            wallets, key=lambda r: (-D(r["gap_to_25pct_target_cad_k"]), r["product_id"])
        )
        candidate = ranked_wallet[0]
        gap = D(candidate["gap_to_25pct_target_cad_k"]) / 1000
        opportunity = (
            f"Review {candidate['product_name']}: largest recorded gap to the 25% wallet "
            f"target is CAD {gap}m in wallet_share.csv. This is an analytical lead, "
            "not an approved opportunity or revenue forecast."
            if gap > 0 else "No positive gap to the 25% wallet target is recorded."
        )
        risk = (
            f"Single-name limit status {limit['status']}: {utilization}% utilised, "
            f"CAD {utilized}m of CAD {ceiling}m. Internal synthetic rating "
            f"{client['internal_risk_rating']}; trend {client['risk_trend']}; "
            f"watchlist flag {client['watchlist_flag']}. KYC refresh due "
            f"{client['kyc_refresh_due']} (relative to cached date, not today). "
            "Headroom is not approval for new commitments."
        )
        evidence = [
            {"iq": "Fabric IQ", "status": "cached synthetic",
             "text": "Local CSV snapshot only; no Fabric service query. " + UNITS},
            {"iq": "Work IQ", "status": "unavailable",
             "text": "No company-specific Work evidence selected for this cache."},
            {"iq": "Foundry IQ", "status": "unavailable",
             "text": "No company-specific Foundry evidence selected for this cache."},
            {"iq": "Web IQ", "status": "unavailable",
             "text": "web_iq_queries.json declares no offline cache. No news, ratings or external facts retrieved."},
        ]
        sources = ["data/fabric-iq/clients.csv"] + [
            f"data/fabric-iq/{name}.csv" for name in tables
        ] + ["data/scenario_facts.py", "data/web-iq/web_iq_queries.json"]
        if cid == FACTS["hero_client_id"]:
            hm = FACTS["hero_metrics"]
            for actual, expected in [
                (exposure, hm["total_exposure_m"]), (commitment, hm["total_committed_m"]),
                (total(facilities, "drawn_cad_m"), hm["total_drawn_m"]),
                (revenue * 1000, hm["fy26_ytd_revenue_k"]),
                (ceiling, hm["single_name_limit_m"]),
                (D(str(utilization)), hm["limit_utilisation_pct"]),
                (D(str(number(wallet_revenue / street * 100, "0.1"))), hm["wallet_share_pct"]),
            ]:
                require(actual == D(str(expected)), f"Hero scenario mismatch: {actual} != {expected}")
            opportunity = "Scenario proposals (not approved): " + "; ".join(
                f"{o['id']} {o['name']} (decision needed by {o['decision_needed_by']})"
                for o in FACTS["opportunities"].values()
            ) + ". Revolver pitch requires Credit pro-forma testing; hedging solicitation requires Control Room clearance."
            tension = FACTS["covenant_tension"]
            risk += (
                f" Scenario covenant {tension['covenant']}: {tension['actual']:.2f}x "
                f"against {tension['threshold']:.2f}x; {tension['headroom_turns']:.2f} turns "
                f"headroom. {FACTS['mnpi_tension']['id']}: {FACTS['mnpi_tension']['effect']}"
            )
        if cid in EVIDENCE_BY_CLIENT:
            email_id, policy_id, policy_is_company_specific = EVIDENCE_BY_CLIENT[cid]
            require(work["as_of"] == AS_OF, "Stale work-iq/emails.json")
            require(foundry["as_of"] == AS_OF, "Stale foundry-iq/cm_policies.json")
            email = next(d for d in work["emails"] if d["id"] == email_id)
            # Deterministic attribution: the record says which company it belongs to.
            require(email.get("client_id") == cid, f"Wrong company evidence {email_id}")
            policy = next(d for d in foundry["documents"] if d["id"] == policy_id)
            named = [n for n in CLIENT_NAMES if n in json.dumps(policy)]
            if policy_is_company_specific:
                require(named == [client["client_name"]],
                        f"Policy {policy_id} is not specific to {cid}")
                policy_card = (
                    f"Illustrative local source {policy_id}: {policy['title']}. "
                    "Not a live retrieval."
                )
            else:
                # A generic standard must never be presented as a company-specific document.
                require(not named, f"Policy {policy_id} names a portfolio company; not generic")
                policy_card = (
                    f"Illustrative local policy {policy_id}: {policy['title']}. Firm-wide "
                    "standard applicable to this situation, not a company-specific document. "
                    "Not a live retrieval."
                )
            evidence[1] = {
                "iq": evidence[1]["iq"], "status": "cached synthetic",
                "text": f"Illustrative local source {email_id}: {email['subject']}. Not a live retrieval.",
            }
            evidence[2] = {"iq": evidence[2]["iq"], "status": "cached synthetic", "text": policy_card}
            sources.append(f"data/work-iq/emails.json#{email_id}")
            sources.append(f"data/foundry-iq/cm_policies.json#{policy_id}")
        companies.append({
            "id": cid, "name": client["client_name"], "sector": client["sector"],
            "asOf": AS_OF, "exposure": None, "commitment": None, "revenue": None,
            "limit": None, "maturity": [], "currency": "USD", "fxRate": None,
            "usdUnavailableReason": "CAD source values; no supported FX rate.",
            "revenuePeriod": f"{FACTS['fiscal_year']} YTD ({FACTS['fiscal_year_start']} to {AS_OF}); not full year",
            "walletPercent": number(wallet_revenue / street * 100, "0.1") if street else None,
            "utilizationPercent": utilization,
            "exposureCad": number(exposure), "commitmentCad": number(commitment),
            "revenueCad": number(revenue), "limitCad": number(ceiling),
            "limitUtilizedCad": number(utilized),
            "walletRevenueCad": number(wallet_revenue), "streetWalletCad": number(street),
            "maturityCad": [{"year": year, "amount": number(amount)} for year, amount in sorted(maturity.items())],
            "maturityBasis": MATURITY_BASIS,
            "commitmentBasis": "Sum of facility commitment_cad_m, including uncommitted and derivative risk lines; not all legally committed lending.",
            "evidence": evidence, "opportunity": opportunity, "risk": risk,
            "dataQuality": issues, "sources": sources,
        })
    return {"snapshotAsOf": AS_OF, "units": UNITS, "disclaimer": DISCLAIMER, "companies": companies}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only: validate truth and fail on a stale/missing cache")
    args = parser.parse_args()
    try:
        snapshot = build_snapshot()
        content = (json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        if args.check:
            require(OUTPUT.exists() and OUTPUT.read_bytes() == content,
                    "Missing/stale snapshot.json; run python data\\generate_dashboard_snapshot.py")
            print("PASS: 10 companies; source aggregation, scenario reconciliation, maturity, units and deterministic cache verified.")
        else:
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_bytes(content)
            print(f"Generated {OUTPUT}")
        return 0
    except (ValueError, KeyError, StopIteration, OSError) as error:
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
