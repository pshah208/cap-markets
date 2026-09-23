/**
 * Chapter 12 - what the agent costs to run.
 *
 * The rest of the deck argues that a grounded answer is *better*. This slide
 * answers the question that always follows it in a bank: what does it cost, and
 * can we see it?
 *
 * PROVENANCE MATTERS MORE THAN THE CHART. Tokens, latency, success and the
 * grounding calls behind them are read from the Foundry project's own gen-AI
 * traces in Application Insights - the same telemetry the Foundry portal's
 * Monitoring blade renders. Nothing on this slide is synthesised, and the only
 * derived number is cost, which is tokens x list price and is labelled as an
 * estimate wherever it appears. If the traces cannot be read, the slide says so
 * rather than showing plausible numbers.
 *
 * Charts are hand-rolled SVG for the same reason `Chart.tsx` is: no chart
 * library may reformat or round a figure presented as measured.
 */

import { useCallback, useEffect, useState } from "react";
import { fetchAgentMetrics } from "../api";
import type { AgentMetrics, AllInCost, BilledCost, Chapter, IQId } from "../types";

/** How often the slide re-reads the telemetry while it is on screen. */
const POLL_MS = 15_000;

const LAYER_COLOUR: Record<IQId, string> = {
  work: "var(--work)",
  fabric: "var(--fabric)",
  foundry: "var(--foundry)",
  web: "var(--web)",
};

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** Money is shown to whatever precision keeps it meaningful, never rounded to 0. */
function fmtMoney(n: number, currency = "CAD"): string {
  const dp = n >= 1 ? 2 : n >= 0.1 ? 3 : 4;
  return `${currency} ${n.toFixed(dp)}`;
}

function fmtSeconds(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

/** Invoice-style money: always 2dp, so a column of them reads as a bill. */
function fmtBilled(n: number, currency: string): string {
  return `${currency} ${n.toFixed(2)}`;
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const mag = Math.pow(10, Math.floor(Math.log10(v)));
  const norm = v / mag;
  const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
  return step * mag;
}

/* ------------------------------------------------------- token columns --- */

/**
 * Tokens per run, prompt and completion stacked.
 *
 * Stacked rather than two series because the story is the ratio: a grounded run
 * spends most of its tokens *reading* what the four layers returned, and seeing
 * the dark band dwarf the light one is the point.
 */
function TokenColumns({ m }: { m: AgentMetrics }) {
  const data = m.series;
  if (!data.length) return null;

  const width = 720;
  const height = 210;
  const padTop = 18;
  const padBottom = 26;
  const padLeft = 46;
  const plotH = height - padTop - padBottom;
  const plotW = width - padLeft - 12;
  const max = niceMax(Math.max(...data.map((d) => d.totalTokens)));
  const slot = plotW / data.length;
  const barW = Math.max(6, Math.min(26, slot - 6));

  return (
    <figure className="chart tel-chart">
      <figcaption className="tel-chart-head">
        <span className="tel-chart-title">Tokens per question</span>
        <span className="tel-chart-legend">
          <span className="tel-key tel-key-in" /> prompt
          <span className="tel-key tel-key-out" /> completion
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="Tokens consumed per agent run, from Foundry traces"
           preserveAspectRatio="xMinYMin meet">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={padLeft} x2={width - 12}
                  y1={padTop + plotH * (1 - f)} y2={padTop + plotH * (1 - f)}
                  className="chart-grid" />
            <text x={padLeft - 8} y={padTop + plotH * (1 - f)}
                  className="chart-tick" textAnchor="end" dominantBaseline="middle">
              {fmtTokens(max * f)}
            </text>
          </g>
        ))}

        {data.map((d, i) => {
          const x = padLeft + i * slot + (slot - barW) / 2;
          const hIn = (d.inputTokens / max) * plotH;
          const hOut = (d.outputTokens / max) * plotH;
          const yOut = padTop + plotH - hIn - hOut;
          const title =
            `${d.label} · ${fmtTokens(d.inputTokens)} prompt + ` +
            `${fmtTokens(d.outputTokens)} completion · ` +
            `${fmtMoney(d.cost, m.currency)} · ${fmtSeconds(d.latencyMs)}` +
            `${d.ok ? "" : " · failed"}`;
          return (
            <g key={d.t + i} className={`tel-col${d.ok ? "" : " failed"}`}>
              <title>{title}</title>
              <rect x={x} y={padTop + plotH - hIn} width={barW} height={Math.max(1, hIn)}
                    className="tel-bar-in" rx={2}>
                <animate attributeName="height" from="0" to={Math.max(1, hIn)}
                         dur="0.45s" fill="freeze" />
              </rect>
              <rect x={x} y={yOut} width={barW} height={Math.max(1, hOut)}
                    className="tel-bar-out" rx={2} />
            </g>
          );
        })}

        <line x1={padLeft} x2={width - 12} y1={padTop + plotH} y2={padTop + plotH}
              className="chart-axis" />
        <text x={padLeft} y={height - 6} className="chart-tick">{data[0].label}</text>
        <text x={width - 12} y={height - 6} className="chart-tick" textAnchor="end">
          {data[data.length - 1].label}
        </text>
      </svg>
    </figure>
  );
}

/* ------------------------------------------------------------ cost area --- */

/** Cumulative estimated spend across the runs in the window. */
function CostArea({ m }: { m: AgentMetrics }) {
  const data = m.series;
  if (data.length < 2) return null;

  const width = 720;
  const height = 190;
  const padTop = 18;
  const padBottom = 26;
  const padLeft = 56;
  const plotH = height - padTop - padBottom;
  const plotW = width - padLeft - 12;
  const first = data[0].cumulativeCost - data[0].cost;
  const max = Math.max(...data.map((d) => d.cumulativeCost)) || 1;

  const pt = (i: number, v: number): [number, number] => [
    padLeft + (i / (data.length - 1)) * plotW,
    padTop + plotH - (v / max) * plotH,
  ];
  const line = data.map((d, i) => pt(i, d.cumulativeCost).join(",")).join(" ");
  const area =
    `${padLeft},${padTop + plotH} ${line} ${padLeft + plotW},${padTop + plotH}`;

  return (
    <figure className="chart tel-chart">
      <figcaption className="tel-chart-head">
        <span className="tel-chart-title">Cumulative estimated cost</span>
        <span className="tel-chart-sub">
          {m.currency} · derived from measured tokens · {m.pricing.model || m.model}
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img"
           aria-label="Cumulative estimated agent cost"
           preserveAspectRatio="xMinYMin meet">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={padLeft} x2={width - 12}
                  y1={padTop + plotH * (1 - f)} y2={padTop + plotH * (1 - f)}
                  className="chart-grid" />
            <text x={padLeft - 8} y={padTop + plotH * (1 - f)}
                  className="chart-tick" textAnchor="end" dominantBaseline="middle">
              {(max * f).toFixed(2)}
            </text>
          </g>
        ))}

        <polygon points={area} className="tel-area" />
        <polyline points={line} className="tel-line" />

        {data.map((d, i) => {
          const [x, y] = pt(i, d.cumulativeCost);
          return (
            <circle key={d.t + i} cx={x} cy={y} r={2.6} className="tel-dot">
              <title>
                {`${d.label} · this question ${fmtMoney(d.cost, m.currency)} · ` +
                 `running total ${fmtMoney(d.cumulativeCost, m.currency)}`}
              </title>
            </circle>
          );
        })}

        <line x1={padLeft} x2={width - 12} y1={padTop + plotH} y2={padTop + plotH}
              className="chart-axis" />
        <text x={padLeft} y={height - 6} className="chart-tick">
          {first > 0 ? `${data[0].label} (carried ${first.toFixed(2)})` : data[0].label}
        </text>
        <text x={width - 12} y={height - 6} className="chart-tick" textAnchor="end">
          {data[data.length - 1].label}
        </text>
      </svg>
    </figure>
  );
}

/* --------------------------------------------------------- layer split --- */

/**
 * Which IQ layer the spend went to, derived from the `execute_tool` spans
 * recorded against each run.
 *
 * A run that reached three layers has its tokens split three ways: the context
 * is shared, so charging the whole run to each layer would treble the bill.
 */
function LayerSplit({ m }: { m: AgentMetrics }) {
  if (!m.byLayer.length) return null;
  const max = Math.max(...m.byLayer.map((l) => l.tokens)) || 1;

  return (
    <div className="tel-layers">
      <div className="tel-chart-head">
        <span className="tel-chart-title">Where the tokens go</span>
        <span className="tel-chart-sub">
          from the tool spans on each run · shared context split across the layers it used
        </span>
      </div>
      {m.byLayer.map((l) => (
        <div className="tel-layer-row" key={l.id}>
          <span className="tel-layer-name">
            <span className="tel-layer-swatch" style={{ background: LAYER_COLOUR[l.id] }} />
            {l.name}
          </span>
          <span className="tel-layer-track">
            <span
              className="tel-layer-fill"
              style={{ width: `${(l.tokens / max) * 100}%`, background: LAYER_COLOUR[l.id] }}
            />
          </span>
          <span className="tel-layer-value">{fmtTokens(l.tokens)}</span>
          <span className="tel-layer-cost">{fmtMoney(l.cost, m.currency)}</span>
          <span className="tel-layer-pct">{l.pct}%</span>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------- recent runs --- */

function RecentRuns({ m }: { m: AgentMetrics }) {
  if (!m.recent.length) return null;
  return (
    <div className="tel-runs">
      <div className="tel-chart-head">
        <span className="tel-chart-title">Recent questions</span>
        <span className="tel-chart-sub">newest first · one row per traced agent run</span>
      </div>
      <table className="tel-table">
        <thead>
          <tr>
            <th>When</th><th>Status</th><th>Layers</th><th>Tools</th>
            <th className="num">Tokens</th><th className="num">Latency</th>
            <th className="num">Est. cost</th>
          </tr>
        </thead>
        <tbody>
          {m.recent.map((r, i) => (
            <tr key={r.t + i}>
              <td>{r.label}</td>
              <td className={r.ok ? "ok" : "bad"}>{r.ok ? "✓ complete" : "✕ failed"}</td>
              <td>
                {r.layers.length
                  ? r.layers.map((l) => (
                      <span className="tel-chip" key={l}
                            style={{ borderColor: LAYER_COLOUR[l], color: LAYER_COLOUR[l] }}>
                        {l}
                      </span>
                    ))
                  : <span className="tel-chip tel-chip-none">none</span>}
              </td>
              <td>{r.toolCalls}</td>
              <td className="num">{fmtTokens(r.totalTokens)}</td>
              <td className="num">{fmtSeconds(r.latencyMs)}</td>
              <td className="num">{fmtMoney(r.cost, m.currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* -------------------------------------------------------- billed cost --- */

/**
 * What Azure actually charged, by resource.
 *
 * This panel exists because the token bill is the *small* half of the answer on
 * this workload. Azure AI Search - the index behind Foundry IQ - is provisioned
 * capacity billed by the hour, so it costs the same whether the agent is asked
 * nine questions or nine thousand, and it dominates the invoice. Showing tokens
 * alone would understate the real number by an order of magnitude, which is the
 * kind of plausible-but-wrong figure the rest of this deck is about.
 *
 * Fixed and metered are separated rather than just ranked, because the split is
 * the actionable part: metered cost is a function of adoption, fixed cost is a
 * function of the SKU you chose and is the first place to look when the bill is
 * too high at low volume.
 */
function BilledCostPanel({ b, allIn, tokenCost }: {
  b: BilledCost; allIn: AllInCost | null; tokenCost: number;
}) {
  if (!b.available) {
    return (
      <div className="tel-runs tel-billed">
        <div className="tel-chart-head">
          <span className="tel-chart-title">What Azure actually charged</span>
        </div>
        <div className="tel-empty-sub">
          {b.detail} {b.error && <code>{b.error}</code>}
        </div>
      </div>
    );
  }

  const max = Math.max(...b.items.map((i) => i.cost)) || 1;
  const fixedPct = b.fixedPct;

  return (
    <div className="tel-runs tel-billed">
      <div className="tel-chart-head">
        <span className="tel-chart-title">What Azure actually charged</span>
        <span className="tel-chart-sub">{b.detail}</span>
      </div>

      {/* The headline split, before the per-resource detail. */}
      <div className="tel-split">
        <div className="tel-split-bar" role="img"
             aria-label={`${fixedPct}% provisioned capacity, ${(100 - fixedPct).toFixed(1)}% usage-metered`}>
          <span className="tel-split-fixed" style={{ width: `${fixedPct}%` }} />
          <span className="tel-split-metered" style={{ width: `${100 - fixedPct}%` }} />
        </div>
        <div className="tel-split-keys">
          <span className="tel-split-key">
            <span className="tel-key tel-key-fixed" />
            Provisioned capacity{" "}
            <strong>{fmtBilled(b.fixed, b.currency)}</strong> ({fixedPct}%)
            <em>billed whether or not anyone asks a question</em>
          </span>
          <span className="tel-split-key">
            <span className="tel-key tel-key-metered" />
            Usage-metered{" "}
            <strong>{fmtBilled(b.metered, b.currency)}</strong>{" "}
            ({(100 - fixedPct).toFixed(1)}%)
            <em>scales with questions asked</em>
          </span>
        </div>
      </div>

      <table className="tel-table tel-cost-table">
        <thead>
          <tr>
            <th>Service</th><th>Resource</th><th>Role</th><th>Billing</th>
            <th className="num">{b.windowDays}-day cost</th>
            <th className="tel-cost-bar-col">Share</th>
          </tr>
        </thead>
        <tbody>
          {b.items.map((i) => (
            <tr key={i.name}>
              <td className="tel-cost-service">{i.service}</td>
              <td className="tel-cost-name">{i.name}</td>
              <td className="tel-cost-role">{i.role}</td>
              <td>
                <span className={`tel-billing ${i.metered ? "metered" : "fixed"}`}>
                  {i.metered ? "metered" : "provisioned"}
                </span>
              </td>
              <td className="num">{fmtBilled(i.cost, b.currency)}</td>
              <td className="tel-cost-bar-col">
                <span className="tel-layer-track">
                  <span
                    className={`tel-layer-fill ${i.metered ? "metered" : "fixed"}`}
                    style={{ width: `${(i.cost / max) * 100}%` }}
                  />
                </span>
                <span className="tel-cost-pct">{i.pct}%</span>
              </td>
            </tr>
          ))}
          <tr className="tel-cost-total">
            <td colSpan={4}>Total</td>
            <td className="num">{fmtBilled(b.total, b.currency)}</td>
            <td />
          </tr>
        </tbody>
      </table>

      {allIn && (
        <div className="tel-allin">
          <div className="tel-allin-figure">
            <span className="tel-allin-label">All-in, per question</span>
            <span className="tel-allin-value">
              {fmtBilled(allIn.costPerQuestion, b.currency)}
            </span>
            <span className="tel-allin-sub">
              vs {fmtMoney(allIn.tokenCostPerQuestion, b.currency)} of tokens
            </span>
          </div>
          <div className="tel-allin-note">
            At this volume the platform costs{" "}
            <strong>{allIn.multiple}x</strong> its own token bill
            {tokenCost > 0 && (
              <> — {fmtBilled(allIn.platformCost, b.currency)} of Azure to serve{" "}
              {fmtMoney(tokenCost, b.currency)} of model usage</>
            )}. Provisioned capacity is amortised across however many questions
            are asked, so the per-question figure falls as adoption rises while
            the token cost per question stays flat.
            <span className="tel-allin-basis">{allIn.basis}</span>
          </div>
        </div>
      )}
    </div>
  );
}

/* --------------------------------------------------------------- slide --- */

export function TelemetrySlide({ ch }: { ch: Chapter }) {
  const [m, setM] = useState<AgentMetrics | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setM(await fetchAgentMetrics());
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll only while the slide is mounted. The story panel unmounts the previous
  // chapter, so paging away stops the traffic.
  useEffect(() => {
    load();
    const id = window.setInterval(load, POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const t = m?.totals;
  const measured = m?.source === "foundry" && !!t?.runs;

  return (
    <div className="slide slide-telemetry">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>

      <div className="tel-toolbar">
        <span className={`tel-status${measured ? " on" : ""}`}>
          <span className="tel-status-dot" aria-hidden />
          {measured
            ? `Measured by Foundry · ${t?.runs} traced run${t?.runs === 1 ? "" : "s"}`
            : m?.sourceDetail || "Reading Foundry traces…"}
        </span>
        {measured && m && (
          <span className="tel-asof">
            {m.sourceDetail} · updated {new Date(m.asOf).toLocaleTimeString()}
          </span>
        )}
        {!!m?.pendingRuns && (
          <span className="tel-pending" title="Application Insights ingests spans a minute or two after the run">
            {m.pendingRuns} run{m.pendingRuns === 1 ? "" : "s"} awaiting ingestion
          </span>
        )}
        <button className="btn-ghost tel-refresh" onClick={load} disabled={loading}>
          {loading ? "Reading…" : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="tel-error">Could not read agent telemetry. {error}</div>
      )}

      {m && m.source === "unavailable" && !error && (
        <div className="tel-empty">
          <div className="tel-empty-head">{m.sourceDetail}</div>
          {m.sourceError && <div className="tel-empty-sub">{m.sourceError}</div>}
          <div className="tel-empty-sub">
            Nothing is shown here unless Foundry has traced it. This slide never
            estimates a run it cannot see.
          </div>
        </div>
      )}

      {measured && t && m && (
        <>
          <div className="metric-grid tel-metrics">
            <div className="metric tone-neutral">
              <div className="metric-label">Tokens consumed</div>
              <div className="metric-value">{fmtTokens(t.totalTokens)}</div>
              <div className="metric-sub">
                {fmtTokens(t.inputTokens)} prompt · {fmtTokens(t.outputTokens)} completion
              </div>
            </div>
            <div className="metric tone-neutral">
              <div className="metric-label">Token cost</div>
              <div className="metric-value">{fmtMoney(t.cost, m.currency)}</div>
              <div className="metric-sub">
                {fmtMoney(t.costPerRun, m.currency)} per question · estimated
              </div>
            </div>
            <div className="metric tone-good">
              <div className="metric-label">Questions answered</div>
              <div className="metric-value">{t.okRuns} / {t.runs}</div>
              <div className="metric-sub">
                {t.successPct}% success · {t.failedRuns} failed
              </div>
            </div>
            <div className="metric tone-neutral">
              <div className="metric-label">Tokens per question</div>
              <div className="metric-value">{fmtTokens(t.tokensPerRun)}</div>
              <div className="metric-sub">{t.avgToolCalls} grounding calls on average</div>
            </div>
            <div className="metric tone-warn">
              <div className="metric-label">Latency</div>
              <div className="metric-value">{fmtSeconds(t.avgLatencyMs)}</div>
              <div className="metric-sub">p95 {fmtSeconds(t.p95LatencyMs)}</div>
            </div>
            <div className="metric tone-neutral">
              <div className="metric-label">Model</div>
              <div className="metric-value tel-model">{m.model || "—"}</div>
              <div className="metric-sub">last {m.windowDays} days of traces</div>
            </div>
            {m.billed?.available && (
              <div className="metric tone-bad">
                <div className="metric-label">Azure bill</div>
                <div className="metric-value">
                  {fmtMoney(m.billed.total, m.billed.currency)}
                </div>
                <div className="metric-sub">
                  {m.billed.fixedPct}% provisioned · {m.billed.windowDays}-day actual
                </div>
              </div>
            )}
          </div>

          <div className="tel-charts">
            <TokenColumns m={m} />
            <CostArea m={m} />
          </div>

          <LayerSplit m={m} />
          <RecentRuns m={m} />

          {m.billed && (
            <BilledCostPanel b={m.billed} allIn={m.allIn} tokenCost={t.cost} />
          )}

          <div className="tel-pricing">
            <strong>Measured</strong> from the Foundry project's gen-AI traces
            (Application Insights): tokens, latency, success and the grounding
            calls behind each run. <strong>Billed</strong> cost comes from Azure
            Cost Management — actual charges, not a projection.{" "}
            <strong>Derived</strong>: the per-question token estimate, at{" "}
            {m.currency} {m.pricing.inputPer1k.toFixed(5)} per 1k prompt and{" "}
            {m.currency} {m.pricing.outputPer1k.toFixed(5)} per 1k completion
            tokens ({m.pricing.basis}) — set{" "}
            <code>TOKEN_PRICE_INPUT_PER_1K</code> /{" "}
            <code>TOKEN_PRICE_OUTPUT_PER_1K</code> to your negotiated rates.
          </div>
        </>
      )}

      {!m && !error && <div className="tel-loading">Reading Foundry traces…</div>}

      {ch.points?.length ? (
        <ul className="diagram-notes">
          {ch.points.map((p) => <li key={p}>{p}</li>)}
        </ul>
      ) : null}
      {ch.note && <div className="slide-note tel-note">{ch.note}</div>}
    </div>
  );
}
