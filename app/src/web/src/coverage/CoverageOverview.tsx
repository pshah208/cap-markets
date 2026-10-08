/**
 * Accounts overview - the top of the dashboard.
 *
 * Woodgrove-style: greeting, data-source chips, a market pulse, an alert that
 * starts the triage flow, exposure by tier, KPI cards, relationships and the
 * review calendar. The pulse is a SYNTHETIC scenario and says so - it is
 * labelled "Scenario", never "Live".
 */

import type { CoverageOverview as Overview } from "./types";

const fmt = (v: number, d = 1) => v.toLocaleString("en-CA", { minimumFractionDigits: d, maximumFractionDigits: d });
const TIER_COLOURS = ["var(--cp-accent)", "#7c3aed", "#0f766e"];
const HEALTH = { healthy: "Healthy", attention: "Attention", at_risk: "At risk" } as const;

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function MarketPulse({ data }: { data: Overview }) {
  return (
    <section className="cv-pulse" aria-label="Market pulse (synthetic scenario)">
      <header>
        <span className="cv-pulse-title">Market pulse</span>
        <span className="cv-pulse-tag" title="Synthetic scenario for the demo - not live market data">● Scenario</span>
        <span className="cv-pulse-time">{data.time_local} · {new Date(data.as_of + "T12:00:00").toLocaleDateString("en-CA", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}</span>
      </header>
      <div className="cv-pulse-grid">
        {data.scenario.pulse.map((p) => (
          <div className="cv-pulse-panel" key={p.panel}>
            <h4>{p.panel}</h4>
            {p.rows.map((r) => (
              <div className="cv-pulse-row" key={r.name}>
                <span className="cv-pulse-name">{r.name}</span>
                <span className="cv-pulse-val">
                  <b>{r.level}</b>
                  <em className={(r.bad ? r.dir === "up" : r.dir === "down") ? "neg" : "pos"}>{r.change}</em>
                </span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}

export function CoverageOverview({ data, userName, onReviewImpact, onOpenClient, onShowCoverage }: {
  data: Overview;
  userName: string;
  onReviewImpact: () => void;
  onOpenClient: (id: string) => void;
  onShowCoverage?: () => void;
}) {
  const k = data.kpis;
  const totalTier = data.tiers.reduce((s, t) => s + t.exposure_m, 0) || 1;
  const first = userName.split(" ")[0] || "there";

  return (
    <section className="cv-overview" aria-label="Accounts overview">
      <div className="cv-head">
        <div>
          <h1>{greeting()}, {first} <span className="cv-head-sep">|</span> Accounts overview</h1>
          <div className="cv-head-chips">
            <span className="cv-chip cv-chip-accent">CAD {fmt(k.exposure_m / 1000, 2)}bn exposure</span>
            <span className="cv-chip">{k.relationships} active relationships</span>
          </div>
        </div>
        {onShowCoverage && (
          <button type="button" className="cv-to-coverage" onClick={onShowCoverage}>
            Coverage overview
            <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M3 8h10M9 4l4 4-4 4" /></svg>
          </button>
        )}
      </div>

      <MarketPulse data={data} />

      <div className="cv-alert" role="alert">
        <span className="cv-alert-icon" aria-hidden>
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></svg>
        </span>
        <div className="cv-alert-text">
          <strong>Market alert · {data.scenario.title}</strong>
          <span>{data.scenario.alert} <b>{data.affected_count} relationships are materially affected.</b></span>
        </div>
        <button type="button" className="cv-alert-btn" onClick={onReviewImpact}>Review impact</button>
      </div>

      <div className="cv-card cv-tiers">
        <div className="cv-card-head"><h3>Exposure by tier</h3><span>CAD {fmt(totalTier)}m total</span></div>
        <div className="cv-tier-bar">
          {data.tiers.map((t, i) => (
            <span key={t.tier} style={{ width: `${t.exposure_m / totalTier * 100}%`, background: TIER_COLOURS[i % 3] }} />
          ))}
        </div>
        <div className="cv-tier-legend">
          {data.tiers.map((t, i) => (
            <div key={t.tier}>
              <span className="cv-tier-pill" style={{
                background: TIER_COLOURS[i % 3],
                color: i % 3 === 0 ? "var(--cp-accent-fg)" : "#fff",
              }}>{t.tier}</span>
              <b>CAD {fmt(t.exposure_m)}m</b>
              <small>{t.count} relationship{t.count === 1 ? "" : "s"}</small>
            </div>
          ))}
        </div>
      </div>

      <div className="cv-kpis">
        <article className="cv-card cv-kpi">
          <h3>Total exposure</h3><strong>CAD {fmt(k.exposure_m / 1000, 2)}bn</strong>
          <small>Committed CAD {fmt(k.committed_m / 1000, 2)}bn across all facilities</small>
        </article>
        <article className="cv-card cv-kpi">
          <h3>Relationship revenue</h3><strong>CAD {fmt(k.revenue_ytd_m)}m</strong>
          <small>FY26 YTD{k.revenue_yoy_pct !== null ? ` · ${k.revenue_yoy_pct >= 0 ? "+" : ""}${k.revenue_yoy_pct}% YoY` : ""}</small>
        </article>
        <article className="cv-card cv-kpi">
          <h3>Relationships</h3><strong>{k.relationships}</strong>
          <small>
            <span className="h-ok">{k.health.healthy} healthy</span> · <span className="h-warn">{k.health.attention} attention</span> · <span className="h-bad">{k.health.at_risk} at risk</span>
          </small>
        </article>
        <article className="cv-card cv-kpi">
          <h3>Shock: covenant breaches</h3><strong className={k.stressed_breaches ? "h-bad" : ""}>{k.stressed_breaches}</strong>
          <small>On shocked EBITDA · {data.affected_count} materially affected</small>
        </article>
      </div>

      <div className="cv-two">
        <article className="cv-card">
          <div className="cv-card-head"><h3>Relationships</h3><span>ranked by shock severity</span></div>
          <ul className="cv-rel-list">
            {data.relationships.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => onOpenClient(r.id)}>
                  <span className={`cv-dot ${r.health}`} aria-hidden />
                  <span className="cv-rel-name">{r.name}<small>{r.tier} · {r.sector}</small></span>
                  <span className="cv-rel-shock">{r.ebitda_shock_pct > 0 ? "+" : ""}{r.ebitda_shock_pct.toFixed(1)}%<small>EBITDA</small></span>
                  <span className={`cv-score ${r.affected ? "on" : ""}`}>{r.score}</span>
                  <span className={`cv-health ${r.health}`}>{HEALTH[r.health]}</span>
                </button>
              </li>
            ))}
          </ul>
        </article>
        <article className="cv-card">
          <div className="cv-card-head"><h3>Upcoming reviews</h3><span>next 120 days</span></div>
          <ul className="cv-review-list">
            {data.reviews.map((r, i) => (
              <li key={i}>
                <time>{new Date(r.date + "T12:00:00").toLocaleDateString("en-CA", { month: "short", day: "numeric" })}</time>
                <div>
                  <b>{r.kind}</b> · {r.client_id
                    ? <button type="button" className="cv-link" onClick={() => onOpenClient(r.client_id!)}>{r.client}</button>
                    : r.client}
                  <small>{r.detail}</small>
                </div>
              </li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}
