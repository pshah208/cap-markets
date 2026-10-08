"""Scenario engine - market factors -> covenants -> credit -> relationship value.

For any combination of seven factors (oil, gas, rates, credit spreads, USD/CAD, US tariff,
industrial demand), per client:

  1. EBITDA %   = beta_oil*oil + beta_gas*gas + beta_fx*usdcad + beta_demand*demand + beta_tariff*tariff
                  (betas from the governed Fabric table scenario_sensitivity;
                  calibrated so the oil-shock preset reproduces the Dashboard).
  2. Covenants  leverage / (1+e); interest coverage * (1+e) / (1 + floating share
                * rate move / all-in rate). Net debt does not move with EBITDA.
  3. Rating     notches = binding-covenant headroom lost * notches per turn,
                + extra notches on breach; PD from the rating.
  4. EAD        exposure, plus a share of undrawn revolvers drawn when EBITDA
                falls past the trigger (clients draw in stress).
  5. Value      relationship value = PV over the horizon of
                (revenue - expected loss - capital charge); revenue moves with
                EBITDA and with hedging demand on markets revenue; the discount
                rate moves with credit spreads.

The change in value is attributed sequentially to revenue, expected loss,
capital and discount rate, so the waterfall always sums to the total.

SYNTHETIC: illustrative economics for a demo, not a pricing or capital model.
"""

from __future__ import annotations

from typing import Any

from .client_skills import _band, _cushion, _ebitda_linked, _headroom
from .market_data import MARKET_DATA
from .skill_data import SKILL_DATA

SENS = MARKET_DATA["sensitivity"]
VAL = SENS["valuation"]
BETAS = SENS["betas"]
EXTRA = MARKET_DATA["extra"]
CLIENTS = SKILL_DATA["clients"]
HERO = SKILL_DATA["client"]["id"]
FACTOR_IDS = [f["id"] for f in SENS["factors"]]
YTD_MONTHS = 11.15  # FY26 YTD: 1 Nov 2025 -> 5 Oct 2026


def library() -> dict[str, Any]:
    return {"factors": SENS["factors"], "presets": SENS["presets"],
            "valuation": {k: v for k, v in VAL.items() if not k.endswith("_by_rating_pct")},
            "as_of": MARKET_DATA["scenario"]["as_of"],
            "source": "Fabric IQ - scenario_sensitivity, market_scenarios"}


def _clean(factors: dict[str, Any] | None) -> dict[str, float]:
    out = {}
    lim = {f["id"]: (f["min"], f["max"]) for f in SENS["factors"]}
    for fid in FACTOR_IDS:
        try:
            v = float((factors or {}).get(fid, 0.0))
        except (TypeError, ValueError):
            v = 0.0
        lo, hi = lim[fid]
        out[fid] = max(lo, min(hi, v))
    return out


def _rating_index(r: str) -> int:
    try:
        return int(r.split("-")[1])
    except (IndexError, ValueError):
        return 6


def _stress_cov(cov: dict, e_pct: float, rates_bp: float, floating: float) -> float:
    k = 1 + e_pct / 100
    if _ebitda_linked(cov) == "leverage":
        return cov["actual"] / k
    interest_k = 1 + floating * rates_bp / VAL["base_rate_bp"]
    return cov["actual"] * k / max(interest_k, 0.05)


def _economics(cid: str, rating: str, ead: float, revenue: float, disc_pct: float) -> dict[str, float]:
    pd_ = VAL["pd_by_rating_pct"][rating] / 100
    rw = VAL["rw_by_rating_pct"][rating] / 100
    el = pd_ * VAL["lgd_pct"] / 100 * ead
    cap = ead * rw * VAL["cet1_ratio_pct"] / 100 * VAL["cost_of_equity_pct"] / 100
    r = disc_pct / 100
    annuity = sum(1 / (1 + r) ** t for t in range(1, VAL["horizon_years"] + 1))
    return {"revenue": revenue, "el": el, "capital": cap, "annuity": annuity,
            "value": (revenue - el - cap) * annuity}


def client_result(cid: str, fx: dict[str, float]) -> dict[str, Any]:
    c, b, x = CLIENTS[cid], BETAS[cid], EXTRA[cid]
    e = (b["beta_oil"] * fx["oil_pct"] + b["beta_gas"] * fx["gas_pct"]
         + b["beta_fx"] * fx["usdcad_pct"] + b["beta_demand"] * fx["demand_pct"]
         + b.get("beta_tariff", 0.0) * fx.get("tariff_pct", 0.0))
    e = max(-60.0, min(60.0, round(e, 2)))
    floating = b["floating_debt_share"]

    covs = []
    for cov in c["covenants"]:
        if not _ebitda_linked(cov):
            continue
        v = _stress_cov(cov, e, fx["rates_bp"], floating)
        h_before, h_after = _headroom(cov, cov["actual"]), _headroom(cov, v)
        band, tone = _band(h_after)
        covs.append({"covenant": cov["covenant"], "threshold": cov["threshold"], "test": cov["test"],
                     "before": cov["actual"], "after": round(v, 2),
                     "headroom_before": round(h_before, 2), "headroom_after": round(h_after, 2),
                     "band_before": _band(h_before)[0], "band_after": band, "tone": tone,
                     "cushion_after": round(_cushion({**cov, "actual": v}), 1) if h_after > 0 else 0.0})
    binding = min(covs, key=lambda k: k["cushion_after"]) if covs else None

    base_idx = _rating_index(c["rating"])
    notches = 0
    if binding:
        lost = binding["headroom_before"] - binding["headroom_after"]
        notches = round(lost * VAL["notch_per_turn"])
        notches = max(-2, min(VAL.get("max_notches", 3), notches))
        if binding["band_after"] == "Breach":
            notches = min(VAL.get("max_notches", 3), notches + VAL["breach_extra_notches"])
    new_idx = max(1, min(12, base_idx + notches))
    rating_after = f"IG-{new_idx}"

    exposure = sum(p["current"] for p in x["exposure_by_product"])
    drawdown = (SENS["revolver_undrawn_m"].get(cid, 0.0) * VAL["drawdown_share_of_undrawn"]
                if e <= VAL["drawdown_trigger_ebitda_pct"] else 0.0)
    ead_after = exposure + drawdown

    rev_base = x["revenue_ytd_m"] * 12 / YTD_MONTHS
    rev_mkts = x.get("revenue_markets_ytd_m", 0.0) * 12 / YTD_MONTHS
    rev_after = (rev_base * (1 + VAL["revenue_elasticity_to_ebitda"] * e / 100)
                 + rev_mkts * VAL["markets_vol_uplift_per_pct_oil"] * abs(fx["oil_pct"]) / 100)
    disc_base = VAL["base_discount_rate_pct"]
    disc_after = disc_base + fx["spreads_bp"] / 100

    base = _economics(cid, c["rating"], exposure, rev_base, disc_base)
    after = _economics(cid, rating_after, ead_after, rev_after, disc_after)

    # Sequential attribution: revenue -> expected loss -> capital -> discount rate.
    a = base["annuity"]
    d_rev = (after["revenue"] - base["revenue"]) * a
    d_el = -(after["el"] - base["el"]) * a
    d_cap = -(after["capital"] - base["capital"]) * a
    d_disc = after["value"] - (base["value"] + d_rev + d_el + d_cap)

    out = {
        "id": cid, "name": c["name"], "sector": c["sector"], "tier": c["tier"],
        "ebitda_pct": round(e, 2), "covenants": covs, "binding": binding,
        "rating_before": c["rating"], "rating_after": rating_after, "notches": new_idx - base_idx,
        "pd_before_pct": VAL["pd_by_rating_pct"][c["rating"]], "pd_after_pct": VAL["pd_by_rating_pct"][rating_after],
        "ead_before_m": round(exposure, 1), "ead_after_m": round(ead_after, 1), "drawdown_m": round(drawdown, 1),
        "revenue_before_m": round(rev_base, 2), "revenue_after_m": round(rev_after, 2),
        "el_before_m": round(base["el"], 3), "el_after_m": round(after["el"], 3),
        "capital_before_m": round(base["capital"], 2), "capital_after_m": round(after["capital"], 2),
        "value_before_m": round(base["value"], 2), "value_after_m": round(after["value"], 2),
        "value_change_m": round(after["value"] - base["value"], 2),
        "value_change_pct": round((after["value"] - base["value"]) / abs(base["value"]) * 100, 1) if base["value"] else None,
        "drivers": {"revenue": round(d_rev, 2), "expected_loss": round(d_el, 2),
                    "capital": round(d_cap, 2), "discount_rate": round(d_disc, 2)},
        "business_model": b["business_model"],
    }
    if cid == HERO:
        fin = SKILL_DATA["financials"]
        ebitda = fin["adjusted_ebitda_ltm_m"] * (1 + e / 100)
        thr = SKILL_DATA["covenant"]["threshold"]
        out["deal"] = {"max_clearing_m": round(max(0.0, thr * ebitda - fin["total_net_debt_m"]), 1),
                       "ask_leverage": round((fin["total_net_debt_m"] + 250) / ebitda, 2)}
    return out


def run(factors: dict[str, Any] | None, name: str = "Custom") -> dict[str, Any]:
    fx = _clean(factors)
    rows = [client_result(cid, fx) for cid in CLIENTS]
    rows.sort(key=lambda r: r["value_change_m"])
    tot = lambda k: round(sum(r[k] for r in rows), 2)  # noqa: E731
    drivers = {k: round(sum(r["drivers"][k] for r in rows), 2)
               for k in ("revenue", "expected_loss", "capital", "discount_rate")}
    sector: dict[str, dict] = {}
    for r in rows:
        s = sector.setdefault(r["sector"], {"sector": r["sector"], "before": 0.0, "after": 0.0, "count": 0})
        s["before"] += r["value_before_m"]
        s["after"] += r["value_after_m"]
        s["count"] += 1
    return {
        "name": name, "factors": fx, "as_of": MARKET_DATA["scenario"]["as_of"],
        "portfolio": {
            "value_before_m": tot("value_before_m"), "value_after_m": tot("value_after_m"),
            "value_change_m": round(tot("value_after_m") - tot("value_before_m"), 2),
            "value_change_pct": round((tot("value_after_m") / tot("value_before_m") - 1) * 100, 1),
            "revenue_before_m": tot("revenue_before_m"), "revenue_after_m": tot("revenue_after_m"),
            "el_before_m": tot("el_before_m"), "el_after_m": tot("el_after_m"),
            "ead_before_m": tot("ead_before_m"), "ead_after_m": tot("ead_after_m"),
            "breaches": sum(1 for r in rows if r["binding"] and r["binding"]["band_after"] == "Breach"),
            "tight": sum(1 for r in rows if r["binding"] and r["binding"]["band_after"] == "Tight"),
            "downgrades": sum(1 for r in rows if r["notches"] > 0),
            "upgrades": sum(1 for r in rows if r["notches"] < 0),
            "drivers": drivers,
        },
        "sectors": [{**s, "before": round(s["before"], 2), "after": round(s["after"], 2),
                     "change_pct": round((s["after"] - s["before"]) / abs(s["before"]) * 100, 1) if s["before"] else None}
                    for s in sector.values()],
        "clients": rows,
        "method": __doc__.split("SYNTHETIC")[0].strip().split("\n\n", 1)[1],
    }


def narrative_prompt(result: dict[str, Any], context: str = "") -> str:
    """Compact, factual brief for the scenario-analyst agent."""
    f, p = result["factors"], result["portfolio"]
    lines = [f"{r['name']}: EBITDA {r['ebitda_pct']:+.1f}%, "
             + (f"{r['binding']['covenant']} {r['binding']['before']}x->{r['binding']['after']}x vs "
                f"{r['binding']['threshold']}x ({r['binding']['band_after']}), " if r["binding"] else "")
             + f"rating {r['rating_before']}->{r['rating_after']}, relationship value "
               f"{r['value_change_m']:+.2f}m"
             + (f" ({r['value_change_pct']:+.1f}%)" if r["value_change_pct"] is not None else "")
             for r in result["clients"]]
    return (
        f"Scenario '{result['name']}' as at {result['as_of']} (synthetic): oil {f['oil_pct']:+g}%, gas {f['gas_pct']:+g}%, "
        f"GoC 10Y {f['rates_bp']:+g}bp, CAD IG spreads {f['spreads_bp']:+g}bp, USD/CAD {f['usdcad_pct']:+g}%, "
        f"industrial demand {f['demand_pct']:+g}%, US tariff on Canadian goods {f.get('tariff_pct', 0):g}%. "
        f"Treat the scenario as given.\n"
        + (f"{context}\n" if context else "") +
        f"Engine results (deterministic, from Fabric IQ scenario_sensitivity): portfolio relationship value "
        f"{p['value_before_m']:.1f}m -> {p['value_after_m']:.1f}m ({p['value_change_pct']:+.1f}%); "
        f"{p['breaches']} covenant breaches, {p['tight']} tight, {p['downgrades']} rating downgrades; "
        f"drivers revenue {p['drivers']['revenue']:+.2f}m, expected loss {p['drivers']['expected_loss']:+.2f}m, "
        f"capital {p['drivers']['capital']:+.2f}m, discount rate {p['drivers']['discount_rate']:+.2f}m.\n"
        + "\n".join(lines) + "\n\n"
        "Write a committee-ready scenario brief: (1) headline in one sentence; (2) the three relationships that "
        "matter most and why, verifying their covenant and limit positions in Fabric IQ; (3) what the Credit & "
        "Markets Committee house view (CP-015) and CP-002/CP-005 imply for lending, capital and sector posture; "
        "(4) three concrete actions with owners. Refer to our firm as 'the Bank'. Refer to people by role only."
    )
