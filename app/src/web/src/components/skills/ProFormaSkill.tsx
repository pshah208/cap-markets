/**
 * CP-005 pro-forma covenant test.
 *
 * The interactive one. Drag the incremental commitment and watch Total Net Debt
 * / Adjusted EBITDA move against the 4.50x maximum, plotted on the client's own
 * eight-quarter history.
 *
 * The arithmetic is NOT done here. CP-005 makes the pro-forma a control that has
 * to be able to come back "no", and says coverage "may not perform it, waive it,
 * or pre-empt it" - so the number comes from the BFF and this component only
 * draws it. The slider is a request, not a calculator.
 */

import { useEffect, useState } from "react";
import type { ProFormaResult, SkillCatalogue } from "../../types";

const W = 640;
const H = 210;
const PAD = { l: 44, r: 92, t: 16, b: 26 };

export function ProFormaSkill({ catalogue, result, onRun }: {
  catalogue: SkillCatalogue;
  result: ProFormaResult | null;
  onRun: (incrementalM: number) => Promise<ProFormaResult>;
}) {
  const rev = catalogue.opportunities.revolver_upsize as Record<string, number>;
  const proposed = Number(rev?.proposed_commitment_total_m ?? 0)
    - Number(rev?.current_commitment_total_m ?? 0);

  const [inc, setInc] = useState<number>(proposed || 250);
  const [res, setRes] = useState<ProFormaResult | null>(result);
  const [busy, setBusy] = useState(false);

  // Debounced so dragging the slider does not fire a request per pixel.
  useEffect(() => {
    let alive = true;
    setBusy(true);
    const t = setTimeout(() => {
      onRun(inc)
        .then((r) => { if (alive) setRes(r); })
        .catch(() => { /* leave the last good result on screen */ })
        .finally(() => { if (alive) setBusy(false); });
    }, 180);
    return () => { alive = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inc]);

  const hist = catalogue.leverage_history;
  const threshold = catalogue.covenant.threshold;
  const pf = res?.pro_forma_leverage ?? catalogue.covenant.actual;

  const values = [...hist.map((h) => h.leverage), threshold, pf];
  const lo = Math.min(...values) - 0.15;
  const hi = Math.max(...values) + 0.15;
  const plotW = W - PAD.l - PAD.r;
  const plotH = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (plotW * i) / hist.length;
  const y = (v: number) => PAD.t + plotH - ((v - lo) / (hi - lo)) * plotH;

  const line = hist.map((h, i) => `${i ? "L" : "M"} ${x(i)} ${y(h.leverage)}`).join(" ");
  const lastX = x(hist.length - 1);
  const pfX = x(hist.length);

  return (
    <div className="pf">
      <p className="pf-lede">
        Total Net Debt / Adjusted EBITDA, tested <strong>fully drawn</strong> as
        CP-005 requires. Adjusted EBITDA {catalogue.financials.adjusted_ebitda_ltm_m.toFixed(1)}m
        and net debt {catalogue.financials.total_net_debt_m.toFixed(1)}m as at{" "}
        {catalogue.financials.as_of}.
      </p>

      <svg viewBox={`0 0 ${W} ${H}`} className="pf-chart" role="img"
           aria-label="Leverage history and pro-forma result">
        {/* covenant ceiling */}
        <line x1={PAD.l} x2={W - PAD.r} y1={y(threshold)} y2={y(threshold)}
              className="pf-threshold" />
        <text x={W - PAD.r + 8} y={y(threshold) + 4} className="pf-threshold-label">
          {threshold.toFixed(2)}x max
        </text>

        {/* the breach zone, so "above the line" reads instantly */}
        <rect x={PAD.l} y={PAD.t} width={plotW} height={Math.max(0, y(threshold) - PAD.t)}
              className="pf-breach-zone" />

        <path d={line} className="pf-line" />
        {hist.map((h, i) => (
          <circle key={h.as_of} cx={x(i)} cy={y(h.leverage)} r={3} className="pf-dot">
            <title>{`${h.as_of}  ${h.leverage.toFixed(2)}x  ${h.rating}`}</title>
          </circle>
        ))}

        {/* the pro-forma point, connected to today by a dashed projection */}
        <line x1={lastX} x2={pfX} y1={y(hist[hist.length - 1].leverage)} y2={y(pf)}
              className="pf-projection" />
        <circle cx={pfX} cy={y(pf)} r={6}
                className={`pf-point tone-${res?.tone ?? "warn"}`} />
        <text x={pfX + 12} y={y(pf) + 4}
              className={`pf-point-label tone-${res?.tone ?? "warn"}`}>
          {pf.toFixed(2)}x
        </text>

        <text x={PAD.l} y={H - 6} className="pf-axis">{hist[0]?.as_of}</text>
        <text x={lastX} y={H - 6} className="pf-axis" textAnchor="middle">today</text>
        <text x={pfX} y={H - 6} className="pf-axis" textAnchor="end">pro-forma</text>
      </svg>

      <label className="pf-slider-row">
        <span className="pf-slider-label">
          Incremental committed capacity
          <em>client level, not our hold</em>
        </span>
        <input
          type="range"
          min={0}
          max={400}
          step={5}
          value={inc}
          onChange={(e) => setInc(Number(e.target.value))}
          className="pf-slider"
          aria-label="Incremental committed capacity in CAD millions"
        />
        <span className="pf-slider-value">CAD {inc}m</span>
      </label>

      <div className="pf-presets">
        <button onClick={() => setInc(proposed)}>As proposed · {proposed}m</button>
        {res && (
          <button onClick={() => setInc(Math.floor(res.max_clearing_m))}>
            Largest that clears · {Math.floor(res.max_clearing_m)}m
          </button>
        )}
        <button onClick={() => setInc(0)}>No change</button>
      </div>

      {res && (
        <div className={`pf-verdict tone-${res.tone}${busy ? " busy" : ""}`}>
          <div className="pf-verdict-head">
            <span className="pf-badge">{res.clears ? "CLEARS" : "DOES NOT CLEAR"}</span>
            <span className="pf-band">{res.band}</span>
          </div>
          <div className="pf-figures">
            <div><b>{res.current_leverage.toFixed(2)}x</b><span>today</span></div>
            <div><b>{res.pro_forma_leverage.toFixed(2)}x</b><span>pro-forma</span></div>
            <div>
              <b>{res.headroom_turns >= 0 ? "+" : ""}{res.headroom_turns.toFixed(2)}</b>
              <span>turns headroom</span>
            </div>
            <div><b>{res.pro_forma_net_debt_m.toFixed(1)}</b><span>pro-forma net debt</span></div>
          </div>
          <p className="pf-statement">{res.verdict}</p>
        </div>
      )}

      <p className="pf-foot">
        Owned by the sector Credit Risk director. Coverage may request this test;
        coverage may not perform, waive or pre-empt it (CP-005). Figures are
        confidential under CP-014 and are not disclosable to the client.
      </p>
    </div>
  );
}
