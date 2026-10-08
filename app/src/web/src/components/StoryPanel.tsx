import { useEffect, useState } from "react";
import { FlowScene } from "./FlowScene";
import { PlainPanel } from "./PlainPanel";
import type { Chapter, Persona, Story } from "../types";
import { IQPanel } from "./IQPanel";
import { IQDiagram } from "./IQDiagram";
import { Markdown } from "./Markdown";
import { TelemetrySlide } from "./TelemetrySlide";
import { DIAGRAMS } from "../lib/iqDiagram";
import { fetchWebPulse, apiPost } from "../api";
import type { IQState, LayerTable, ProFormaResult, WebPulse } from "../types";
import { SkillModal, useSkillCatalogue } from "./SkillBar";
import { ProFormaSkill } from "./skills/ProFormaSkill";
import { PapersSkill } from "./skills/PapersSkill";

interface Props {
  story: Story;
  persona: Persona;
  index: number;
  iqs: IQState[];
  busy: boolean;
  onPrev: () => void;
  onNext: () => void;
  onRunPrompt: (prompt: string) => void;
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).map((p) => p[0]).slice(0, 2).join("");
}

function PersonaSlide({ persona, ch }: { persona: Persona; ch: Chapter }) {
  const points = persona.points ?? ch.points ?? [];
  return (
    <div className="slide slide-persona">
      <div className="persona-card">
        <div className="persona-top">
          <div>
            <div className="persona-org">{persona.org}</div>
            <div className="persona-role">{persona.title}</div>
            <h2 className="persona-name">{persona.name}</h2>
          </div>
          <div className="persona-avatar" aria-hidden>{initials(persona.name)}</div>
        </div>
        <div className="persona-goal">{persona.goal}</div>
      </div>
      <div className="persona-body">
        <div className="slide-eyebrow">{ch.kicker}</div>
        <p className="slide-lede">{ch.body}</p>
        <ol className="persona-objectives">
          {persona.objectives.map((o, i) => (
            <li key={i}>
              <span className="obj-num">{String(i + 1).padStart(2, "0")}</span>
              <span>{o}</span>
            </li>
          ))}
        </ol>
        {points.length ? (
          <div className="persona-points">
            {points.map((p) => (
              <div className="point" key={p}>{p}</div>
            ))}
          </div>
        ) : null}
        {ch.plain && <PlainPanel plain={ch.plain} />}
      </div>
    </div>
  );
}

function ArchitectureSlide({ ch }: { ch: Chapter }) {
  return (
    <div className="slide slide-arch">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>
      <div className="arch-grid">
        {ch.columns?.map((col, i) => (
          <div className={`arch-col arch-col-${i}`} key={col.title}>
            <div className="arch-tag">{col.tag}</div>
            <div className="arch-col-title">{col.title}</div>
            {col.items.map((it) => (
              <div className="arch-item" key={it.name}>
                <div className="arch-item-name">{it.name}</div>
                <div className="arch-item-detail">{it.detail}</div>
              </div>
            ))}
          </div>
        ))}
      </div>
      {ch.assurances?.length ? (
        <div className="arch-assurances">
          {ch.assurances.map((a) => (
            <span className="assurance" key={a}>✓ {a}</span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The metrics board.
 *
 * Its job is to let the audience form a conclusion before the reveal slide takes
 * it away. Every tile here is deliberately green, because the point of the demo
 * is that six correct green indicators can still add up to the wrong answer.
 */
function MetricsSlide({ ch }: { ch: Chapter }) {
  return (
    <div className="slide slide-metrics">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>

      <div className="metric-grid">
        {ch.metrics?.map((m) => (
          <div className={`metric tone-${m.tone ?? "neutral"}`} key={m.label}>
            <div className="metric-label">{m.label}</div>
            <div className="metric-value">{m.value}</div>
            {m.sub && <div className="metric-sub">{m.sub}</div>}
          </div>
        ))}
      </div>

      {ch.note && <div className="slide-note metric-note">{ch.note}</div>}
      {ch.plain && <PlainPanel plain={ch.plain} />}
    </div>
  );
}

/**
 * The reveal.
 *
 * Two columns side by side: the reasonable conclusion, then what actually binds.
 * Used twice - once to spring the country-limit trap, and once at the end to
 * contrast a search tool with a grounded agent.
 */
function RevealSlide({ ch }: { ch: Chapter }) {
  return (
    <div className="slide slide-reveal">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>

      <div className="reveal-grid">
        <div className="reveal-col reveal-wrong">
          <div className="reveal-head">{ch.wrong?.head}</div>
          <ul>
            {ch.wrong?.lines.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </div>
        <div className="reveal-vs" aria-hidden>vs</div>
        <div className="reveal-col reveal-right">
          <div className="reveal-head">{ch.right?.head}</div>
          <ul>
            {ch.right?.lines.map((l) => <li key={l}>{l}</li>)}
          </ul>
        </div>
      </div>

      {ch.note && <div className="slide-note reveal-note">{ch.note}</div>}
      {ch.plain && <PlainPanel plain={ch.plain} />}
    </div>
  );
}

/**
 * DiagramSlide - a slide whose main content is the animated flow scene.
 *
 * Rendered right after the "four columns" architecture slide. The columns
 * chapter frames WHAT the four sources are; this one shows HOW they connect
 * through the app and the Foundry agent, all under the signed-in user's
 * identity.
 *
 * The sequence is drawn and scrubbable rather than filmed: an MP4 would need
 * hosting, a rebuild to re-cut, and would soften on a 4K presenter screen. It
 * also lets a presenter stop on the on-behalf-of step, which is the one people
 * ask about.
 */
function DiagramSlide({ ch }: { ch: Chapter }) {
  return (
    <div className="slide slide-diagram">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>

      <FlowScene />

      {ch.points?.length ? (
        <ul className="diagram-notes">
          {ch.points.map((p) => <li key={p}>{p}</li>)}
        </ul>
      ) : null}
      {ch.note && <div className="slide-note reveal-note">{ch.note}</div>}
    </div>
  );
}

/** The Web IQ row is fetched live rather than authored, so it never goes stale. */
function LiveWebCell({ fallback }: { fallback: string }) {
  const [pulse, setPulse] = useState<WebPulse | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchWebPulse().then((p) => { if (alive) setPulse(p); });
    return () => { alive = false; };
  }, []);

  const refresh = () => {
    setRefreshing(true);
    fetchWebPulse(true).then((p) => { setPulse(p); setRefreshing(false); });
  };

  if (!pulse || refreshing) {
    return (
      <div className="web-live" aria-busy="true">
        <span className="web-live-tag pending">Fetching live from the web…</span>
        <div className="skel skel-line w90" />
        <div className="skel skel-line w75" />
        <div className="skel skel-line w60" />
      </div>
    );
  }
  if (pulse.status !== "live" || !pulse.text) {
    return (
      <div className="web-live">
        <span className="web-live-tag off">Live web unavailable</span>
        <p className="web-live-fallback">{fallback}</p>
      </div>
    );
  }
  const when = pulse.fetchedAt
    ? new Date(pulse.fetchedAt).toLocaleString(undefined, {
      dateStyle: "medium", timeStyle: "short",
    })
    : "";
  return (
    <div className="web-live">
      <span className="web-live-tag">
        ● Live · Bing grounding · {when}{pulse.stale ? " · last good answer" : ""}
      </span>
      <div className="web-live-body"><Markdown text={pulse.text} /></div>
      {pulse.citations?.length ? (
        <div className="web-live-sources">
          {pulse.citations.slice(0, 4).map((c, i) => (
            <a key={c.url ?? i} href={c.url} target="_blank" rel="noreferrer">
              {c.title || new URL(c.url ?? "", window.location.href).hostname}
            </a>
          ))}
        </div>
      ) : null}
      <button className="web-live-refresh" onClick={refresh} type="button">Refresh</button>
    </div>
  );
}

function LayerTableView({ table, iqs }: { table: LayerTable; iqs: IQState[] }) {
  const byId = new Map(iqs.map((i) => [i.id, i]));
  const used = iqs.filter((i) => i.status !== "idle").length;
  return (
    <section className="layer-table-wrap">
      <div className="panel-head">
        <h2 className="panel-title">Microsoft intelligence layers</h2>
        <span className="panel-count">{used} of {iqs.length} engaged</span>
      </div>
      <p className="panel-sub">
        The badges light up from the agent's actual tool calls — nothing here is scripted.
      </p>
      <table className="layer-table">
        <thead>
          <tr>{table.headers.map((h) => <th key={h} scope="col">{h}</th>)}</tr>
        </thead>
        <tbody>
          {table.rows.map((r) => {
            const iq = byId.get(r.iq);
            const status = iq?.status ?? "idle";
            return (
              <tr key={r.iq} className={`layer-row iq-${r.iq}`}>
                <th scope="row">
                  <span className="layer-name">{iq?.name ?? r.iq}</span>
                  <span className={`iq-badge badge-${status}`}>
                    {status === "active" ? "ACTIVE" : status === "done" ? "USED" : "IDLE"}
                  </span>
                </th>
                <td>{r.holds}</td>
                <td className="layer-tells">
                  {r.iq === "web" ? <LiveWebCell fallback={r.tells} /> : r.tells}
                </td>
                <td className="layer-cannot">{r.cannot}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}

/**
 * The path to yes.
 *
 * The "no" on its own is where most risk tooling stops. This slide turns it into
 * a sequence: the ask as made, the version that can go into the room, and every
 * gate between them with the person who owns it. The agent prompt asks for the
 * same thing live, so the slide is the expectation and the answer is the proof.
 */
function PathSlide({ ch, busy, onRunPrompt }: {
  ch: Chapter; busy: boolean; onRunPrompt: (p: string) => void;
}) {
  const catalogue = useSkillCatalogue();
  const [open, setOpen] = useState<"proforma" | "papers" | null>(null);
  return (
    <div className="slide slide-path">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>

      <div className="reveal-grid">
        <div className="reveal-col reveal-wrong">
          <div className="reveal-head">{ch.wrong?.head}</div>
          <ul>{ch.wrong?.lines.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
        <div className="reveal-vs" aria-hidden>→</div>
        <div className="reveal-col reveal-right">
          <div className="reveal-head">{ch.right?.head}</div>
          <ul>{ch.right?.lines.map((l) => <li key={l}>{l}</li>)}</ul>
        </div>
      </div>

      {ch.pathSteps?.length ? (
        <table className="path-table">
          <thead>
            <tr><th scope="col">#</th><th scope="col">Gate</th><th scope="col">What clears it</th><th scope="col">Who decides</th></tr>
          </thead>
          <tbody>
            {ch.pathSteps.map((s, i) => (
              <tr key={s.constraint} className={`path-row tone-${s.tone ?? "warn"}`}>
                <td className="path-num">{i + 1}</td>
                <th scope="row">{s.constraint}</th>
                <td>{s.clears}</td>
                <td className="path-owner">{s.owner}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      {ch.note && <div className="slide-note">{ch.note}</div>}

      <div className="path-actions">
        {ch.prompt && (
          <button
            className="run-prompt"
            disabled={busy}
            onClick={() => onRunPrompt(ch.prompt as string)}
          >
            {busy ? "Running…" : "Ask the agent →"}
          </button>
        )}
        {catalogue && (
          <>
            <button className="path-skill" onClick={() => setOpen("proforma")}>Stress-test it</button>
            <button className="path-skill" onClick={() => setOpen("papers")}>Draft the approval papers</button>
          </>
        )}
      </div>

      {catalogue && open === "proforma" && (
        <SkillModal title="CP-005 pro-forma covenant test" onClose={() => setOpen(null)}>
          <ProFormaSkill
            catalogue={catalogue}
            result={null}
            onRun={(incrementalM, ebitdaShockPct) =>
              apiPost<ProFormaResult>("/api/skills/proforma", { incrementalM, ebitdaShockPct })}
          />
        </SkillModal>
      )}
      {catalogue && open === "papers" && (
        <SkillModal title="Approval papers — drafts" onClose={() => setOpen(null)} wide>
          <PapersSkill catalogue={catalogue} />
        </SkillModal>
      )}
    </div>
  );
}

function IQSlide({ ch, iqs, busy, onRunPrompt }: {
  ch: Chapter; iqs: IQState[]; busy: boolean; onRunPrompt: (p: string) => void;
}) {
  const focus = ch.iq && ch.iq !== "all"
    ? iqs.filter((i) => i.id === ch.iq)
    : iqs;

  /* A slide about one layer gets that layer's architecture diagram instead of
     the summary card, and drops the "what a good answer contains" checklist:
     the diagram already shows what the layer reaches and what comes out of it,
     so the list underneath was saying the same thing twice. The four-layer
     slide keeps both — four diagrams side by side would be unreadable. */
  const single = focus.length === 1 && focus[0].id in DIAGRAMS ? focus[0] : null;

  return (
    <div className="slide slide-iq">
      <div className="slide-eyebrow">{ch.kicker}</div>
      <h2 className="slide-title">{ch.title}</h2>
      <p className="slide-lede">{ch.body}</p>

      {ch.layerTable ? (
        <LayerTableView table={ch.layerTable} iqs={iqs} />
      ) : single ? <IQDiagram iq={single} /> : <IQPanel iqs={focus} />}

      {!single && !ch.layerTable && ch.expect?.length ? (
        <div className="expect">
          <div className="expect-head">What a good answer contains</div>
          <ul>
            {ch.expect.map((e) => <li key={e}>{e}</li>)}
          </ul>
        </div>
      ) : null}

      {ch.note && <div className="slide-note">{ch.note}</div>}

      {ch.prompt && (
        <button
          className="run-prompt"
          disabled={busy}
          onClick={() => onRunPrompt(ch.prompt as string)}
        >
          {busy ? "Running…" : "Ask the agent →"}
        </button>
      )}
    </div>
  );
}

export function StoryPanel({
  story, persona, index, iqs, busy, onPrev, onNext, onRunPrompt,
}: Props) {
  const ch = story.chapters[index];

  // Arrow keys move between chapters. A guided walkthrough that needs a mouse is
  // painful to present from a lectern.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement;
      if (el && /^(INPUT|TEXTAREA)$/.test(el.tagName)) return;
      if (e.key === "ArrowLeft") onPrev();
      if (e.key === "ArrowRight") onNext();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onPrev, onNext]);

  if (!ch) return null;
  const pct = ((index + 1) / story.chapters.length) * 100;

  return (
    <section className="story-panel">
      <div className="story-bar">
        <div className="story-progress" style={{ width: `${pct}%` }} />
        <div className="story-bar-inner">
          <div className="story-meta">
            <span className="story-num">
              {String(index + 1).padStart(2, "0")} · {ch.title}
            </span>
            <span className="story-sub">Guided walkthrough · live agent</span>
          </div>
          <div className="story-dots" role="tablist" aria-label="Chapters">
            {story.chapters.map((c, i) => (
              <span
                key={c.id}
                className={`story-dot${i === index ? " on" : ""}${i < index ? " past" : ""}`}
                title={c.title}
                aria-hidden
              />
            ))}
          </div>
          <div className="story-nav">
            <button onClick={onPrev} disabled={index === 0} aria-label="Previous">←</button>
            <span className="story-count">
              {String(index + 1).padStart(2, "0")} / {String(story.chapters.length).padStart(2, "0")}
            </span>
            <button
              onClick={onNext}
              disabled={index === story.chapters.length - 1}
              aria-label="Next"
            >→</button>
          </div>
        </div>
      </div>

      <div className="story-stage" key={ch.id}>
        {ch.layout === "persona" && <PersonaSlide persona={persona} ch={ch} />}
        {ch.layout === "architecture" && <ArchitectureSlide ch={ch} />}
        {ch.layout === "metrics" && <MetricsSlide ch={ch} />}
        {ch.layout === "reveal" && <RevealSlide ch={ch} />}
        {ch.layout === "diagram" && <DiagramSlide ch={ch} />}
        {ch.layout === "telemetry" && <TelemetrySlide ch={ch} />}
        {ch.layout === "path" && (
          <PathSlide ch={ch} busy={busy} onRunPrompt={onRunPrompt} />
        )}
        {ch.layout === "iq" && (
          <IQSlide ch={ch} iqs={iqs} busy={busy} onRunPrompt={onRunPrompt} />
        )}
      </div>
    </section>
  );
}
