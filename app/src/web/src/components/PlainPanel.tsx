/**
 * The "in plain English" panel.
 *
 * The first three chapters carry the whole setup, and all three assume the
 * reader already knows what a revolver, a covenant and a bookrunner are. For a
 * non-finance audience that is three slides of nodding along, and the trap in
 * chapter 03 lands on nobody.
 *
 * This fills the space under those slides with the same story told without
 * jargon. It is driven entirely from `story.json`, so the wording can be
 * re-cut for a different audience without touching code.
 *
 * One renderer, three shapes:
 *   cards   - a row of explained things (the three asks, the three numbers)
 *   gauges  - two bars side by side, for "these two limits are not the same"
 *   punch   - the single line to say out loud before moving on
 */

import type { PlainEnglish } from "../types";

export function PlainPanel({ plain }: { plain: PlainEnglish }) {
  return (
    <section className="plain" aria-label={plain.heading}>
      <div className="plain-head">
        <span className="plain-tag">{plain.heading}</span>
        {plain.lead && <p className="plain-lead">{plain.lead}</p>}
      </div>

      {plain.cards?.length ? (
        <div className={`plain-cards cols-${Math.min(plain.cards.length, 3)}`}>
          {plain.cards.map((c) => (
            <div className="plain-card" key={c.title}>
              <div className="plain-card-top">
                <span className="plain-icon" aria-hidden>{c.icon}</span>
                <span className="plain-card-title">{c.title}</span>
              </div>
              {c.sub && <div className="plain-card-sub">{c.sub}</div>}
              <p className="plain-card-body">{c.body}</p>
            </div>
          ))}
        </div>
      ) : null}

      {plain.gauges?.length ? (
        <div className="plain-gauges">
          {plain.gauges.map((g) => (
            <div className={`plain-gauge tone-${g.tone}`} key={g.label}>
              <div className="plain-gauge-head">
                <span className="plain-gauge-label">{g.label}</span>
                <span className="plain-gauge-value">{g.value}</span>
              </div>
              {g.sub && <div className="plain-gauge-sub">{g.sub}</div>}
              <div className="plain-gauge-track">
                <div
                  className="plain-gauge-fill"
                  style={{ width: `${Math.max(0, Math.min(100, g.pct))}%` }}
                />
                <span className="plain-gauge-pct">{g.pct}%</span>
              </div>
              <div className="plain-gauge-caption">{g.caption}</div>
            </div>
          ))}
        </div>
      ) : null}

      {plain.punch && <div className="plain-punch">{plain.punch}</div>}
    </section>
  );
}
