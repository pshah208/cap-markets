/**
 * "How it works" - the scenario engine as an animated six-stage pipeline.
 * Each stage shows its rule AND the live numbers for one example relationship,
 * so the method is read through a real run rather than as prose. CSS-only motion
 * (transform / opacity), staggered, and disabled under prefers-reduced-motion.
 */
import { useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import type { ClientRun, Library, ScenarioRun } from "./types";

const ICON: Record<string, ReactNode> = {
  factors: <path d="M3 17l5-6 4 3 6-8M15 6h3v3" />,
  ebitda: <path d="M4 19V9M10 19V5M16 19v-7M2 19h20" />,
  covenant: <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6l8-3zM8.5 12l2.5 2.5 4.5-5" />,
  rating: <path d="M12 4v16M6 14l6 6 6-6" />,
  loss: <path d="M12 3v18M17 7.5C17 5.6 14.8 4.5 12 4.5S7 5.6 7 7.5s2 3 5 3.5 5 1.6 5 3.5-2.2 3-5 3-5-1.1-5-3" />,
  value: <path d="M3 12h4l3-7 4 14 3-7h4" />,
};

const s = (v: number, dp = 1) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(dp)}`;
const FACTOR_SHORT: Record<string, string> = {
  oil_pct: "Oil", gas_pct: "Gas", tariff_pct: "Tariff", rates_bp: "Rates", spreads_bp: "Spreads", usdcad_pct: "USD/CAD", demand_pct: "Demand",
};

interface Stage { id: string; title: string; rule: string; source: string; live: ReactNode }

function stages(c: ClientRun, run: ScenarioRun, v: Record<string, number>): Stage[] {
  const moved = Object.entries(run.factors).filter(([, x]) => x !== 0);
  const b = c.binding;
  return [
    {
      id: "factors", title: "Market factors", source: "market_scenarios",
      rule: "Seven governed factors: a committee preset or your own slider settings.",
      live: moved.length
        ? <span className="sc-flow-chips">{moved.map(([k, x]) => <em key={k}>{FACTOR_SHORT[k] ?? k} {s(x, k.endsWith("bp") ? 0 : 1)}{k.endsWith("bp") ? "bp" : "%"}</em>)}</span>
        : <span>All factors flat</span>,
    },
    {
      id: "ebitda", title: "EBITDA impact", source: "scenario_sensitivity",
      rule: "Σ βᵢ × factorᵢ. Per-client betas are calibrated so today's shock matches the Dashboard.",
      live: <><b className={c.ebitda_pct < 0 ? "t-down" : c.ebitda_pct > 0 ? "t-up" : ""}>{s(c.ebitda_pct)}%</b><small>adjusted EBITDA</small></>,
    },
    {
      id: "covenant", title: "Covenant stress", source: "covenants",
      rule: "Leverage ÷ (1 + Δ). Coverage also pays floating-rate interest on the rates move.",
      live: b ? <><b>{b.before.toFixed(2)}x → {b.after.toFixed(2)}x</b><small>vs {b.threshold.toFixed(2)}x · <span className={`sc-band b-${b.band_after === "Breach" ? "bad" : b.band_after === "Tight" ? "warn" : b.band_after === "Monitor" ? "watch" : "ok"}`}>{b.band_after}</span></small></> : <small>No EBITDA-linked covenant</small>,
    },
    {
      id: "rating", title: "Rating migration", source: "risk_ratings",
      rule: `${v.notch_per_turn ?? 3} notches per turn of headroom lost, +${v.breach_extra_notches ?? 1} on breach, capped at ${v.max_notches ?? 3}.`,
      live: <><b className={c.notches > 0 ? "t-down" : c.notches < 0 ? "t-up" : ""}>{c.rating_before} → {c.rating_after}</b><small>PD {c.pd_before_pct}% → {c.pd_after_pct}%</small></>,
    },
    {
      id: "loss", title: "Loss & capital", source: "exposures · credit_facilities",
      rule: `EL = PD × ${v.lgd_pct ?? 40}% LGD × EAD. Capital = RWA × ${v.cet1_ratio_pct ?? 11.5}% CET1 × ${v.cost_of_equity_pct ?? 12}% cost of equity.`,
      live: <><b>EL {c.el_before_m.toFixed(2)} → {c.el_after_m.toFixed(2)}m</b><small>capital {c.capital_before_m.toFixed(2)} → {c.capital_after_m.toFixed(2)}m{c.drawdown_m > 0 ? ` · +${c.drawdown_m.toFixed(1)}m draw` : ""}</small></>,
    },
    {
      id: "value", title: "Relationship value", source: "client_360",
      rule: `PV over ${v.horizon_years ?? 3} years of revenue − EL − capital at ${v.base_discount_rate_pct ?? 9}% plus the spread move.`,
      live: <><b className={c.value_change_m < 0 ? "t-down" : c.value_change_m > 0 ? "t-up" : ""}>{c.value_before_m.toFixed(2)} → {c.value_after_m.toFixed(2)}m</b><small>{s(c.value_change_m, 2)}m</small></>,
    },
  ];
}

export function MethodFlow({ run, lib, initialId }: { run: ScenarioRun; lib: Library; initialId?: string | null }) {
  const [exId, setExId] = useState<string>(initialId ?? run.clients[0]?.id ?? "");
  const [focus, setFocus] = useState<string | null>(null);
  const c = run.clients.find((x) => x.id === exId) ?? run.clients[0];
  if (!c) return null;
  const list = stages(c, run, lib.valuation);

  return (
    <section className="sc-flow" aria-label="How the scenario engine works">
      <div className="sc-flow-head">
        <div>
          <span className="sc-flow-kicker">How it works</span>
          <h2>Six deterministic steps from market move to relationship value</h2>
          <p>Every number is reproducible. Inputs come from governed Fabric IQ tables; the Scenario Analyst only narrates them.</p>
        </div>
        <label className="sc-flow-pick">
          <span>Trace a relationship</span>
          <select value={c.id} onChange={(e) => setExId(e.target.value)}>
            {run.clients.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
          </select>
        </label>
      </div>

      <ol className={`sc-flow-track${focus ? " has-focus" : ""}`}>
        {list.map((st, i) => (
          <li key={st.id} className={`sc-flow-stage${focus === st.id ? " focus" : ""}`} style={{ "--i": i } as CSSProperties}
              tabIndex={0} onMouseEnter={() => setFocus(st.id)} onMouseLeave={() => setFocus(null)}
              onFocus={() => setFocus(st.id)} onBlur={() => setFocus(null)}>
            {i > 0 && <span className="sc-flow-link" aria-hidden><i /></span>}
            <div className="sc-flow-node">
              <span className="sc-flow-icon" aria-hidden>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">{ICON[st.id]}</svg>
              </span>
              <span className="sc-flow-step">{String(i + 1).padStart(2, "0")}</span>
            </div>
            <h3>{st.title}</h3>
            <p className="sc-flow-rule">{st.rule}</p>
            <div className="sc-flow-live" key={`${c.id}-${run.name}-${JSON.stringify(run.factors)}`}>{st.live}</div>
            <code className="sc-flow-src">{st.source}</code>
          </li>
        ))}
      </ol>

      <div className="sc-flow-foot">
        <div className="sc-flow-tile fabric" style={{ "--i": 6 } as CSSProperties}>
          <small>Fabric IQ · governed data</small>
          <b>scenario_sensitivity · market_scenarios</b>
          <span>Per-client betas, floating-debt share and the preset library, joined to client_360.</span>
        </div>
        <div className="sc-flow-tile foundry" style={{ "--i": 7 } as CSSProperties}>
          <small>Foundry IQ · policy</small>
          <b>CP-015 · CP-002 · CP-005</b>
          <span>House view, sector concentration and covenant pro-forma rules frame the brief.</span>
        </div>
        <div className="sc-flow-tile agent" style={{ "--i": 8 } as CSSProperties}>
          <small>Foundry agent</small>
          <b>Agent-scenario-analyst</b>
          <span>Fabric IQ + Foundry IQ only. No mailbox, Teams or web, so it can't leak correspondence or override governed numbers.</span>
        </div>
      </div>

      <details className="sc-flow-text">
        <summary>Full method (text)</summary>
        <pre>{run.method}</pre>
      </details>
    </section>
  );
}
