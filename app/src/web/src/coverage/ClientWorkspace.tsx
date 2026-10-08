/**
 * Client workspace - prepare, guardrails, call, wrap-up.
 *
 *   Prepare     posture indicators, shock impact (incl. the live-deal re-cut),
 *               exposure allocation, engagement history.
 *   Guardrails  what may be said, what needs a disclaimer or approval, what must
 *               not be said; the banker approves before connecting.
 *   Call        simulated call: the client's questions arrive in turn and each
 *               answer is grounded, pre-approved framing with its sources; the
 *               internal note never leaves the screen.
 *   Wrap-up     agreed next steps -> coverage memo (.docx) + follow-up email,
 *               saved to the banker's own Outlook Drafts (the Cowork step).
 *
 * The AI panel on the right is the LIVE Foundry agent (all four IQ layers),
 * scoped to this client by its suggested prompts.
 */

import { useEffect, useRef, useState } from "react";
import { apiDownload, apiGet, apiPost, streamChat } from "../api";
import { Markdown } from "../components/Markdown";
import type { CallScript, Guardrails, Workspace, Wrapup } from "./types";
import { SplitHandle, SplitRail, type ChatSplit } from "../components/ChatSplit";
import type { CSSProperties } from "react";

type Step = "prepare" | "guardrails" | "call" | "wrapup";
const STEPS: { id: Step; label: string }[] = [
  { id: "prepare", label: "Prepare" }, { id: "guardrails", label: "Guardrails" },
  { id: "call", label: "Call" }, { id: "wrapup", label: "Wrap-up" },
];

function AiPanel({ ws, hidden }: { ws: Workspace; hidden?: boolean }) {
  const [q, setQ] = useState("");
  const [answer, setAnswer] = useState("");
  const [asked, setAsked] = useState("");
  const [layers, setLayers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const thread = useRef<string | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const ask = async (question: string, label?: string) => {
    if (!question.trim() || busy) return;
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setAsked(label ?? question);
    setAnswer("");
    setLayers([]);
    setBusy(true);
    await streamChat(question, thread.current, {
      onStatus: setStatus,
      onIQ: (iq) => setLayers((l) => (l.includes(iq) ? l : [...l, iq])),
      onToken: (t) => setAnswer((a) => a + t),
      onMessage: (t) => setAnswer(t),
      onError: (t, d) => setAnswer(`**${t}**\n\n${d}`),
      onDone: (p) => {
        setBusy(false);
        setStatus("");
        if (typeof p.threadId === "string") thread.current = p.threadId;
      },
    }, ctrl.signal).catch(() => setBusy(false));
  };

  return (
    <aside className="cv-ai" id="cv-ai-panel" hidden={hidden} aria-label="AI assistant for this client">
      <header><span className="cv-ai-mark" aria-hidden>✦</span><b>Coverage AI</b><small>Live Foundry agent · {ws.name}</small></header>
      <div className="cv-ai-prompts">
        {ws.prompts.map((p) => (
          <button key={p.label} type="button" disabled={busy} onClick={() => ask(p.prompt, p.label)}>{p.label} ↗</button>
        ))}
      </div>
      <div className="cv-ai-body" aria-live="polite">
        {!asked && <p className="cv-muted">Pick a prompt or ask anything about {ws.name}. Answers are grounded across Work, Fabric, Foundry and Web IQ under your identity.</p>}
        {asked && <div className="cv-ai-q">{asked}</div>}
        {layers.length > 0 && <div className="cv-ai-layers">{layers.map((l) => <span key={l} className={`cv-ai-layer l-${l}`}>{l} IQ</span>)}</div>}
        {busy && !answer && <div aria-busy="true"><div className="skel skel-line w90" /><div className="skel skel-line w75" /><small className="cv-muted">{status}</small></div>}
        {answer && <div className="cv-ai-answer"><Markdown text={answer} /></div>}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(q); setQ(""); }}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask about ${ws.name}…`} aria-label="Ask the agent" />
        <button type="submit" className="cp-primary" disabled={busy || !q.trim()}>Ask</button>
      </form>
    </aside>
  );
}

function Prepare({ ws }: { ws: Workspace }) {
  const b = ws.impact.binding;
  return (
    <>
      <div className="cv-posture">
        {ws.posture.map((p) => (
          <div key={p.label} className={`cv-post t-${p.tone}`}><small>{p.label}</small><b>{p.value}</b><span>{p.sub}</span></div>
        ))}
      </div>
      <div className="cv-two">
        <article className="cv-card">
          <div className="cv-card-head"><h3>Today's shock</h3><span>Adjusted EBITDA {ws.impact.ebitda_shock_pct > 0 ? "+" : ""}{ws.impact.ebitda_shock_pct.toFixed(1)}%</span></div>
          <p>{ws.impact.driver}</p>
          {ws.impact.covenants.map((c) => (
            <div key={c.covenant} className="cv-cov">
              <span>{c.covenant}</span>
              <span>{c.before}x → <b className={`t-${c.tone}`}>{c.after}x</b> vs {c.threshold}x</span>
              <span className={`cv-band t-${c.tone}`}>{c.band_after}</span>
            </div>
          ))}
          {b && <p className="cv-muted">EBITDA cushion {b.cushion_before}% → {b.cushion_after}%.</p>}
          {ws.impact.deal && (
            <p className="cv-callout">
              Revolver path to yes, re-cut: largest clearing increase CAD {ws.impact.deal.max_clearing_before_m}m → <b>CAD {ws.impact.deal.max_clearing_after_m}m</b>.
              The ask runs {ws.impact.deal.ask_leverage_after}x and the resized +150m {ws.impact.deal.resized_150_leverage_after}x
              ({ws.impact.deal.resized_150_clears ? "clears" : "breaches"}) on shocked EBITDA.
            </p>
          )}
        </article>
        <article className="cv-card">
          <div className="cv-card-head"><h3>Exposure allocation</h3><span>CAD {ws.exposure_m.toFixed(1)}m</span></div>
          {ws.allocation.map((a) => (
            <div key={a.product} className="cv-alloc">
              <div><span>{a.product}</span><b>{a.exposure_m.toFixed(1)}</b></div>
              <div className="cv-alloc-track"><span style={{ width: `${a.pct}%` }} /></div>
            </div>
          ))}
        </article>
      </div>
      <div className="cv-two">
        <article className="cv-card">
          <div className="cv-card-head"><h3>Engagement history</h3><span>Work IQ + Fabric IQ</span></div>
          <ul className="cv-timeline">
            {ws.engagement.map((e, i) => (
              <li key={i}><time>{e.date}</time><span className={`cv-kind k-${e.kind}`}>{e.kind}</span><span>{e.title}</span><small>{e.source}</small></li>
            ))}
          </ul>
        </article>
        <article className="cv-card">
          <div className="cv-card-head"><h3>Recent activity</h3><span>trade blotter</span></div>
          <ul className="cv-timeline">
            {ws.trades.map((t, i) => (
              <li key={i}><time>{t.date}</time><span className="cv-kind k-trade">{t.status}</span><span>{t.description}</span><small>CAD {t.notional_m}m</small></li>
            ))}
          </ul>
        </article>
      </div>
    </>
  );
}

function GuardrailsStep({ g, approved, onApprove }: { g: Guardrails | null; approved: boolean; onApprove: () => void }) {
  if (!g) return <div className="skel skel-card" />;
  const col = (title: string, items: string[], cls: string) => (
    <div className={`cv-guard ${cls}`}><h4>{title}</h4><ul>{items.map((t) => <li key={t}>{t}</li>)}</ul></div>
  );
  return (
    <>
      <div className="cv-guards">
        {col("You can say", g.can_say, "ok")}
        {col("Needs a disclaimer", g.needs_disclaimer, "info")}
        {col("Needs approval first", g.needs_approval, "warn")}
        {col("Do not say", g.never_say, "bad")}
      </div>
      <article className="cv-card">
        <div className="cv-card-head"><h3>Committee house view</h3><span>CP-015 · synthetic</span></div>
        <dl className="cv-hv">{g.house_view.map((h) => <div key={h.topic}><dt>{h.topic}</dt><dd>{h.view}</dd></div>)}</dl>
        <p className="cv-muted">Sources: {g.sources.join(" · ")}</p>
      </article>
      <div className="cv-step-actions">
        {approved
          ? <span className="cv-status accepted">Guardrails approved</span>
          : <button type="button" className="cp-primary cv-btn" onClick={onApprove}>Approve guardrails</button>}
      </div>
    </>
  );
}

function CallStep({ script, onFinish }: { script: CallScript | null; onFinish: () => void }) {
  const [shown, setShown] = useState(1);
  const [secs, setSecs] = useState(0);
  useEffect(() => { const t = window.setInterval(() => setSecs((s) => s + 1), 1000); return () => window.clearInterval(t); }, []);
  if (!script) return <div className="skel skel-card" />;
  const done = shown >= script.turns.length;
  const mm = `${String(Math.floor(secs / 60)).padStart(2, "0")}:${String(secs % 60).padStart(2, "0")}`;
  return (
    <div className="cv-call">
      <div className="cv-call-stage">
        <div className="cv-call-tile"><span className="cv-avatar">{script.contact_role.split(" ").map((w) => w[0]).join("").slice(0, 3)}</span><b>{script.contact_role}</b><small>{script.name}</small></div>
        <div className="cv-call-meta"><span className="cv-live">● Connected (simulated)</span><span>{script.channel_detail} · {mm}</span></div>
      </div>
      <ol className="cv-transcript">
        {script.turns.slice(0, shown).map((t, i) => (
          <li key={i} className={`turn-${t.kind}`}>
            <b>{t.speaker}</b>
            <p>{t.text}</p>
            {t.disclaimer && <small className="cv-disc">Disclaimer: {t.disclaimer}</small>}
            {t.internal && <div className="cv-internal"><b>Internal only</b> {t.internal}</div>}
            {t.sources && <div className="cv-srcs">{t.sources.map((s) => <span key={s}>{s}</span>)}</div>}
          </li>
        ))}
      </ol>
      <div className="cv-step-actions">
        {!done
          ? <button type="button" className="cp-primary cv-btn" onClick={() => setShown(shown + 1)}>Next ›</button>
          : <button type="button" className="cp-primary cv-btn" onClick={onFinish}>Wrap up ›</button>}
      </div>
    </div>
  );
}

function WrapupStep({ ws, script }: { ws: Workspace; script: CallScript | null }) {
  const [steps, setSteps] = useState<{ text: string; on: boolean }[]>([]);
  const [notes, setNotes] = useState("");
  const [draft, setDraft] = useState<Wrapup | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (script) setSteps(script.next_steps.map((t) => ({ text: t, on: true }))); }, [script]);
  const body = () => ({ agreed: steps.filter((s) => s.on).map((s) => s.text), notes });

  const generate = async () => {
    setBusy(true);
    try { setDraft(await apiPost<Wrapup>(`/api/coverage/client/${ws.id}/wrapup`, body())); setMsg(""); }
    catch (e) { setMsg(String(e)); } finally { setBusy(false); }
  };
  const toOutlook = async () => {
    setBusy(true);
    try {
      const r = await apiPost<{ note: string; webLink: string }>(`/api/coverage/client/${ws.id}/wrapup/outlook-draft`, body());
      setMsg(r.note + (r.webLink ? " " : ""));
      if (r.webLink) window.open(r.webLink, "_blank", "noopener");
    } catch (e) {
      setMsg(String(e).includes("502") ? "Outlook draft failed - sign out and back in once to grant mailbox draft access." : String(e));
    } finally { setBusy(false); }
  };

  return (
    <div className="cv-wrap">
      <article className="cv-card">
        <div className="cv-card-head"><h3>Agreed next steps</h3><span>untick anything not agreed</span></div>
        <ul className="cv-checks">
          {steps.map((s, i) => (
            <li key={i}><label><input type="checkbox" checked={s.on}
              onChange={() => setSteps(steps.map((x, j) => (j === i ? { ...x, on: !x.on } : x)))} />{s.text}</label></li>
          ))}
        </ul>
        <label className="cv-notes">Banker notes (optional)
          <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Anything else from the call…" />
        </label>
        <button type="button" className="cp-primary cv-btn" disabled={busy} onClick={generate}>Draft memo + email</button>
      </article>

      {draft && (
        <>
          <div className="papers-status">{draft.status}</div>
          <div className="cv-two">
            <article className="cv-card cv-doc">
              <div className="cv-card-head"><h3>{draft.memo.title}</h3><span>Word</span></div>
              {draft.memo.sections.map((s) => (
                <section key={s.heading}><h4>{s.heading}</h4><ul>{s.lines.map((l, i) => <li key={i}>{l}</li>)}</ul></section>
              ))}
            </article>
            <article className="cv-card cv-doc">
              <div className="cv-card-head"><h3>Follow-up email</h3><span>Outlook draft</span></div>
              <p><b>Subject:</b> {draft.email.subject}</p>
              <pre className="cv-email">{draft.email.body}</pre>
              <p className="cv-muted">{draft.email.to_note}</p>
            </article>
          </div>
          <div className="cv-step-actions">
            <button type="button" className="cv-btn-ghost" disabled={busy}
                    onClick={() => apiDownload(`/api/coverage/client/${ws.id}/wrapup/docx`, body(), "coverage-memo.docx")}>Download memo (.docx)</button>
            <button type="button" className="cp-primary cv-btn" disabled={busy} onClick={toOutlook}>Save email to Outlook drafts</button>
          </div>
          <details className="cv-card cv-cowork">
            <summary>Use Microsoft 365 Copilot Cowork instead</summary>
            <p className="cv-muted">With Cowork access, run the <b>CMCI Coverage Memo</b> skill (cowork/cmci-coverage-memo/SKILL.md) with this prompt:</p>
            <pre className="cv-email">{draft.cowork_prompt}</pre>
            <button type="button" className="cv-btn-ghost" onClick={() => navigator.clipboard?.writeText(draft.cowork_prompt)}>Copy prompt</button>
          </details>
        </>
      )}
      {msg && <p className="cv-muted" role="status">{msg}</p>}
    </div>
  );
}

export function ClientWorkspace({ clientId, onBack, guardApproved, onGuardApproved, split }: {
  split: ChatSplit;
  clientId: string;
  onBack: () => void;
  guardApproved: boolean;
  onGuardApproved: () => void;
}) {
  const [ws, setWs] = useState<Workspace | null>(null);
  const shell = useRef<HTMLDivElement>(null);
  const [g, setG] = useState<Guardrails | null>(null);
  const [script, setScript] = useState<CallScript | null>(null);
  const [step, setStep] = useState<Step>("prepare");
  const [error, setError] = useState("");

  useEffect(() => {
    setWs(null); setG(null); setScript(null); setStep("prepare");
    apiGet<Workspace>(`/api/coverage/client/${clientId}`).then(setWs).catch((e) => setError(String(e)));
    apiGet<Guardrails>(`/api/coverage/client/${clientId}/guardrails`).then(setG).catch(() => undefined);
    apiGet<CallScript>(`/api/coverage/client/${clientId}/call`).then(setScript).catch(() => undefined);
  }, [clientId]);

  const approve = async () => {
    try { await apiPost(`/api/coverage/client/${clientId}/guardrails/approve`, {}); onGuardApproved(); }
    catch (e) { setError(String(e)); }
  };

  const idx = STEPS.findIndex((s) => s.id === step);
  const locked = (s: Step) => (s === "call" || s === "wrapup") && !guardApproved;

  return (
    <div ref={shell} className={`cv-ws${split.open ? "" : " cv-ws-collapsed"}`} style={{ "--split-w": `${split.width}%` } as CSSProperties}>
      <div className="cv-ws-main">
        <div className="cv-ws-top">
          <button type="button" className="cv-link" onClick={onBack}>← Accounts overview</button>
          <ol className="cv-steps" aria-label="Workflow">
            {STEPS.map((s, i) => (
              <li key={s.id} className={i === idx ? "on" : i < idx ? "done" : ""}>
                <button type="button" disabled={locked(s.id)} title={locked(s.id) ? "Approve the guardrails first" : ""}
                        onClick={() => setStep(s.id)}>{i + 1} · {s.label}</button>
              </li>
            ))}
          </ol>
        </div>
        {error && <p className="cv-error">{error}</p>}
        {!ws ? <div aria-busy="true"><div className="skel skel-title" /><div className="skel skel-card" /></div> : <>
          <header className="cv-ws-head">
            <div>
              <div className="cv-eyebrow">{ws.tier} · {ws.sector} / {ws.sub_sector}{ws.restricted ? " · RESTRICTED LIST" : ""}</div>
              <h2>{ws.name} <small>{ws.ticker}</small></h2>
              <p className="cv-muted">Owner {ws.owner.name} · Committed CAD {ws.committed_m.toFixed(1)}m · Revenue FY26 YTD CAD {ws.revenue_ytd_m.toFixed(2)}m
                {ws.wallet_share_pct !== null ? ` · Wallet ${ws.wallet_share_pct}%` : ""}</p>
            </div>
            <div className="cv-ws-call">
              <small>{ws.contact_role}</small>
              <b>{ws.channel_detail} · {ws.slot}</b>
              {step !== "call" && (
                <button type="button" className="cp-primary cv-btn" disabled={!guardApproved}
                        title={guardApproved ? "" : "Approve the guardrails first"}
                        onClick={() => setStep("call")}>Connect</button>
              )}
            </div>
          </header>

          {step === "prepare" && <><Prepare ws={ws} /><div className="cv-step-actions"><button type="button" className="cp-primary cv-btn" onClick={() => setStep("guardrails")}>Review guardrails ›</button></div></>}
          {step === "guardrails" && <GuardrailsStep g={g} approved={guardApproved} onApprove={approve} />}
          {step === "call" && <CallStep script={script} onFinish={() => setStep("wrapup")} />}
          {step === "wrapup" && <WrapupStep ws={ws} script={script} />}
        </>}
      </div>
      {split.open ? <SplitHandle split={split} container={shell} controls="cv-ai-panel" /> : <SplitRail split={split} controls="cv-ai-panel" label="Coverage AI" />}
      {ws ? <AiPanel ws={ws} hidden={!split.open} /> : <aside className="cv-ai" id="cv-ai-panel" hidden={!split.open} aria-busy="true" />}
    </div>
  );
}
