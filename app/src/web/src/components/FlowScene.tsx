import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  EDGES, NODES, SCENES, SCENE_STARTS, TOTAL_MS, VIEWBOX, sceneAt,
} from "../lib/flowScene";

/** Dots rendered per frame; the busiest scene moves four packets at once. */
const MAX_PACKETS = 4;

function clamp01(v: number): number {
  return v < 0 ? 0 : v > 1 ? 1 : v;
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/**
 * The four-IQ flow, rendered as a scrubbable animated scene rather than a video
 * file.
 *
 * Everything is driven from a single elapsed-time value held in a ref and
 * advanced by requestAnimationFrame. Packet positions and edge trails are
 * written straight to the DOM each frame; React state only changes when the
 * scene does, which keeps a 60fps animation from re-rendering the slide.
 *
 * Because time is the only input, pausing, seeking and scrubbing are the same
 * operation — set `t` and draw. A pre-rendered MP4 would need hosting, a
 * rebuild to re-cut, and would blur on a 4K presenter screen; this stays sharp
 * and edits as data in `lib/flowScene.ts`.
 */
export function FlowScene() {
  const reduced = useMemo(prefersReducedMotion, []);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [playing, setPlaying] = useState(!reduced);

  const tRef = useRef(0);
  const sceneRef = useRef(0);
  const playingRef = useRef(playing);
  const lastRef = useRef(0);

  const pathRefs = useRef<Record<string, SVGPathElement | null>>({});
  const trailRefs = useRef<Record<string, SVGPathElement | null>>({});
  const packetRefs = useRef<(SVGGElement | null)[]>([]);
  const rangeRef = useRef<HTMLInputElement>(null);
  const barRef = useRef<HTMLDivElement>(null);

  playingRef.current = playing;

  const draw = useCallback((t: number) => {
    const i = sceneAt(t);
    if (i !== sceneRef.current) {
      sceneRef.current = i;
      setSceneIndex(i);
    }

    const scene = SCENES[i];
    const p = clamp01((t - SCENE_STARTS[i]) / scene.ms);

    let packet = 0;
    const lit = new Set<string>();

    for (const flow of scene.flows) {
      const path = pathRefs.current[flow.edge];
      if (!path) continue;

      const start = flow.from ?? 0;
      const end = flow.to ?? 1;
      const span = Math.max(end - start, 0.0001);
      const q = clamp01((p - start) / span);

      const len = path.getTotalLength();
      const along = flow.reverse ? 1 - q : q;
      const pt = path.getPointAtLength(len * along);

      const trail = trailRefs.current[flow.edge];
      if (trail) {
        trail.style.opacity = q > 0 && q < 1 ? "1" : q >= 1 ? "0.55" : "0";
        trail.style.strokeDasharray = `${len}`;
        trail.style.strokeDashoffset = `${(flow.reverse ? -1 : 1) * len * (1 - q)}`;
      }
      lit.add(flow.edge);

      const el = packetRefs.current[packet];
      if (el) {
        el.style.opacity = q > 0 && q < 1 ? "1" : "0";
        el.setAttribute("transform", `translate(${pt.x} ${pt.y})`);
        el.dataset.tone = flow.tone ?? "app";
      }
      packet += 1;
      if (packet >= MAX_PACKETS) break;
    }

    for (let k = packet; k < MAX_PACKETS; k += 1) {
      const el = packetRefs.current[k];
      if (el) el.style.opacity = "0";
    }
    for (const edge of EDGES) {
      if (lit.has(edge.id)) continue;
      const trail = trailRefs.current[edge.id];
      if (trail) trail.style.opacity = "0";
    }

    const pct = (t / TOTAL_MS) * 100;
    if (barRef.current) barRef.current.style.width = `${pct}%`;
    if (rangeRef.current && document.activeElement !== rangeRef.current) {
      rangeRef.current.value = String(Math.round(t));
    }
  }, []);

  useEffect(() => {
    let frame = 0;
    lastRef.current = performance.now();

    const tick = (now: number) => {
      const dt = now - lastRef.current;
      lastRef.current = now;
      if (playingRef.current) {
        tRef.current = (tRef.current + dt) % TOTAL_MS;
      }
      draw(tRef.current);
      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [draw]);

  const seek = useCallback((t: number) => {
    tRef.current = Math.max(0, Math.min(TOTAL_MS - 1, t));
    draw(tRef.current);
  }, [draw]);

  const step = useCallback((delta: number) => {
    const next = sceneRef.current + delta;
    if (next < 0 || next >= SCENES.length) return;
    seek(SCENE_STARTS[next]);
  }, [seek]);

  const scene = SCENES[sceneIndex];
  const active = useMemo(() => new Set(scene.nodes), [scene]);
  const visited = useMemo(() => {
    const s = new Set<string>();
    for (let i = 0; i <= sceneIndex; i += 1) {
      for (const n of SCENES[i].nodes) s.add(n);
    }
    return s;
  }, [sceneIndex]);

  return (
    <div className="flow">
      <div className="flow-stage">
        <svg
          viewBox={`0 0 ${VIEWBOX.w} ${VIEWBOX.h}`}
          className="flow-svg"
          role="img"
          aria-label={`Data flow diagram, step ${sceneIndex + 1} of ${SCENES.length}: ${scene.label}`}
        >
          <g className="flow-edges">
            {EDGES.map((e) => (
              <path
                key={e.id}
                d={e.d}
                className="flow-edge"
                ref={(el) => { pathRefs.current[e.id] = el; }}
              />
            ))}
            {EDGES.map((e) => (
              <path
                key={`trail-${e.id}`}
                d={e.d}
                className="flow-trail"
                ref={(el) => { trailRefs.current[e.id] = el; }}
              />
            ))}
          </g>

          <g className="flow-nodes">
            {NODES.map((n) => {
              const isActive = active.has(n.id);
              const isVisited = visited.has(n.id) && !isActive;
              const cls = [
                "flow-node",
                `tone-${n.tone}`,
                isActive ? "is-active" : "",
                isVisited ? "is-visited" : "",
              ].filter(Boolean).join(" ");
              const status = isActive ? n.working : isVisited ? n.done : "";

              return (
                <g key={n.id} className={cls}>
                  {n.avatar ? (
                    <circle className="flow-node-shape" cx={n.x} cy={n.y} r={n.w / 2} />
                  ) : (
                    <rect
                      className="flow-node-shape"
                      x={n.x - n.w / 2}
                      y={n.y - n.h / 2}
                      width={n.w}
                      height={n.h}
                      rx={10}
                    />
                  )}
                  {n.avatar ? (
                    <text className="flow-node-avatar" x={n.x} y={n.y + 6}>
                      {n.label.slice(0, 1)}
                    </text>
                  ) : (
                    <>
                      <text className="flow-node-label" x={n.x} y={n.y - 6}>
                        {n.label}
                      </text>
                      <text className="flow-node-sub" x={n.x} y={n.y + 13}>
                        {n.sub}
                      </text>
                    </>
                  )}
                  {n.avatar && (
                    <text className="flow-node-caption" x={n.x} y={n.y + n.h / 2 + 18}>
                      {n.label}
                    </text>
                  )}
                  {status ? (
                    <text
                      className="flow-node-status"
                      x={n.x}
                      y={n.y + n.h / 2 + (n.avatar ? 34 : 17)}
                    >
                      {status}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </g>

          <g className="flow-packets">
            {Array.from({ length: MAX_PACKETS }).map((_, i) => (
              <g
                key={i}
                className="flow-packet"
                style={{ opacity: 0 }}
                ref={(el) => { packetRefs.current[i] = el; }}
              >
                <circle className="flow-packet-halo" r={11} />
                <circle className="flow-packet-core" r={5} />
              </g>
            ))}
          </g>
        </svg>
      </div>

      <p className="flow-caption" aria-live="polite">
        <span className="flow-caption-label">{scene.label}</span>
        {scene.caption}
      </p>

      <div className="flow-transport">
        <button
          className="flow-btn"
          onClick={() => setPlaying((v) => !v)}
          aria-label={playing ? "Pause" : "Play"}
          title={playing ? "Pause" : "Play"}
        >{playing ? "❚❚" : "▶"}</button>
        <button
          className="flow-btn"
          onClick={() => step(-1)}
          disabled={sceneIndex === 0}
          aria-label="Previous step"
          title="Previous step"
        >‹</button>
        <button
          className="flow-btn"
          onClick={() => step(1)}
          disabled={sceneIndex === SCENES.length - 1}
          aria-label="Next step"
          title="Next step"
        >›</button>
        <button
          className="flow-btn"
          onClick={() => seek(0)}
          aria-label="Restart"
          title="Restart"
        >⟲</button>

        <div className="flow-scrub">
          <div className="flow-scrub-track">
            <div className="flow-scrub-fill" ref={barRef} />
            {SCENE_STARTS.map((s, i) => (
              <span
                key={SCENES[i].id}
                className="flow-scrub-tick"
                style={{ left: `${(s / TOTAL_MS) * 100}%` }}
              />
            ))}
          </div>
          <input
            ref={rangeRef}
            className="flow-scrub-input"
            type="range"
            min={0}
            max={TOTAL_MS}
            step={20}
            defaultValue={0}
            aria-label="Scrub the sequence"
            onInput={(e) => seek(Number((e.target as HTMLInputElement).value))}
          />
        </div>

        <span className="flow-count">
          {String(sceneIndex + 1).padStart(2, "0")}
          <span className="flow-count-sep">/</span>
          {String(SCENES.length).padStart(2, "0")}
        </span>
      </div>

      <div className="flow-chips" role="group" aria-label="Jump to step">
        {SCENES.map((s, i) => (
          <button
            key={s.id}
            className={`flow-chip${i === sceneIndex ? " on" : ""}`}
            onClick={() => seek(SCENE_STARTS[i])}
            aria-current={i === sceneIndex ? "step" : undefined}
          >{s.label}</button>
        ))}
      </div>
    </div>
  );
}
