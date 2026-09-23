/**
 * Portfolio covenant radar.
 *
 * The demo's trap is about one client. The question an executive asks straight
 * afterwards is "how many more of these are there?" - and the dataset already
 * answers it: the same leverage covenant is tracked for all ten names, and
 * Gibson is only the *third* tightest. Stella-Jones sits at 99.0% utilised with
 * 0.04 turns of headroom.
 *
 * What makes Gibson the one to worry about is not the level but the direction:
 * it is the only name in the book moving the wrong way. The arrow column is
 * therefore the point of the chart, not decoration.
 */

import type { RadarEntry } from "../../types";

export function RadarSkill({ radar }: {
  radar: { as_of: string; entries: RadarEntry[]; tight_count: number; hero_id: string; note: string };
}) {
  const max = Math.max(...radar.entries.map((e) => e.utilisation_pct), 100);

  return (
    <div className="radar">
      <p className="radar-lede">{radar.note}</p>

      <div className="radar-rows">
        {radar.entries.map((e) => {
          const isHero = e.client_id === radar.hero_id;
          return (
            <div key={e.client_id} className={`radar-row${isHero ? " is-hero" : ""}`}>
              <div className="radar-name">
                {e.client}
                {isHero && <span className="radar-hero-tag">this answer</span>}
              </div>

              <div className="radar-track">
                {/* The CP-005 "Tight" band starts where headroom < 0.35 turns.
                    Drawn as a zone so the threshold is visible, not implied. */}
                <div
                  className="radar-tight-zone"
                  style={{ left: `${(1 - 0.35 / e.threshold) * 100 * (100 / max)}%` }}
                />
                <div
                  className={`radar-fill tone-${e.tone}`}
                  style={{ width: `${(e.utilisation_pct / max) * 100}%` }}
                />
                <span className="radar-value">
                  {e.actual.toFixed(2)}x <em>/ {e.threshold.toFixed(2)}x</em>
                </span>
              </div>

              <div className="radar-headroom">
                {e.headroom.toFixed(2)}<em>turns</em>
              </div>

              <div className={`radar-move ${e.deteriorating ? "worse" : "better"}`}
                   title={`was ${e.prior.toFixed(2)}x last quarter`}>
                {e.moved === 0
                  ? <span className="radar-flat">flat</span>
                  : <>{e.deteriorating ? "▲" : "▼"} {Math.abs(e.moved).toFixed(2)}</>}
              </div>

              <span className={`radar-status tone-${e.tone}`}>{e.status}</span>
            </div>
          );
        })}
      </div>

      <p className="radar-foot">
        Total Net Debt / Adjusted EBITDA, as at {radar.as_of}. Sorted by
        utilisation of the covenant, not by exposure — the largest name is not
        the tightest one. Confidential under CP-014.
      </p>
    </div>
  );
}
