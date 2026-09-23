import { useEffect, useMemo, useState } from "react";
import type { IQState } from "../types";
import { DIAGRAMS, stageCount } from "../lib/iqDiagram";
import type { DiagramSpec } from "../lib/iqDiagram";

/**
 * Per-layer architecture diagram for the four single-IQ story slides.
 *
 * Replaces the summary IQ card on those slides: the card said *that* a layer was
 * engaged, this says *what it is made of* — the sources it reaches, the thing in
 * the middle that governs them, and what comes out the other side.
 *
 * Two things are deliberate.
 *
 * **The stream is real, not decorative.** The connectors advance through the
 * diagram's stages on a loop so the shape reads as a flow rather than a static
 * org chart, but the loop's speed and intensity are bound to `iq.status`, which
 * comes from the agent's actual tool calls. Idle drifts, active surges, done
 * settles with every column lit. A presenter can therefore point at the diagram
 * and say "that is happening now" without it being theatre.
 *
 * **Connectors flow as dashes, not as travelling dots.** The bracket that splits
 * the core into a stack of outcomes has to stretch to whatever height the boxes
 * end up, so its SVG scales non-uniformly. A dot positioned along such a path
 * would drift; an animated `stroke-dashoffset` on the path itself cannot, and
 * `vector-effect: non-scaling-stroke` keeps the line weight honest.
 */

const STAGE_MS: Record<string, number> = {
  idle: 2800,
  active: 1300,
  done: 3600,
};

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

function LayerIcon({ id }: { id: string }) {
  const common = {
    width: 22, height: 22, viewBox: "0 0 24 24", fill: "none",
    stroke: "currentColor", strokeWidth: 1.7,
    strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
  };
  if (id === "work") {
    return (
      <svg {...common} aria-hidden>
        <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
        <path d="M3 7l9 6 9-6" />
      </svg>
    );
  }
  if (id === "fabric") {
    return (
      <svg {...common} aria-hidden>
        <ellipse cx="12" cy="6" rx="8" ry="3" />
        <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
        <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </svg>
    );
  }
  if (id === "foundry") {
    return (
      <svg {...common} aria-hidden>
        <path d="M12 2.5l8 3v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10v-6z" />
        <path d="M8.5 12l2.5 2.5 4.5-5" />
      </svg>
    );
  }
  return (
    <svg {...common} aria-hidden>
      <rect x="9" y="2.5" width="6" height="5" rx="1.2" />
      <rect x="2.5" y="16.5" width="6" height="5" rx="1.2" />
      <rect x="15.5" y="16.5" width="6" height="5" rx="1.2" />
      <path d="M12 7.5v4.5M5.5 16.5V12h13v4.5" />
    </svg>
  );
}

function ShieldGlyph() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
         strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2.5l8 3v6c0 5-3.4 8.7-8 10-4.6-1.3-8-5-8-10v-6z" />
    </svg>
  );
}

/**
 * One animated connector. `targets` is how many boxes the stream fans out to,
 * which turns the straight line into a bracket.
 */
function Stream({ targets, live, lit }: {
  targets: number; live: boolean; lit: boolean;
}) {
  const paths: string[] = [];
  if (targets <= 1) {
    paths.push("M 0 50 H 100");
  } else {
    const ys = Array.from({ length: targets }, (_, i) => ((i + 0.5) / targets) * 100);
    paths.push("M 0 50 H 42");
    paths.push(`M 42 ${ys[0]} V ${ys[ys.length - 1]}`);
    for (const y of ys) paths.push(`M 42 ${y} H 100`);
  }

  const cls = ["iqd-stream", live ? "is-live" : "", lit ? "is-lit" : ""]
    .filter(Boolean).join(" ");

  return (
    <div className={cls} aria-hidden>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="iqd-stream-svg">
        {paths.map((d, i) => (
          <path key={`base-${i}`} d={d} className="iqd-stream-base" vectorEffect="non-scaling-stroke" />
        ))}
        {paths.map((d, i) => (
          <path key={`flow-${i}`} d={d} className="iqd-stream-flow" vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
    </div>
  );
}

function Column({ lit, className, children }: {
  lit: boolean; className: string; children: React.ReactNode;
}) {
  return (
    <div className={`${className}${lit ? " is-lit" : ""}`}>{children}</div>
  );
}

export function IQDiagram({ iq }: { iq: IQState }) {
  const spec: DiagramSpec | undefined = DIAGRAMS[iq.id];
  const reduced = useMemo(prefersReducedMotion, []);
  const stages = spec ? stageCount(spec) : 0;
  const [stage, setStage] = useState(0);

  /* One timer, restarted whenever the layer's live status changes so the stream
     immediately takes on the new tempo instead of finishing the old beat. */
  useEffect(() => {
    if (reduced || stages === 0) return;
    const ms = STAGE_MS[iq.status] ?? STAGE_MS.idle;
    const t = window.setInterval(() => {
      setStage((s) => (s + 1) % stages);
    }, ms);
    return () => window.clearInterval(t);
  }, [reduced, stages, iq.status]);

  if (!spec) return null;

  /* Reduced motion and the settled "done" state both show the whole diagram at
     once: there is no animation to carry the eye, so nothing should be dimmed. */
  const showAll = reduced || iq.status === "done";
  const active = showAll ? stages - 1 : stage;
  const litTo = (col: number) => showAll || col <= active;

  const badge = iq.status === "active" ? "Streaming"
    : iq.status === "done" ? "Used in this answer"
    : "Standing by";

  const hasOutcomes = Boolean(spec.outcomes);
  const hasAgents = Boolean(spec.agents);
  const outcomeStage = 1;
  const agentStage = hasOutcomes ? 2 : 1;

  return (
    <section className={`iqd iqd-${spec.id} status-${iq.status}`}
             aria-label={`${spec.title} architecture`}>
      <header className="iqd-head">
        <span className="iqd-head-icon"><LayerIcon id={spec.id} /></span>
        <div className="iqd-head-text">
          <h3 className="iqd-title">{spec.title}</h3>
          <p className="iqd-subtitle">{spec.subtitle}</p>
        </div>
        <span className={`iqd-badge badge-${iq.status}`}>
          {iq.status === "active" && <span className="iqd-badge-dot" aria-hidden />}
          {badge}
        </span>
      </header>

      <div className="iqd-board">
        <Column className="iqd-col iqd-sources" lit={litTo(0)}>
          <div className="iqd-col-label">{spec.sources.label}</div>
          {spec.sources.lede && <p className="iqd-col-lede">{spec.sources.lede}</p>}
          <div className="iqd-tiles">
            {spec.sources.tiles.map((t) => (
              <div className="iqd-tile" key={t}>{t}</div>
            ))}
            {spec.sources.wideTiles?.map((t) => (
              <div className="iqd-tile iqd-tile-wide" key={t}>{t}</div>
            ))}
          </div>
          {spec.sources.foot && <div className="iqd-col-foot">{spec.sources.foot}</div>}
        </Column>

        <Stream targets={1} live={!showAll && active === 0} lit={litTo(0)} />

        <Column className="iqd-col iqd-core" lit={litTo(0)}>
          <div className="iqd-core-head">
            <span className="iqd-core-icon"><LayerIcon id={spec.id} /></span>
            <div>
              <div className="iqd-core-title">{spec.core.title}</div>
              <div className="iqd-core-detail">{spec.core.detail}</div>
            </div>
          </div>
          {spec.core.notes?.length ? (
            <div className="iqd-notes">
              {spec.core.notes.map((n) => (
                <div className="iqd-note" key={n}>{n}</div>
              ))}
            </div>
          ) : null}
          {spec.core.cards?.length ? (
            <div className="iqd-cards">
              {spec.core.cards.map((c) => (
                <div className={`iqd-card${c.wide ? " iqd-card-wide" : ""}`} key={c.title}>
                  <div className="iqd-card-title">{c.title}</div>
                  <div className="iqd-card-detail">{c.detail}</div>
                </div>
              ))}
            </div>
          ) : null}
        </Column>

        {hasOutcomes && (
          <>
            <Stream
              targets={spec.outcomes!.items.length}
              live={!showAll && active === outcomeStage}
              lit={litTo(outcomeStage)}
            />
            <Column className="iqd-col iqd-outcomes" lit={litTo(outcomeStage)}>
              <div className="iqd-outcome-stack">
                {spec.outcomes!.items.map((o) => (
                  <div className="iqd-outcome" key={o.title}>
                    <div className="iqd-outcome-title">{o.title}</div>
                    <div className="iqd-outcome-detail">{o.detail}</div>
                  </div>
                ))}
              </div>
              {spec.outcomes!.foot && (
                <div className="iqd-col-foot iqd-foot-accent">{spec.outcomes!.foot}</div>
              )}
            </Column>
          </>
        )}

        {hasAgents && (
          <>
            <Stream targets={1} live={!showAll && active === agentStage} lit={litTo(agentStage)} />
            <Column className="iqd-col iqd-agents" lit={litTo(agentStage)}>
              <span className="iqd-agents-icon"><LayerIcon id={spec.id} /></span>
              <div className="iqd-agents-title">{spec.agents!.title}</div>
              <div className="iqd-agents-detail">{spec.agents!.detail}</div>
              {spec.agents!.foot && (
                <div className="iqd-col-foot iqd-foot-accent">{spec.agents!.foot}</div>
              )}
              {spec.agents!.items && (
                <div className="iqd-agents-items">{spec.agents!.items}</div>
              )}
            </Column>
          </>
        )}
      </div>

      <p className="iqd-caption" aria-live="polite">
        <span className="iqd-caption-step">
          {String(active + 1).padStart(2, "0")}/{String(stages).padStart(2, "0")}
        </span>
        {spec.stages[active] ?? spec.stages[spec.stages.length - 1]}
      </p>

      <footer className="iqd-assurances">
        <span className="iqd-assurance-glyph"><ShieldGlyph /></span>
        {spec.assurances.map((a) => (
          <span className="iqd-assurance" key={a}>{a}</span>
        ))}
      </footer>
    </section>
  );
}
