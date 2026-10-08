/**
 * Agent mission for one client - the Dashboard actions that need an agent, run through a visible harness.
 *
 * The Dashboard's numbers are deterministic (and labelled so). This panel shows what an API alone returns
 * next to what only the agent can do, then runs one mission end to end:
 *   1 plan -> 2 governed packet + business-line positions + rules view -> 3 agent (live tool calls)
 *   -> 4 guardrails -> 5 barrier reviewer -> 6 banker decision (audit-logged).
 * Streams from POST /api/missions/{kind}/run.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost, streamSSE } from "../api";
import { Markdown } from "./Markdown";
import "./missions.css";

export type MissionKind = "briefing" | "opportunities" | "risks";
export type Layer = "work" | "fabric" | "foundry" | "web";
const LAYER_NAME: Record<Layer, string> = { work: "Work IQ", fabric: "Fabric IQ", foundry: "Foundry IQ", web: "Web IQ" };
export const MISSION_KINDS: { id: MissionKind; label: string }[] = [
  { id: "briefing", label: "Prepare briefing" }, { id: "opportunities", label: "Explore opportunities" }, { id: "risks", label: "Review risks" },
];

interface LinePos { line: string; stance: string; action: string; rationale: string; policy: string }
/** Live retrieval for one client by IQ layer, captured from the mission's own tool calls and citations. */
export interface EvidenceSnap {
  clientId: string; kind: string; runId: string; agent: string; at: string; restricted: boolean;
  layers: Record<Layer, { queries: string[]; results: { title: string; meta: string }[]; used: boolean }> | null;
}
interface Mission {
  kind: MissionKind; clientId: string; client: string; asOf: string; agentName: string; reviewer: string; title: string;
  question: string; deliverable: string; api: string[]; agentCan: string[]; rulesView: string; conflict: boolean;
  lines: LinePos[]; harness: { step: string; title: string; detail: string }[];
}
interface Check { rule: string; name: string; status: "pass" | "warn" | "block"; detail: string }
interface Step { state: "idle" | "running" | "done" | "skipped" | "failed" | "waiting"; title: string; detail: string; ms: number; data: any }
interface ToolCall { iq: Layer | null; tool: string; detail: string; error: string }
interface Decision { decision: string; by: string; at: string; note: string; runId: string; guardrails: string; review: string; rulesFlag: string }

const STEP_ICON: Record<Step["state"], string> = { idle: "○", running: "◌", done: "✓", skipped: "–", failed: "✕", waiting: "●" };
const secs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);
const stanceClass = (s: string) => `ms-st-${s.toLowerCase()}`;

export function MissionPanel({ clientId, kind, onKind, onDecided, onEvidence }: {
  clientId: string; kind: MissionKind; onKind: (k: MissionKind) => void; onDecided?: () => void;
  onEvidence?: (snap: EvidenceSnap) => void;
}) {
  const [m, setM] = useState<Mission | null>(null);
  const [err, setErr] = useState("");
  const [steps, setSteps] = useState<Record<string, Step>>({});
  const [tools, setTools] = useState<ToolCall[]>([]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [answer, setAnswer] = useState("");
  const [review, setReview] = useState("");
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<Decision | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [copied, setCopied] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const t0 = useRef(0);
  const [, tick] = useState(0);

  const reset = () => {
    setSteps({}); setTools([]); setLayers([]); setAnswer(""); setReview(""); setRunId(""); setError("");
    setDecision(null); setNote(""); setCopied(false);
  };

  useEffect(() => {
    abort.current?.abort(); setRunning(false); reset(); setM(null); setErr("");
    apiGet<Mission>(`/api/missions/${kind}/${clientId}`).then(setM).catch((e) => setErr(String(e)));
  }, [kind, clientId]);
  useEffect(() => () => abort.current?.abort(), []);
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => tick((x) => x + 1), 250);
    return () => window.clearInterval(id);
  }, [running]);

  const guard = steps.guardrails?.data ?? null;
  const checks: Check[] = guard?.checks ?? [];
  const clientMsg: { subject: string; body: string } | null = guard?.clientMessage ?? null;
  const verdict: string = guard?.verdict ?? "";
  const rulesFlag: string = guard?.rulesFlag ?? "";
  const rulesReason: string = guard?.rulesReason ?? "";
  const reviewVerdict: string = steps.review?.data?.verdict ?? "";
  const started = Object.keys(steps).length > 0;
  const copyBlocked = verdict === "blocked" || reviewVerdict === "BLOCKED";
  const elapsed = running ? performance.now() - t0.current : (steps.human?.ms ?? steps.agent?.ms ?? 0);
  const stats = useMemo(() => {
    const by: Record<string, number> = {};
    tools.forEach((t) => { const k = t.iq ?? "other"; by[k] = (by[k] ?? 0) + 1; });
    return by;
  }, [tools]);

  const run = async () => {
    if (!m || running) return;
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    reset();
    setRunning(true);
    t0.current = performance.now();
    await streamSSE(`/api/missions/${kind}/run`, { clientId }, {
      onIQ: (iq, st) => { if (st === "active") setLayers((l) => (l.includes(iq as Layer) ? l : [...l, iq as Layer])); },
      onToken: (t) => setAnswer((a) => a + t),
      onMessage: (t) => setAnswer(t),
      onError: (t, d) => setError(`${t} ${d}`.trim()),
      onDone: (p) => { if (typeof p.runId === "string") setRunId(p.runId); setRunning(false); },
      onEvent: (ev, p) => {
        if (ev === "harness") {
          if (p.runId) setRunId(p.runId);
          setSteps((s) => ({ ...s, [p.step]: { state: p.state, title: p.title, detail: p.detail, ms: p.ms, data: p.data ?? {} } }));
          if (p.step === "agent" && p.state === "done" && p.data?.evidence) onEvidence?.(p.data.evidence as EvidenceSnap);
        } else if (ev === "tool_call") setTools((t) => [...t, p as ToolCall]);
        else if (ev === "review_token") setReview((r) => r + (p.text ?? ""));
        else if (ev === "review_message") setReview(p.text ?? "");
        else if (ev === "review_error") setReview(`**${p.text ?? "Reviewer error"}**\n\n${p.detail ?? ""}`);
      },
    }, ctrl.signal).catch((e) => { if (e?.name !== "AbortError") setError(String(e)); });
    setRunning(false);
  };

  const decide = async (d: "approve" | "send_back" | "escalate") => {
    if (!runId) return;
    setDeciding(true);
    try {
      setDecision(await apiPost<Decision>(`/api/missions/${kind}/decision`, {
        runId, clientId, decision: d, note, guardrails: verdict, review: reviewVerdict, rulesFlag, rulesReason,
      }));
      onDecided?.();
    } catch (e) {
      setError(`Could not record the decision: ${String(e)}`);
    } finally { setDeciding(false); }
  };

  const copyMsg = async () => {
    if (!clientMsg) return;
    try { await navigator.clipboard.writeText(`${clientMsg.subject}\n\n${clientMsg.body}`); setCopied(true); } catch { setCopied(false); }
  };

  return (
    <section className="ms-root" aria-labelledby={`ms-${clientId}-h`}>
      <header className="ms-head">
        <div className="ms-head-text">
          <div className="ms-eyebrow"><span className="ms-dot" aria-hidden />Agent mission · {m?.client ?? "…"} · runs through the harness</div>
          <div className="ms-kinds" role="tablist" aria-label="Mission">
            {MISSION_KINDS.map((k) => (
              <button key={k.id} type="button" role="tab" aria-selected={kind === k.id} disabled={running}
                      className={kind === k.id ? "on" : ""} onClick={() => onKind(k.id)}>{k.label}</button>
            ))}
          </div>
          <h2 id={`ms-${clientId}-h`}>{m?.title ?? "Loading mission…"}</h2>
          <p>{m?.question}</p>
        </div>
        {m && (
          <dl className="ms-deliv">
            <div><dt>Deliverable</dt><dd>{m.deliverable}</dd></div>
            <div><dt>Lines</dt><dd>{m.conflict ? <span className="ms-chip ms-chip-conflict">Lines disagree</span> : <span className="ms-chip ms-chip-ok">Lines agree</span>}</dd></div>
          </dl>
        )}
      </header>
      {err && <p className="ms-error" role="alert">Could not load the mission ({err}).</p>}

      {m && (
        <>
          <div className="ms-contrast">
            <div className="ms-col ms-col-api">
              <h3><span className="ms-tag ms-tag-api">API</span> An API alone returns</h3>
              <ul>{m.api.map((x) => <li key={x}>{x}</li>)}</ul>
              <p className="ms-rules"><b>Rules view:</b> {m.rulesView}</p>
              <small>Deterministic: governed figures and rules in code. No agent needed. Already on this page.</small>
            </div>
            <div className="ms-col ms-col-agent">
              <h3><span className="ms-tag ms-tag-agent">Agent</span> Only the agent can</h3>
              <ul>{m.agentCan.map((x) => <li key={x}>{x}</li>)}</ul>
              <small>{m.agentName} · Work IQ, Foundry IQ, Web IQ, Fabric IQ · {m.reviewer} on client text · you decide</small>
            </div>
          </div>

          <div className="ms-lines">
            <h3>Where the business lines stand <span>Fabric IQ · line_positions · each correct on its own terms</span></h3>
            <ul>
              {m.lines.map((l) => (
                <li key={l.line} className={stanceClass(l.stance)}>
                  <b>{l.line}</b><i>{l.stance}</i><span>{l.action}</span><small>{l.rationale} <code>{l.policy}</code></small>
                </li>
              ))}
            </ul>
          </div>

          <div className="ms-run-bar">
            <button type="button" className="ms-btn ms-btn-primary" disabled={running} onClick={run}>
              {running ? "Mission running…" : started ? "Run again" : "Run mission"}
            </button>
            {running && <button type="button" className="ms-btn ms-btn-ghost" onClick={() => { abort.current?.abort(); setRunning(false); }}>Stop</button>}
            <span className="ms-muted">{m.agentName} · as of {m.asOf}{started && <> · {secs(Math.round(elapsed))}</>}</span>
          </div>

          {started && (
            <div className="ms-run">
              <ol className="ms-steps" aria-label="Harness steps">
                {m.harness.map((h, i) => {
                  const s = steps[h.step];
                  const state = s?.state ?? "idle";
                  return (
                    <li key={h.step} className={`ms-step ms-s-${state}`}>
                      <span className="ms-step-ico" aria-hidden>{STEP_ICON[state]}</span>
                      <div>
                        <b>{i + 1}. {h.title}</b>
                        <span>{s?.title ?? h.detail}</span>
                        {s?.detail && <small>{s.detail}</small>}
                        {h.step === "agent" && (tools.length > 0 || layers.length > 0) && (
                          <span className="ms-layer-row">
                            {(["work", "foundry", "web", "fabric"] as Layer[]).map((l) => (
                              <i key={l} className={`ms-layer ms-l-${l}${layers.includes(l) || stats[l] ? " ms-lit" : ""}`}>
                                {LAYER_NAME[l]}{stats[l] ? ` ×${stats[l]}` : ""}
                              </i>
                            ))}
                          </span>
                        )}
                      </div>
                      {s && state !== "running" && <em>{secs(s.ms)}</em>}
                    </li>
                  );
                })}
              </ol>

              <div className="ms-body">
                {error && <p className="ms-error" role="alert">{error}</p>}
                {(tools.length > 0 || steps.agent) && (
                  <details className="ms-block" open={running}>
                    <summary><b>Agent trace</b><span>{tools.length} tool call{tools.length === 1 ? "" : "s"} · every call, in order</span></summary>
                    <ol className="ms-trace">
                      {tools.map((t, i) => (
                        <li key={i} className={t.error ? "ms-trace-err" : ""}>
                          <i className={`ms-layer ms-lit ms-l-${t.iq ?? "other"}`}>{t.iq ? LAYER_NAME[t.iq] : "Tool"}</i>
                          <code>{t.tool}</code><span>{t.detail}</span>{t.error && <small>{t.error}</small>}
                        </li>
                      ))}
                      {running && <li className="ms-trace-wait"><span className="ms-skel" /></li>}
                    </ol>
                  </details>
                )}
                {(answer || steps.agent?.state === "running") && (
                  <article className="ms-block ms-answer" aria-live="polite">
                    <div className="ms-answer-head">
                      <b>Agent's decision package</b>
                      {rulesFlag && <span className={`ms-flag ms-flag-${rulesFlag.toLowerCase()}`}>
                        {rulesFlag === "CHANGED" ? "Agent changed the rules answer" : "Agent agrees with the rules"}{rulesReason ? `: ${rulesReason}` : ""}
                      </span>}
                    </div>
                    {answer ? <Markdown text={answer} /> : <div className="ms-skel-lines"><span className="ms-skel" /><span className="ms-skel short" /></div>}
                  </article>
                )}
                {checks.length > 0 && (
                  <div className="ms-block">
                    <div className="ms-block-head">
                      <b>Guardrails over the agent's output</b>
                      <span className={`ms-verdict ms-v-${verdict}`}>{verdict === "pass" ? "Pass" : verdict === "blocked" ? "Blocked" : "Needs a banker"}</span>
                    </div>
                    <ul className="ms-checks">
                      {checks.map((c, i) => (
                        <li key={i} className={`ms-ck ms-ck-${c.status}`}>
                          <span aria-hidden>{c.status === "pass" ? "✓" : c.status === "warn" ? "!" : "✕"}</span>
                          <b>{c.name}</b><code>{c.rule}</code><small>{c.detail}</small>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {(review || steps.review) && (
                  <div className="ms-block">
                    <div className="ms-block-head">
                      <b>Barrier reviewer</b>
                      <span className={`ms-verdict ms-v-${reviewVerdict === "PASS" ? "pass" : reviewVerdict === "BLOCKED" ? "blocked" : reviewVerdict ? "needs_approval" : "none"}`}>
                        {steps.review?.state === "skipped" ? "Skipped" : reviewVerdict || (steps.review?.state === "running" ? "Reviewing…" : "-")}
                      </span>
                    </div>
                    {steps.review?.state === "skipped" && <p className="ms-muted">{steps.review.title}: {steps.review.detail}</p>}
                    {review && <div className="ms-review"><Markdown text={review.replace(/^\s*VERDICT:[^\n]*\n?/i, "")} /></div>}
                  </div>
                )}
                {steps.human && (
                  <div className="ms-block ms-human">
                    <div className="ms-block-head"><b>Your decision</b><span>The agent prepared this. You decide. Nothing is sent from here.</span></div>
                    {!decision ? (
                      <>
                        <label className="ms-note"><span>Note for the audit record (optional)</span>
                          <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Agreed - Credit first, then the pitch" />
                        </label>
                        <div className="ms-human-actions">
                          <button type="button" className="ms-btn ms-btn-primary" disabled={deciding} onClick={() => decide("approve")}>
                            {verdict === "blocked" ? "Approve plan (not the client text)" : "Approve plan"}
                          </button>
                          <button type="button" className="ms-btn" disabled={deciding} onClick={() => decide("send_back")}>Send back</button>
                          <button type="button" className="ms-btn" disabled={deciding} onClick={() => decide("escalate")}>Escalate</button>
                          {clientMsg && (
                            <button type="button" className="ms-btn ms-btn-ghost" disabled={copyBlocked} onClick={copyMsg}
                                    title={copyBlocked ? "Blocked by the guardrails or the reviewer" : "Copy the client text into your approved channel"}>
                              {copied ? "Copied ✓" : "Copy client text"}
                            </button>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="ms-decided">
                        <b>{decision.decision === "approve" ? "Approved" : decision.decision === "send_back" ? "Sent back" : "Escalated"}</b>
                        {" "}by {decision.by} at {new Date(decision.at).toLocaleString("en-CA")} · run <code>{decision.runId}</code>
                        {" "}· rules view {decision.rulesFlag || "-"} · guardrails {decision.guardrails || "-"} · reviewer {decision.review || "-"}
                        {decision.note && <> · "{decision.note}"</>}
                        <small>Written to the audit log - it feeds the "agent changed the answer" KPI.</small>
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
