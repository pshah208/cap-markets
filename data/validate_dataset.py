"""Cross-layer consistency check for the Capital Markets Client Intelligence demo.

The whole point of this dataset is that a number quoted in an email matches the
number in the Fabric table, which matches the threshold in the policy document,
which matches the figure in the meeting minutes. This script proves it.

    python validate_dataset.py
    python validate_dataset.py --verbose

Exit code 0 means every layer agrees. Non-zero means the layers have drifted and
the demo will contradict itself on stage.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from scenario_facts import CLIENTS, FACTS, PEOPLE  # noqa: E402

FABRIC = HERE / "fabric-iq"
FOUNDRY = HERE / "foundry-iq"
WORK = HERE / "work-iq"
WEB = HERE / "web-iq"

HERO = FACTS["hero_client_id"]
HM = FACTS["hero_metrics"]
CT = FACTS["covenant_tension"]

_failures: list[str] = []
_checks = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _checks
    _checks += 1
    if ok:
        print(f"  OK   {label}")
    else:
        print(f"  FAIL {label}" + (f"  -- {detail}" if detail else ""))
        _failures.append(label)


def load_csv(name: str) -> list[dict]:
    with (FABRIC / name).open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def all_text(*paths: Path) -> str:
    out = []
    for p in paths:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file():
                    out.append(f.read_text(encoding="utf-8"))
        elif p.is_file():
            out.append(p.read_text(encoding="utf-8"))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    print(f"Capital Markets Client Intelligence - cross-layer validation")
    print(f"  as at {FACTS['as_of']} | hero {FACTS['hero_client_name']} ({FACTS['hero_ticker']})\n")

    # ---------------------------------------------------------------- files
    print("Layer presence")
    expected = [
        FABRIC / "clients.csv", FABRIC / "coverage_team.csv",
        FABRIC / "credit_facilities.csv", FABRIC / "exposures.csv",
        FABRIC / "limits_utilization.csv", FABRIC / "revenue_by_product.csv",
        FABRIC / "wallet_share.csv", FABRIC / "trades.csv",
        FABRIC / "covenants.csv", FABRIC / "risk_ratings.csv",
        FOUNDRY / "cm_policies.json",
        WORK / "emails.json", WORK / "teams_messages.json", WORK / "user_mapping.json",
        WEB / "web_iq_queries.json", WEB / "README.md",
    ]
    for p in expected:
        check(f"{p.relative_to(HERE)}", p.exists())
    meetings = sorted((WORK / "meetings").glob("*.md"))
    files = sorted((WORK / "files").glob("*.md"))
    check(f"work-iq/meetings/ has 5 records (found {len(meetings)})", len(meetings) == 5)
    check(f"work-iq/files/ has 2 documents (found {len(files)})", len(files) == 2)

    # --------------------------------------------------------- fabric totals
    print("\nFabric IQ reconciles to scenario_facts")
    fac = [r for r in load_csv("credit_facilities.csv") if r["client_id"] == HERO]
    check("committed CAD 465.0m",
          abs(sum(float(r["commitment_cad_m"]) for r in fac) - HM["total_committed_m"]) < 0.05)
    check("drawn CAD 288.4m",
          abs(sum(float(r["drawn_cad_m"]) for r in fac) - HM["total_drawn_m"]) < 0.05)

    exp = [r for r in load_csv("exposures.csv") if r["client_id"] == HERO]
    check("exposure CAD 341.7m",
          abs(sum(float(r["current_exposure_cad_m"]) for r in exp) - HM["total_exposure_m"]) < 0.05)

    rev = [r for r in load_csv("revenue_by_product.csv") if r["client_id"] == HERO]
    check("FY26 YTD revenue CAD 8,420k",
          abs(sum(float(r["fy26_ytd_revenue_cad_k"]) for r in rev) - HM["fy26_ytd_revenue_k"]) < 0.5)
    prior = sum(float(r["fy25_same_period_revenue_cad_k"]) for r in rev)
    ytd = sum(float(r["fy26_ytd_revenue_cad_k"]) for r in rev)
    check("revenue YoY +17.9%",
          abs(round((ytd - prior) / prior * 100, 1) - HM["revenue_yoy_pct"]) < 0.05,
          f"got {round((ytd - prior) / prior * 100, 1)}")

    wal = [r for r in load_csv("wallet_share.csv") if r["client_id"] == HERO]
    street = sum(float(r["estimated_street_wallet_cad_k"]) for r in wal)
    bmo = sum(float(r["bmo_revenue_cad_k"]) for r in wal)
    check("wallet share 21.4%", abs(round(bmo / street * 100, 1) - HM["wallet_share_pct"]) < 0.05)
    check("BMO revenue in wallet table == revenue table",
          abs(bmo - ytd) < 0.5, f"wallet {bmo} vs revenue {ytd}")

    lim = load_csv("limits_utilization.csv")
    sn = next(r for r in lim if r["limit_id"] == "LIM-1001-SN")
    check("single-name utilisation 68.3% / GREEN",
          abs(float(sn["utilisation_pct"]) - HM["limit_utilisation_pct"]) < 0.05
          and sn["status"] == "Green")
    check("single-name utilised == total exposure",
          abs(float(sn["utilised_cad_m"]) - HM["total_exposure_m"]) < 0.05)
    sec = next(r for r in lim if r["limit_id"] == "LIM-SEC-ENE")
    check("energy sector 85.8% / AMBER",
          abs(float(sec["utilisation_pct"]) - 85.8) < 0.05 and sec["status"] == "Amber")
    pse = next(r for r in lim if r["limit_id"] == "LIM-1001-DV")
    check("PSE line CAD 90m / 69.2m utilised / AMBER",
          abs(float(pse["limit_cad_m"]) - 90.0) < 0.05
          and abs(float(pse["utilised_cad_m"]) - 69.2) < 0.05
          and pse["status"] == "Amber")

    cov = [r for r in load_csv("covenants.csv") if r["client_id"] == HERO]
    lev = next(r for r in cov if r["covenant"] == CT["covenant"])
    check("leverage 4.18x of 4.50x, 0.32 turns headroom",
          abs(float(lev["actual"]) - CT["actual"]) < 0.005
          and abs(float(lev["threshold"]) - CT["threshold"]) < 0.005
          and abs(float(lev["headroom"]) - CT["headroom_turns"]) < 0.005)
    check("leverage is the tightest covenant in the file",
          min(cov, key=lambda r: float(r["utilisation_pct"]) * -1)["covenant"] == CT["covenant"],
          "another covenant has higher utilisation")

    rr = [r for r in load_csv("risk_ratings.csv") if r["client_id"] == HERO]
    latest = max(rr, key=lambda r: r["as_of_date"])
    check("latest internal rating IG-6 improving",
          latest["internal_risk_rating"] == HM["internal_risk_rating"]
          and latest["trend"] == HM["risk_trend"])
    check("rating trend leverage matches covenant actual",
          abs(float(latest["net_debt_to_ebitda"]) - CT["actual"]) < 0.005)
    check("two quarters ago was IG-7",
          sorted(rr, key=lambda r: r["as_of_date"])[-3]["internal_risk_rating"]
          == HM["internal_risk_rating_2q_ago"])

    cl = load_csv("clients.csv")
    check(f"10 clients in the portfolio (found {len(cl)})", len(cl) == len(CLIENTS))
    hero_row = next(r for r in cl if r["client_id"] == HERO)
    check("hero KYC refresh due 2026-09-30", hero_row["kyc_refresh_due"] == HM["kyc_refresh_due"])
    check("hero coverage: 5 team members",
          len([r for r in load_csv("coverage_team.csv") if r["client_id"] == HERO]) == len(PEOPLE))

    # ------------------------------------------------------------ foundry iq
    print("\nFoundry IQ")
    pol = json.loads((FOUNDRY / "cm_policies.json").read_text(encoding="utf-8"))
    docs = pol["documents"]
    check(f"14 policy documents (found {len(docs)})", len(docs) == 14)
    check("ids are CP-001..CP-014 with no gaps",
          [d["id"] for d in docs] == [f"CP-{i:03d}" for i in range(1, 15)])
    check("every document has a category from the declared list",
          all(d["category"] in pol["categories"] for d in docs))
    check("every document has content over 1000 chars",
          all(len(d["content"]) > 1000 for d in docs),
          str([d["id"] for d in docs if len(d["content"]) <= 1000]))

    ptext = json.dumps(pol)
    check("CP-001 single-name ceiling for IG-5/IG-6 is CAD 500m",
          "IG-5 to IG-6 | CAD 500m" in ptext)
    check("CP-005 Tight band is below 0.35 turns", "0.35 turns" in ptext)
    check("CP-003 CAD 151m-250m band requires convened Credit Committee",
          "CAD 151m to CAD 250m" in ptext and "Credit Committee (convened)" in ptext)
    check("CP-006 states no grace period", "There is no grace period" in ptext)
    check("CP-012 account plan quotes the Fabric figures",
          all(s in ptext for s in ["CAD 465m", "CAD 288.4m", "CAD 341.7m",
                                   "68.3 per cent", "CAD 8.42m", "21.4 per cent"]))
    check("CP-012 quotes the covenant headroom", "0.32 turns" in ptext)
    check("CP-002 sector ceiling is CAD 3,200m", "Energy CAD 3,200m" in ptext)

    # --------------------------------------------------------------- work iq
    print("\nWork IQ")
    em = json.loads((WORK / "emails.json").read_text(encoding="utf-8"))
    tm = json.loads((WORK / "teams_messages.json").read_text(encoding="utf-8"))
    um = json.loads((WORK / "user_mapping.json").read_text(encoding="utf-8"))

    aliases = {p["alias"] for p in PEOPLE}
    portfolio_ids = {c[0] for c in CLIENTS}
    hero_emails = [e for e in em["emails"] if e.get("client_id") == HERO]
    check(f"30 emails (found {len(em['emails'])})", len(em["emails"]) == 30)
    check(f"22 of them are hero ({HERO}) emails (found {len(hero_emails)})",
          len(hero_emails) == 22)
    check("every email is attributed to a portfolio client_id",
          all(e.get("client_id") in portfolio_ids for e in em["emails"]),
          str(sorted(e["id"] for e in em["emails"]
                     if e.get("client_id") not in portfolio_ids)))
    check("cached dashboard evidence emails exist and are attributed",
          all(any(e["id"] == eid and e.get("client_id") == cid for e in em["emails"])
              for eid, cid in [("EM-003", "CLI-1001"), ("EM-024", "CLI-1002"),
                               ("EM-027", "CLI-1007")]))
    check("every email category is declared",
          all(e["category"] in em["categories"] for e in em["emails"]))
    check("every email sender is a mapped persona",
          all(e["from"] in aliases for e in em["emails"]))
    check("every email recipient is a mapped persona",
          all(all(r in aliases for r in e.get("to", []) + e.get("cc", []))
              for e in em["emails"]))
    check("all 5 categories are used",
          {e["category"] for e in em["emails"]} == set(em["categories"]))

    # Teams JSON must match the contract seed_work_iq.py expects: channels carry
    # "conversations" (not "threads") and each message body is "message".
    threads = [t for ch in tm["channels"] for t in ch["conversations"]]
    replies = [r for t in threads for r in t.get("replies", [])]
    check(f"4 Teams channels (found {len(tm['channels'])})", len(tm["channels"]) == 4)
    check(f"{len(threads)} conversations and {len(replies)} replies",
          len(threads) >= 12 and len(replies) >= 25)
    check("every Teams author is a mapped persona",
          all(t["from"] in aliases for t in threads)
          and all(r["from"] in aliases for r in replies))
    check("every conversation and reply has a message body",
          all(t.get("message") for t in threads) and all(r.get("message") for r in replies))
    check("team owner and members are mapped personas",
          set(tm["team"]["ownerAliases"]) <= aliases
          and set(tm["team"]["memberAliases"]) <= aliases)
    check("driver owns the team",
          tm["team"]["ownerAliases"] == [um["driver_alias"]])
    check("all 5 personas are on the team",
          set(tm["team"]["ownerAliases"]) | set(tm["team"]["memberAliases"]) == aliases)

    check("user_mapping has all 5 personas", set(um["mapping"]) == aliases)
    check("driver is Sydney Mattos", um["driver_alias"] == "sydney.mattos")
    scotia = {"LisaT", "MarioR", "MonicaT", "SEdemo", "KaiC", "AdilE", "AmberR",
              "BillieV", "CoraT", "CoreyG", "DaichiM", "DakotaS", "EkaS", "HadarC"}
    used = {v["upn"].split("@")[0] for v in um["mapping"].values()}
    check("no overlap with the Scotia mortgage demo accounts",
          not (used & scotia), str(used & scotia))
    check("display names match scenario_facts",
          all(um["mapping"][p["alias"]]["displayName"] == p["displayName"] for p in PEOPLE))
    check("job titles match scenario_facts",
          all(um["mapping"][p["alias"]]["jobTitle"] == p["title"] for p in PEOPLE))
    check("wall status matches scenario_facts",
          all(um["mapping"][p["alias"]]["wall_status"] == p["wall_status"] for p in PEOPLE))

    # ------------------------------------------------- cross-layer agreement
    print("\nCross-layer figure agreement")
    corpus = json.dumps(em) + json.dumps(tm) + all_text(WORK / "meetings", WORK / "files")

    pins = [
        ("committed CAD 465m",            r"CAD 465(\.0)?m"),
        ("drawn CAD 288.4m",              r"CAD 288\.4m"),
        ("exposure CAD 341.7m",           r"CAD 341\.7m"),
        ("single-name limit CAD 500m",    r"CAD 500(\.0)?m"),
        ("utilisation 68.3%",             r"68\.3"),
        ("sector CAD 2,744m of CAD 3,200m", r"CAD 2,744m"),
        ("sector 85.8% amber",            r"85\.8"),
        ("PSE line CAD 90m / 69.2m",      r"CAD 69\.2m"),
        ("FY26 YTD CAD 8.42m",            r"CAD 8\.42m"),
        ("prior period CAD 7.14m",        r"CAD 7\.14m"),
        ("revenue +17.9%",                r"17\.9 per cent"),
        ("wallet share 21.4%",            r"21\.4"),
        ("covenant 4.18x of 4.50x",       r"4\.18x"),
        ("headroom 0.32 turns",           r"0\.32 turns"),
        ("prior quarter 3.94x",           r"3\.94x"),
        ("rating IG-6",                   r"IG-6"),
        ("prior rating IG-7",             r"IG-7"),
        ("revolver CAD 1.10bn to 1.35bn", r"CAD 1\.35bn"),
        ("target hold CAD 210m",          r"CAD 210m"),
        ("current hold CAD 165m",         r"CAD 165m"),
        ("KYC due 30 September 2026",     r"30 September 2026"),
        ("restriction CR-2026-0184",      r"CR-2026-0184"),
        ("hedging notional CAD 240m",     r"CAD 240m"),
    ]
    for label, pat in pins:
        check(f"Work IQ narrative states {label}", re.search(pat, corpus) is not None)

    # Policy citations must resolve to real documents.
    cited = set(re.findall(r"\bCP-0\d\d\b", corpus))
    known = {d["id"] for d in docs}
    check(f"every CP-xxx cited in Work IQ exists in Foundry IQ ({len(cited)} cited)",
          cited <= known, f"dangling: {sorted(cited - known)}")
    check("Work IQ cites at least 10 distinct policies", len(cited) >= 10)

    # The MNPI tension must be visible in Work IQ, Foundry IQ and the brief.
    check("MNPI tension present in Work IQ", "CR-2026-0184" in corpus)
    check("MNPI tension anchored in policy (CP-008 restricted list)",
          "restricted list" in ptext.lower())
    check("wall-crossed personas match scenario_facts",
          all(um["mapping"][a]["wall_status"] == "wall_crossed"
              for a in FACTS["mnpi_tension"]["restricted_persons"]))

    # ---------------------------------------------------------------- web iq
    print("\nWeb IQ")
    wq = json.loads((WEB / "web_iq_queries.json").read_text(encoding="utf-8"))
    check("mode is live_only", wq["mode"] == "live_only")
    check("no offline cache", wq["offline_cache"] is False)
    check("hero ticker matches scenario_facts", wq["hero_client"]["ticker"] == FACTS["hero_ticker"])
    check("8 topics defined", len(wq["topics"]) == 8)
    check("every role has default topics",
          set(wq["role_default_topics"]) == {"relationship_manager", "trader", "analyst", "credit_risk"})
    all_topic_ids = {t["id"] for t in wq["topics"]}
    check("role default topics all resolve",
          all(set(v) <= all_topic_ids for v in wq["role_default_topics"].values()))
    check("unavailable behaviour is defined",
          "unavailable" in wq["grounding"]["unavailable_behaviour"].lower())

    # ------------------------------------------------------------ disclaimer
    print("\nSynthetic-data disclosure")
    for p in [FOUNDRY / "cm_policies.json", WORK / "emails.json",
              WORK / "teams_messages.json", WEB / "web_iq_queries.json"]:
        txt = p.read_text(encoding="utf-8")
        check(f"{p.name} carries a synthetic-data note",
              "SYNTHETIC DEMO DATA" in txt or "synthetic" in txt.lower())
    for p in meetings + files:
        check(f"{p.name} carries a synthetic-data note",
              "SYNTHETIC DEMO DATA" in p.read_text(encoding="utf-8"))

    # ----------------------------------------------------------------- done
    print(f"\n{'-' * 70}")
    if _failures:
        print(f"FAILED  {len(_failures)} of {_checks} checks:")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print(f"PASSED  all {_checks} checks. Every layer agrees.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
