"""Deterministic generator for the Fabric IQ layer of the Capital Markets
Client Intelligence demo.

Produces ten CSVs under this directory. Every hero-client figure is pinned to
``scenario_facts.FACTS`` so the numbers quoted in emails, meeting minutes and
policy documents reconcile exactly with what the agent reads out of Fabric.

    python generate_fabric_data.py
    python generate_fabric_data.py --check     # reconcile and verify CSVs without writing

``build_tables()`` returns fresh, deterministic tables in memory. Both CLI modes
reconcile against scenario_facts before writing or checking existing CSV bytes.

SYNTHETIC DEMO DATA - see scenario_facts.py for the full disclaimer.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scenario_facts import (  # noqa: E402
    CLIENTS,
    DISCLAIMER,
    FACTS,
    PEOPLE,
    PRODUCTS,
)

HERE = Path(__file__).parent
AS_OF = date.fromisoformat(FACTS["as_of"])
HERO = FACTS["hero_client_id"]
HM = FACTS["hero_metrics"]

rng = random.Random(FACTS["random_seed"])


def _csv_bytes(header: list[str], rows: list[list]) -> bytes:
    with io.StringIO(newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)
        return fh.getvalue().encode("utf-8")


def _write(name: str, header: list[str], rows: list[list]) -> None:
    (HERE / name).write_bytes(_csv_bytes(header, rows))
    print(f"  {name:<32} {len(rows):>4} rows")


def _check(name: str, header: list[str], rows: list[list]) -> bool:
    try:
        actual = (HERE / name).read_bytes()
    except OSError as exc:
        print(f"  FAIL {name}: {exc}")
        return False
    if actual != _csv_bytes(header, rows):
        print(f"  FAIL {name}: CSV differs from generated data")
        return False
    print(f"  OK  {name:<32} {len(rows):>4} rows")
    return True


def _r(lo: float, hi: float, dp: int = 1) -> float:
    return round(rng.uniform(lo, hi), dp)


# ---------------------------------------------------------------------------
# 1. clients.csv
# ---------------------------------------------------------------------------

RATINGS = {
    "CLI-1001": ("S&P BBB- / DBRS BBB (low)", "IG-6", "improving", "N"),
    "CLI-1002": ("S&P BBB / DBRS BBB",        "IG-5", "stable",    "N"),
    "CLI-1003": ("S&P BB+ / DBRS BB (high)",  "IG-8", "improving", "N"),
    "CLI-1004": ("S&P BB / DBRS BB",          "IG-9", "stable",    "N"),
    "CLI-1005": ("S&P BBB / DBRS BBB",        "IG-5", "stable",    "N"),
    "CLI-1006": ("S&P BBB- / DBRS BBB (low)", "IG-6", "stable",    "N"),
    "CLI-1007": ("S&P BB- / DBRS BB (low)",   "IG-10", "deteriorating", "Y"),
    "CLI-1008": ("S&P BB- / not rated",       "IG-10", "deteriorating", "Y"),
    "CLI-1009": ("not rated",                 "IG-7", "stable",    "N"),
    "CLI-1010": ("S&P BB / DBRS BB (high)",   "IG-8", "stable",    "N"),
}

COVERAGE = {
    "CLI-1001": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1002": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1003": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1004": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1005": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1006": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1007": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1008": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1009": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
    "CLI-1010": ("sydney.mattos", "sasha.ouellet", "robin.kline", "quinn.campbell", "vance.deleon"),
}

# Non-hero portfolio scale (committed CAD m, single-name limit CAD m).
PORTFOLIO_SCALE = {
    "CLI-1002": (520.0, 600.0),
    "CLI-1003": (310.0, 375.0),
    "CLI-1004": (185.0, 250.0),
    "CLI-1005": (240.0, 300.0),
    "CLI-1006": (275.0, 350.0),
    "CLI-1007": (160.0, 200.0),
    "CLI-1008": (120.0, 150.0),
    "CLI-1009": (145.0, 200.0),
    "CLI-1010": (330.0, 400.0),
}


def gen_clients() -> list[list]:
    rows = []
    for cid, name, ticker, sector, sub, hq, tier, since in CLIENTS:
        pub, internal, trend, watch = RATINGS[cid]
        if cid == HERO:
            rating, prior = HM["internal_risk_rating"], HM["internal_risk_rating_prior"]
            trend, watch = HM["risk_trend"], "Y" if HM["watchlist"] else "N"
            products = HM["products_held"]
            last_meet = HM["last_meeting_date"]
            kyc = HM["kyc_refresh_due"]
        else:
            rating = prior = internal
            products = rng.randint(2, 6)
            last_meet = (AS_OF - timedelta(days=rng.randint(20, 210))).isoformat()
            kyc = (AS_OF + timedelta(days=rng.randint(40, 640))).isoformat()
        rows.append([
            cid, name, ticker, sector, sub, hq, tier, since,
            AS_OF.year - since, pub, rating, prior, trend, watch,
            products, len(PRODUCTS), last_meet, kyc,
            COVERAGE[cid][0], COVERAGE[cid][1],
        ])
    return rows


# ---------------------------------------------------------------------------
# 2. coverage_team.csv
# ---------------------------------------------------------------------------

COVERAGE_ROLE = {
    "sydney.mattos":  ("Relationship Owner", "Primary", "Approves the account plan and owns the client P&L"),
    "sasha.ouellet":  ("Coverage Banker", "Primary", "Day-to-day coverage, origination and pitch execution"),
    "robin.kline":    ("Research Analyst", "Public side", "Publishing analyst - subject to information barrier"),
    "quinn.campbell": ("Corporate Sales", "Secondary", "Commodity and FX derivative coverage"),
    "vance.deleon":   ("Credit Risk", "Control function", "Limit setting, covenant monitoring and annual review"),
}


def gen_coverage_team() -> list[list]:
    rows = []
    for cid, name, *_ in CLIENTS:
        for p in PEOPLE:
            cov_role, kind, note = COVERAGE_ROLE[p["alias"]]
            if cid == HERO:
                interactions = {"sydney.mattos": 14, "sasha.ouellet": 31,
                                "robin.kline": 6, "quinn.campbell": 11,
                                "vance.deleon": 9}[p["alias"]]
                last = {"sydney.mattos": "2026-10-02", "sasha.ouellet": "2026-10-03",
                        "robin.kline": "2026-09-22", "quinn.campbell": "2026-09-30",
                        "vance.deleon": "2026-10-01"}[p["alias"]]
                wall = p["wall_status"]
            else:
                interactions = rng.randint(0, 12)
                last = (AS_OF - timedelta(days=rng.randint(5, 260))).isoformat()
                wall = "public_side"
            rows.append([
                cid, name, p["alias"], p["displayName"], p["title"], p["department"],
                cov_role, kind, interactions, last, wall, note,
            ])
    return rows


# ---------------------------------------------------------------------------
# 3. credit_facilities.csv
# ---------------------------------------------------------------------------

HERO_FACILITIES = [
    # facility_id, type, product, commitment, drawn, maturity, pricing, bank_role, status
    ("FAC-10011", "Revolving Credit Facility", "PRD-01", 165.0, 96.0,  "2029-06-30", "SOFR + 162.5 bps", "Co-Lead Arranger / Joint Bookrunner", "Active"),
    ("FAC-10012", "Term Loan B (Chauvin bridge take-out)", "PRD-02", 140.0, 140.0, "2030-03-31", "SOFR + 200.0 bps", "Joint Lead Arranger", "Active"),
    ("FAC-10013", "Letter of Credit Facility", "PRD-03", 60.0, 32.4, "2027-12-31", "Fee 145.0 bps", "Issuing Bank", "Active"),
    ("FAC-10014", "Uncommitted Bilateral Operating Line", "PRD-01", 40.0, 0.0, "2027-06-30", "Prime + 75.0 bps", "Sole Lender", "Active"),
    ("FAC-10015", "Derivative Settlement / Pre-Settlement Line", "PRD-09", 60.0, 20.0, "2028-06-30", "n/a - risk line", "Counterparty", "Active"),
]
# 165 + 140 + 60 + 40 + 60 = 465.0 committed   (= FACTS hero_metrics.total_committed_m)
# 96 + 140 + 32.4 + 0 + 20 = 288.4 drawn       (= FACTS hero_metrics.total_drawn_m)


def gen_credit_facilities() -> list[list]:
    rows = []
    for fid, ftype, prod, commit, drawn, mat, pricing, role, status in HERO_FACILITIES:
        rows.append([
            HERO, FACTS["hero_client_name"], fid, ftype, prod, commit, drawn,
            round(commit - drawn, 1), round(drawn / commit * 100, 1) if commit else 0.0,
            mat, pricing, role, status,
            "Y" if ftype.startswith("Revolving") else "N",
        ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        total, _limit = PORTFOLIO_SCALE[cid]
        splits = [0.55, 0.30, 0.15]
        types = [
            ("Revolving Credit Facility", "PRD-01", "Participant"),
            ("Term Loan", "PRD-02", "Participant"),
            ("Letter of Credit Facility", "PRD-03", "Issuing Bank"),
        ]
        for i, (ftype, prod, role) in enumerate(types):
            commit = round(total * splits[i], 1)
            drawn = round(commit * _r(0.30, 0.92, 3), 1)
            rows.append([
                cid, name, f"FAC-{cid[-4:]}{i + 1}", ftype, prod, commit, drawn,
                round(commit - drawn, 1), round(drawn / commit * 100, 1),
                (AS_OF + timedelta(days=rng.randint(300, 1700))).isoformat(),
                f"SOFR + {rng.choice([137.5, 150.0, 175.0, 212.5, 250.0])} bps",
                role, "Active", "Y" if i == 0 else "N",
            ])
    return rows


# ---------------------------------------------------------------------------
# 4. exposures.csv
# ---------------------------------------------------------------------------

HERO_EXPOSURES = [
    # product, exposure_type, current, peak_12m, tenor_note
    ("PRD-01", "Funded - drawn revolver",              96.0,  118.0, "Committed to 2029-06-30"),
    ("PRD-02", "Funded - term loan",                  140.0,  140.0, "Committed to 2030-03-31"),
    ("PRD-03", "Contingent - letters of credit",       32.4,   38.1, "Rolling 364-day"),
    ("PRD-09", "Derivative - commodity MTM + PSE",     41.2,   47.8, "WTI-WCS differential, 18m"),
    ("PRD-07", "Derivative - FX forward MTM + PSE",    18.6,   22.9, "CAD/USD strip, 12m"),
    ("PRD-08", "Derivative - interest rate swap MTM",   9.4,   14.2, "SOFR fixed-pay, 5y"),
    ("PRD-10", "Intraday settlement / daylight",        4.1,    6.8, "Uncommitted"),
]
# Funded + contingent + derivative current = 96 + 140 + 32.4 + 41.2 + 18.6 + 9.4 + 4.1 = 341.7


def gen_exposures() -> list[list]:
    prod_name = {p[0]: p[1] for p in PRODUCTS}
    prod_line = {p[0]: p[2] for p in PRODUCTS}
    rows = []
    for prod, etype, cur, peak, note in HERO_EXPOSURES:
        rows.append([
            HERO, FACTS["hero_client_name"], prod, prod_name[prod], prod_line[prod],
            etype, cur, peak, note, FACTS["as_of"],
        ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        total, _ = PORTFOLIO_SCALE[cid]
        for prod, share in (("PRD-01", 0.34), ("PRD-02", 0.28), ("PRD-03", 0.09),
                            ("PRD-07", 0.06), ("PRD-08", 0.04)):
            cur = round(total * share * _r(0.55, 1.0, 3), 1)
            rows.append([
                cid, name, prod, prod_name[prod], prod_line[prod],
                "Funded" if prod in ("PRD-01", "PRD-02") else
                "Contingent" if prod == "PRD-03" else "Derivative - MTM + PSE",
                cur, round(cur * _r(1.02, 1.30, 3), 1), "", FACTS["as_of"],
            ])
    return rows


# ---------------------------------------------------------------------------
# 5. limits_utilization.csv
# ---------------------------------------------------------------------------

def _longest_tenor_years() -> float:
    """Remaining years to the latest-maturing hero facility.

    Derived rather than hardcoded. This row previously carried a literal 5.6,
    which reconciled to nothing: the longest facility (FAC-10012, 2030-03-31) is
    3.6 years out from the 2026-10-05 as-at date. An audience member who asked
    the agent for the tenor position and then for the facility maturities would
    have got two numbers that could not both be true - and "every figure
    reconciles" is the claim this whole dataset rests on.

    "Max remaining maturity" is stated explicitly in the row label because the
    alternative reading - tenor at origination - is also a real way banks set
    this limit, and the two give different answers. Being explicit means the
    agent can say which one it is reporting.
    """
    latest = max(date.fromisoformat(f[5]) for f in HERO_FACILITIES)
    return round((latest - AS_OF).days / 365.25, 1)


def gen_limits() -> list[list]:
    rows = []
    # Hero: the single-name limit is the one the demo turns on.
    hero_limits = [
        ("LIM-1001-SN", "Single-name credit limit", HM["single_name_limit_m"], HM["total_exposure_m"], "Credit Committee", "2027-03-31", 85.0),
        ("LIM-1001-DV", "Derivative pre-settlement limit", 90.0, 69.2, "Credit Risk - Global Markets", "2027-03-31", 75.0),
        ("LIM-1001-TN", "Tenor limit - max remaining maturity", 7.0, _longest_tenor_years(), "Credit Committee", "2027-03-31", 85.0),
        ("LIM-1001-UW", "Underwriting commitment limit", 250.0, 0.0, "Underwriting Committee", "2026-12-31", 85.0),
    ]
    for lid, ltype, limit, used, owner, review, amber_at in hero_limits:
        util = round(used / limit * 100, 1)
        rows.append([
            HERO, FACTS["hero_client_name"], lid, ltype, limit, used,
            round(limit - used, 1), util,
            "Breach" if util >= 100 else "Amber" if util >= amber_at else "Green",
            owner, review, FACTS["as_of"],
        ])
    # Sector concentration limit - relevant to whether the upsize can be held.
    rows.append([
        "SECTOR-ENERGY", "Energy sector (all clients)", "LIM-SEC-ENE",
        "Sector concentration limit", 3_200.0, 2_744.0, 456.0, 85.8, "Amber",
        "Chief Risk Officer", "2026-12-31", FACTS["as_of"],
    ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        _total, limit = PORTFOLIO_SCALE[cid]
        used = round(limit * _r(0.42, 0.93, 3), 1)
        util = round(used / limit * 100, 1)
        rows.append([
            cid, name, f"LIM-{cid[-4:]}-SN", "Single-name credit limit", limit, used,
            round(limit - used, 1), util,
            "Breach" if util >= 100 else "Amber" if util >= 85 else "Green",
            "Credit Committee",
            (AS_OF + timedelta(days=rng.randint(60, 500))).isoformat(), FACTS["as_of"],
        ])
    return rows


# ---------------------------------------------------------------------------
# 6. revenue_by_product.csv
# ---------------------------------------------------------------------------

HERO_REVENUE = [
    # product, fy26_ytd_k, fy25_same_period_k, fy25_full_year_k
    ("PRD-01", 1_240.0, 1_180.0, 1_610.0),
    ("PRD-02", 1_015.0,   640.0,   905.0),
    ("PRD-03",   395.0,   360.0,   492.0),
    ("PRD-04", 2_680.0, 1_940.0, 2_610.0),
    ("PRD-06",   450.0,   750.0,   750.0),
    ("PRD-07",   905.0,   820.0, 1_140.0),
    ("PRD-08",   410.0,   365.0,   508.0),
    ("PRD-09", 1_010.0, 1_005.0, 1_425.0),
    ("PRD-10",   315.0,    80.0,   520.0),
]
# FY26 YTD total = 8,420.0 k   FY25 same period = 7,140.0 k   FY25 FY = 9,960.0 k


def gen_revenue() -> list[list]:
    prod_name = {p[0]: p[1] for p in PRODUCTS}
    prod_line = {p[0]: p[2] for p in PRODUCTS}
    rows = []
    for prod, ytd, prior_ytd, prior_fy in HERO_REVENUE:
        yoy = round((ytd - prior_ytd) / prior_ytd * 100, 1) if prior_ytd else None
        rows.append([
            HERO, FACTS["hero_client_name"], prod, prod_name[prod], prod_line[prod],
            ytd, prior_ytd, prior_fy, yoy, FACTS["fiscal_year"], FACTS["as_of"],
        ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        total, _ = PORTFOLIO_SCALE[cid]
        base = total * _r(0.010, 0.022, 4) * 1000
        for prod, share in (("PRD-01", 0.22), ("PRD-02", 0.16), ("PRD-03", 0.06),
                            ("PRD-04", 0.24), ("PRD-07", 0.12), ("PRD-09", 0.11),
                            ("PRD-10", 0.09)):
            ytd = round(base * share, 1)
            prior_ytd = round(ytd * _r(0.72, 1.28, 3), 1)
            rows.append([
                cid, name, prod, prod_name[prod], prod_line[prod], ytd, prior_ytd,
                round(prior_ytd * _r(1.28, 1.42, 3), 1),
                round((ytd - prior_ytd) / prior_ytd * 100, 1),
                FACTS["fiscal_year"], FACTS["as_of"],
            ])
    return rows


# ---------------------------------------------------------------------------
# 7. wallet_share.csv
# ---------------------------------------------------------------------------

HERO_WALLET = [
    # product, bank_k, street_wallet_k, rank, lead_competitor
    ("PRD-01", 1_240.0,  4_900.0, 2, "Competitor A"),
    ("PRD-02", 1_015.0,  3_600.0, 2, "Competitor B"),
    ("PRD-03",   395.0,  1_450.0, 3, "Competitor A"),
    ("PRD-04", 2_680.0, 11_200.0, 2, "Competitor C"),
    ("PRD-05",     0.0,  2_800.0, 6, "Competitor C"),
    ("PRD-06",   450.0,  4_500.0, 4, "Competitor D"),
    ("PRD-07",   905.0,  3_900.0, 2, "Competitor B"),
    ("PRD-08",   410.0,  2_050.0, 3, "Competitor B"),
    ("PRD-09", 1_010.0,  3_100.0, 1, "Competitor A"),
    ("PRD-10",   315.0,  1_450.0, 3, "Competitor E"),
    ("PRD-11",     0.0,    400.0, 5, "Competitor E"),
]
# street wallet total = 39,350.0 k ; the Bank = 8,420.0 k -> 21.4%


def gen_wallet_share() -> list[list]:
    prod_name = {p[0]: p[1] for p in PRODUCTS}
    rows = []
    for prod, bank, street, rank, comp in HERO_WALLET:
        share = round(bank / street * 100, 1) if street else 0.0
        rows.append([
            HERO, FACTS["hero_client_name"], prod, prod_name[prod], bank, street,
            share, rank, comp, "Y" if bank == 0 else "N",
            round(street * 0.25 - bank, 1),  # whitespace to a 25% target share
            FACTS["as_of"],
        ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        total, _ = PORTFOLIO_SCALE[cid]
        for prod in ("PRD-01", "PRD-04", "PRD-07", "PRD-09"):
            bank = round(total * _r(0.002, 0.010, 4) * 1000, 1)
            street = round(bank * _r(3.2, 9.5, 2), 1)
            rows.append([
                cid, name, prod, prod_name[prod], bank, street,
                round(bank / street * 100, 1), rng.randint(1, 6),
                f"Competitor {rng.choice('ABCDE')}", "N",
                round(street * 0.25 - bank, 1), FACTS["as_of"],
            ])
    return rows


# ---------------------------------------------------------------------------
# 8. trades.csv  (blotter - last 12 months)
# ---------------------------------------------------------------------------

HERO_TRADES = [
    # trade_id, date, product, description, notional_m, revenue_k, desk, status
    ("TRD-88401", "2026-09-01", "PRD-04", "Senior unsecured notes - joint bookrunner", 400.0, 1_940.0, "DCM Syndicate", "Settled"),
    ("TRD-88377", "2026-08-19", "PRD-09", "WTI-WCS differential swap - 12m strip",      75.0,   312.0, "Commodities", "Live"),
    ("TRD-88355", "2026-08-06", "PRD-07", "CAD/USD forward - 6m",                       60.0,   148.0, "FX Corporate Sales", "Live"),
    ("TRD-88301", "2026-07-14", "PRD-08", "SOFR fixed-pay swap - 5y",                  100.0,   205.0, "Rates", "Live"),
    ("TRD-88244", "2026-04-28", "PRD-09", "WCS crude collar - 18m",                     55.0,   268.0, "Commodities", "Live"),
    ("TRD-88190", "2026-03-31", "PRD-02", "Chauvin bridge take-out term loan",         140.0,   740.0, "Loan Syndications", "Settled"),
    ("TRD-88121", "2026-02-17", "PRD-07", "CAD/USD forward - 12m",                      85.0,   205.0, "FX Corporate Sales", "Live"),
    ("TRD-88044", "2026-01-22", "PRD-09", "Propane basis swap - 9m",                    30.0,   142.0, "Commodities", "Matured"),
    ("TRD-87988", "2025-12-09", "PRD-06", "Chauvin acquisition - buy-side advisory",   630.0,   450.0, "M&A", "Settled"),
    ("TRD-87901", "2025-11-14", "PRD-01", "Revolver amend and extend - upfront fee",   165.0,   288.0, "Loan Syndications", "Settled"),
]


def gen_trades() -> list[list]:
    prod_name = {p[0]: p[1] for p in PRODUCTS}
    rows = []
    for tid, dt, prod, desc, notional, rev, desk, status in HERO_TRADES:
        rows.append([
            HERO, FACTS["hero_client_name"], tid, dt, prod, prod_name[prod],
            desc, notional, rev, desk, status,
            (date.fromisoformat(dt) + timedelta(days=rng.choice([180, 365, 545, 1825]))).isoformat()
            if status == "Live" else "",
        ])
    tno = 87000
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        for _ in range(rng.randint(3, 6)):
            tno += rng.randint(3, 40)
            prod = rng.choice(["PRD-01", "PRD-04", "PRD-07", "PRD-08", "PRD-09"])
            dt = AS_OF - timedelta(days=rng.randint(15, 350))
            notional = round(_r(15, 320, 1), 1)
            rows.append([
                cid, name, f"TRD-{tno}", dt.isoformat(), prod, prod_name[prod],
                f"{prod_name[prod]} - client transaction", notional,
                round(notional * _r(1.8, 6.5, 2), 1),
                rng.choice(["Commodities", "FX Corporate Sales", "Rates",
                            "DCM Syndicate", "Loan Syndications"]),
                rng.choice(["Live", "Settled", "Matured"]), "",
            ])
    return rows


# ---------------------------------------------------------------------------
# 9. covenants.csv
# ---------------------------------------------------------------------------

CT = FACTS["covenant_tension"]

HERO_COVENANTS = [
    # covenant, test, threshold, actual, prior, unit, frequency, source
    (CT["covenant"], "maximum", CT["threshold"], CT["actual"], CT["prior_quarter_actual"], "x", "Quarterly", "FAC-10011 / FAC-10012"),
    ("Senior Secured Net Debt to Adjusted EBITDA", "maximum", 3.50, 2.61, 2.44, "x", "Quarterly", "FAC-10011"),
    ("Interest Coverage (Adjusted EBITDA / Interest)", "minimum", 2.50, 4.12, 4.38, "x", "Quarterly", "FAC-10011 / FAC-10012"),
    ("Minimum Tangible Net Worth", "minimum", 1_150.0, 1_486.0, 1_402.0, "CAD m", "Quarterly", "FAC-10012"),
    ("Restricted Payments Basket Utilisation", "maximum", 100.0, 63.4, 58.1, "%", "Quarterly", "FAC-10012"),
    ("Asset Disposal Threshold (trailing 12m)", "maximum", 250.0, 41.0, 41.0, "CAD m", "Annual", "FAC-10011"),
]


def gen_covenants() -> list[list]:
    rows = []
    for cov, test, thr, act, prior, unit, freq, src in HERO_COVENANTS:
        if test == "maximum":
            headroom = round(thr - act, 2)
            util = round(act / thr * 100, 1)
        else:
            headroom = round(act - thr, 2)
            util = round(thr / act * 100, 1) if act else 0.0
        status = "Breach" if headroom < 0 else "Amber" if util >= 90 else "Green"
        rows.append([
            HERO, FACTS["hero_client_name"], cov, test, thr, act, prior, unit,
            headroom, util, status, freq, src, "2026-06-30", "2026-09-30",
        ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        for cov, test, thr, unit in (
            ("Total Net Debt to Adjusted EBITDA", "maximum", 4.00, "x"),
            ("Interest Coverage (Adjusted EBITDA / Interest)", "minimum", 2.50, "x"),
        ):
            if test == "maximum":
                act = round(thr * _r(0.62, 0.99, 3), 2)
                headroom, util = round(thr - act, 2), round(act / thr * 100, 1)
            else:
                act = round(thr * _r(1.02, 2.10, 3), 2)
                headroom, util = round(act - thr, 2), round(thr / act * 100, 1)
            rows.append([
                cid, name, cov, test, thr, act, act, unit, headroom, util,
                "Breach" if headroom < 0 else "Amber" if util >= 90 else "Green",
                "Quarterly", f"FAC-{cid[-4:]}1", "2026-06-30", "2026-09-30",
            ])
    return rows


# ---------------------------------------------------------------------------
# 10. risk_ratings.csv  (8-quarter trend)
# ---------------------------------------------------------------------------

HERO_RATING_TREND = [
    ("2024-10-31", "IG-8", "stable",        "N", 4.61, "Pre-Chauvin. Leverage elevated after the 2024 capital programme."),
    ("2025-01-31", "IG-8", "stable",        "N", 4.48, "No change. Infrastructure segment throughput improving."),
    ("2025-04-30", "IG-7", "improving",     "N", 4.22, "Upgrade on sustained take-or-pay contract coverage."),
    ("2025-07-31", "IG-7", "stable",        "N", 4.05, "Held. Marketing segment volatility noted."),
    ("2025-10-31", "IG-7", "stable",        "N", 3.88, "Held into the Chauvin announcement."),
    ("2026-01-31", "IG-7", "under review",  "N", 4.31, "Placed under review for the acquisition-funded leverage step-up."),
    ("2026-04-30", "IG-6", "improving",     "N", 3.94, "Upgrade. Contracted cash flow mix improved post-close."),
    ("2026-07-31", "IG-6", "improving",     "N", 4.18, "Held at IG-6. Leverage ticked up on full-quarter Chauvin debt service."),
]


def gen_risk_ratings() -> list[list]:
    rows = []
    for dt, rating, trend, watch, lev, note in HERO_RATING_TREND:
        rows.append([
            HERO, FACTS["hero_client_name"], dt, rating, trend, watch, lev,
            HM["public_ratings"], note,
        ])
    for cid, name, *_ in CLIENTS:
        if cid == HERO:
            continue
        pub, internal, trend, watch = RATINGS[cid]
        for dt in ("2025-10-31", "2026-01-31", "2026-04-30", "2026-07-31"):
            rows.append([
                cid, name, dt, internal, trend, watch,
                round(_r(1.8, 4.6, 2), 2), pub, "",
            ])
    return rows


# ---------------------------------------------------------------------------

GENERATORS = [
    ("clients.csv",
     ["client_id", "client_name", "ticker", "sector", "sub_sector", "hq_city",
      "coverage_tier", "relationship_since", "relationship_years", "public_ratings",
      "internal_risk_rating", "internal_risk_rating_prior", "risk_trend",
      "watchlist_flag", "products_held", "products_available", "last_meeting_date",
      "kyc_refresh_due", "relationship_owner_alias", "coverage_banker_alias"],
     gen_clients),

    ("coverage_team.csv",
     ["client_id", "client_name", "alias", "display_name", "job_title", "department",
      "coverage_role", "coverage_type", "interactions_90d", "last_interaction_date",
      "wall_status", "responsibility"],
     gen_coverage_team),

    ("credit_facilities.csv",
     ["client_id", "client_name", "facility_id", "facility_type", "product_id",
      "commitment_cad_m", "drawn_cad_m", "undrawn_cad_m", "utilisation_pct",
      "maturity_date", "pricing", "bank_role", "status", "revolving_flag"],
     gen_credit_facilities),

    ("exposures.csv",
     ["client_id", "client_name", "product_id", "product_name", "business_line",
      "exposure_type", "current_exposure_cad_m", "peak_12m_exposure_cad_m",
      "tenor_note", "as_of_date"],
     gen_exposures),

    ("limits_utilization.csv",
     ["client_id", "client_name", "limit_id", "limit_type", "limit_cad_m",
      "utilised_cad_m", "headroom_cad_m", "utilisation_pct", "status",
      "limit_owner", "next_review_date", "as_of_date"],
     gen_limits),

    ("revenue_by_product.csv",
     ["client_id", "client_name", "product_id", "product_name", "business_line",
      "fy26_ytd_revenue_cad_k", "fy25_same_period_revenue_cad_k",
      "fy25_full_year_revenue_cad_k", "yoy_change_pct", "fiscal_year", "as_of_date"],
     gen_revenue),

    ("wallet_share.csv",
     ["client_id", "client_name", "product_id", "product_name", "bank_revenue_cad_k",
      "estimated_street_wallet_cad_k", "bank_wallet_share_pct", "bank_rank",
      "lead_competitor", "whitespace_flag", "gap_to_25pct_target_cad_k", "as_of_date"],
     gen_wallet_share),

    ("trades.csv",
     ["client_id", "client_name", "trade_id", "trade_date", "product_id",
      "product_name", "description", "notional_cad_m", "revenue_cad_k", "desk",
      "status", "maturity_date"],
     gen_trades),

    ("covenants.csv",
     ["client_id", "client_name", "covenant", "test_type", "threshold", "actual",
      "prior_quarter_actual", "unit", "headroom", "utilisation_pct", "status",
      "test_frequency", "source_facility", "last_tested_date", "next_test_date"],
     gen_covenants),

    ("risk_ratings.csv",
     ["client_id", "client_name", "as_of_date", "internal_risk_rating", "trend",
      "watchlist_flag", "net_debt_to_ebitda", "public_ratings", "analyst_note"],
     gen_risk_ratings),
]


def build_tables() -> dict[str, tuple[list[str], list[list]]]:
    """Build all ten tables in memory, resetting the seed before each full build."""
    rng.seed(FACTS["random_seed"])
    tables = {}
    for name, header, fn in GENERATORS:
        tables[name] = (header.copy(), fn())
    return tables


def reconcile_tables(tables: dict[str, tuple[list[str], list[list]]]) -> bool:
    """Report whether the generated hero figures agree with scenario_facts."""
    print("\nReconciling hero figures against scenario_facts...")
    ok = True

    def chk(label: str, got: float, want: float, tol: float = 0.05) -> None:
        nonlocal ok
        good = abs(got - want) <= tol
        ok &= good
        print(f"  {'OK ' if good else 'FAIL'} {label:<42} got {got:>10,.1f}  want {want:>10,.1f}")

    hdr, rows = tables["credit_facilities.csv"]
    hero_fac = [r for r in rows if r[0] == HERO]
    chk("total committed (CAD m)", sum(r[5] for r in hero_fac), HM["total_committed_m"])
    chk("total drawn (CAD m)", sum(r[6] for r in hero_fac), HM["total_drawn_m"])

    hdr, rows = tables["exposures.csv"]
    chk("total exposure (CAD m)",
        sum(r[6] for r in rows if r[0] == HERO), HM["total_exposure_m"])

    hdr, rows = tables["revenue_by_product.csv"]
    hero_rev = [r for r in rows if r[0] == HERO]
    chk("FY26 YTD revenue (CAD k)", sum(r[5] for r in hero_rev), HM["fy26_ytd_revenue_k"])
    chk("FY25 same-period revenue (CAD k)",
        sum(r[6] for r in hero_rev), HM["fy25_same_period_revenue_k"])
    chk("FY25 full-year revenue (CAD k)",
        sum(r[7] for r in hero_rev), HM["fy25_full_year_revenue_k"])

    hdr, rows = tables["wallet_share.csv"]
    hero_wal = [r for r in rows if r[0] == HERO]
    street = sum(r[5] for r in hero_wal)
    bank = sum(r[4] for r in hero_wal)
    chk("estimated street wallet (CAD k)", street, HM["estimated_street_wallet_k"])
    chk("wallet share (%)", round(bank / street * 100, 1), HM["wallet_share_pct"])

    hdr, rows = tables["limits_utilization.csv"]
    sn = next(r for r in rows if r[2] == "LIM-1001-SN")
    chk("single-name limit utilisation (%)", sn[7], HM["limit_utilisation_pct"])

    hdr, rows = tables["covenants.csv"]
    lev = next(r for r in rows if r[0] == HERO and r[2] == CT["covenant"])
    chk("leverage covenant headroom (turns)", lev[8], CT["headroom_turns"], tol=0.005)

    print("\n" + ("All hero figures reconcile." if ok else "RECONCILIATION FAILED."))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="reconcile and verify existing CSV bytes without writing")
    args = ap.parse_args()

    print(f"Capital Markets Client Intelligence - Fabric IQ data")
    print(f"  as at {FACTS['as_of']} | hero {FACTS['hero_client_name']} ({FACTS['hero_ticker']})")
    print(f"  {DISCLAIMER}\n")

    tables = build_tables()
    if not reconcile_tables(tables):
        return 1

    if args.check:
        print("\nChecking existing CSVs...")
        ok = True
        for name, (header, rows) in tables.items():
            ok &= _check(name, header, rows)
        return 0 if ok else 1

    for name, (header, rows) in tables.items():
        _write(name, header, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
