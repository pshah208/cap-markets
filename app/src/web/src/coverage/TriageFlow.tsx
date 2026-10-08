/**
 * Review impact -> triage -> outreach plan -> approve -> responses.
 *
 * Step 1 ranks every relationship by a deterministic 0-100 severity score and
 * shows exactly which factors produced it. Step 2 proposes outreach for the
 * affected ones on each client's preferred channel; the banker can adjust the
 * channel or slot, then approves. Delivery is simulated - nothing leaves the
 * tenant - and the approval is audit-logged with the banker's UPN.
 */

import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";
import type { OutreachItem, OutreachPlan, OutreachResult, OutreachStatus, Triage } from "./types";

const STATUS: Record<OutreachStatus["status"], string> = {
  accepted: "Confirmed", awaiting: "Awaiting reply", tomorrow: "Tomorrow",
};

export function TriageFlow({ onClose, onOpenClient, approved, onApproved }: {
  onClose: () => void;
  onOpenClient: (id: string) => void;
  approved: OutreachResult | null;
  onApproved: (r: OutreachResult) => void;
}) {
  const [step, setStep] = useState<1 | 2>(approved ? 2 : 1);
  const [triage, setTriage] = useState<Triage | null>(null);
  const [plan, setPlan] = useState<OutreachPlan | null>(null);
  const [edits, setEdits] = useState<Record<string, Partial<OutreachItem>>>({});
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiGet<Triage>("/api/coverage/triage").then(setTriage).catch((e) => setError(String(e)));
    apiGet<OutreachPlan>("/api/coverage/outreach").then(setPlan).catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const approve = async (ids: string[]) => {
    if (!plan) return;
    setBusy(true);
    try {
      const items = plan.items.filter((i) => ids.includes(i.id))
        .map((i) => ({ id: i.id, channel: edits[i.id]?.channel ?? i.channel, slot: edits[i.id]?.slot ?? i.slot }));
      const r = await apiPost<OutreachResult>("/api/coverage/outreach/approve", { items });
      const merged = approved ? { ...r, items: [...approved.items.filter((x) => !ids.includes(x.id)), ...r.items] } : r;
      onApproved(merged);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const statusFor = (id: string) => approved?.items.find((x) => x.id === id);
  const pending = plan?.items.filter((i) => !statusFor(i.id)).map((i) => i.id) ?? [];

  return (
    <div className="cv-drawer-backdrop" onClick={onClose} role="presentation">
      <aside className="cv-drawer" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="Market impact triage">
        <header className="cv-drawer-head">
          <div>
            <div className="cv-eyebrow">Market alert · {triage?.as_of ?? ""}</div>
            <h2>{step === 1 ? "Impact triage" : "Outreach plan"}</h2>
          </div>
          <ol className="cv-steps" aria-label="Progress">
            <li className={step === 1 ? "on" : "done"}><button type="button" onClick={() => setStep(1)}>1 · Triage</button></li>
            <li className={step === 2 ? "on" : ""}><button type="button" onClick={() => setStep(2)}>2 · Outreach</button></li>
          </ol>
          <button type="button" className="cv-x" onClick={onClose} aria-label="Close">✕</button>
        </header>

        {error && <p className="cv-error">{error}</p>}

        {step === 1 && (
          <div className="cv-drawer-body">
            {!triage ? <div className="skel skel-card" /> : <>
              <p className="cv-muted" title={triage.method}>
                Ranked by a deterministic 0–100 severity score (stressed covenant, limit, rating trend, near-term events, shock size);
                {" "}{triage.items.filter((i) => i.affected).length} of {triage.items.length} relationships score at or above {triage.threshold}.
                Expand a row to see exactly how its score was built.
              </p>
              <ol className="cv-triage">
                {triage.items.map((it, n) => (
                  <li key={it.id} className={it.affected ? "affected" : ""}>
                    <button type="button" className="cv-triage-row" aria-expanded={open === it.id}
                            onClick={() => setOpen(open === it.id ? null : it.id)}>
                      <span className="cv-rank">{n + 1}</span>
                      <span className="cv-triage-name">{it.name}<small>{it.tier} · {it.sector}</small></span>
                      <span className="cv-triage-cov">
                        {it.binding ? <>{it.binding.before}x → <b className={`t-${it.binding.tone}`}>{it.binding.after}x</b><small>{it.binding.band_after}</small></> : "—"}
                      </span>
                      <span className="cv-meter" aria-label={`Severity ${it.score} of 100`}>
                        <span style={{ width: `${it.score}%` }} className={it.score >= 55 ? "bad" : it.affected ? "warn" : "ok"} />
                      </span>
                      <span className={`cv-score ${it.affected ? "on" : ""}`}>{it.score}</span>
                    </button>
                    {open === it.id && (
                      <div className="cv-triage-detail">
                        <p>{it.driver}</p>
                        <table>
                          <tbody>
                            {it.parts.map((p) => <tr key={p.factor}><th>{p.factor}</th><td>{p.detail}</td><td className="pts">+{p.points}</td></tr>)}
                          </tbody>
                        </table>
                        {it.deal && (
                          <p className="cv-callout">
                            Live deal re-cut on shocked EBITDA: the largest clearing increase falls from CAD {it.deal.max_clearing_before_m}m to
                            <b> CAD {it.deal.max_clearing_after_m}m</b>; the resized +150m now runs {it.deal.resized_150_leverage_after}x
                            ({it.deal.resized_150_clears ? "clears" : "breaches"}).
                          </p>
                        )}
                        {it.pse && <p className="cv-muted">Derivative pre-settlement exposure CAD {it.pse.before}m → {it.pse.after}m ({it.pse.pct_after}% of limit) as the wider differential moves the hedge toward the client.</p>}
                        <button type="button" className="cv-link" onClick={() => onOpenClient(it.id)}>Open workspace →</button>
                      </div>
                    )}
                  </li>
                ))}
              </ol>
              <div className="cv-drawer-actions">
                <button type="button" className="cp-primary cv-btn" onClick={() => setStep(2)}>See outreach plan →</button>
              </div>
            </>}
          </div>
        )}

        {step === 2 && (
          <div className="cv-drawer-body">
            {!plan ? <div className="skel skel-card" /> : <>
              <p className="cv-muted">Proposed contact for each affected relationship on its preferred channel. Adjust, then approve. Delivery is simulated — nothing leaves the tenant.</p>
              <ul className="cv-outreach">
                {plan.items.map((it) => {
                  const st = statusFor(it.id);
                  const ch = edits[it.id]?.channel ?? it.channel;
                  const slot = edits[it.id]?.slot ?? it.slot;
                  return (
                    <li key={it.id} className={st ? `sent ${st.status}` : ""}>
                      <div className="cv-out-head">
                        <b>{it.name}</b>
                        <span className="cv-muted">{it.contact_role} · caller {it.caller.name}</span>
                        <span className={`cv-score on`}>{it.score}</span>
                      </div>
                      <div className="cv-out-ctrl">
                        <label>Channel
                          <select value={ch} disabled={!!st}
                                  onChange={(e) => setEdits({ ...edits, [it.id]: { ...edits[it.id], channel: e.target.value } })}>
                            {plan.channels.map((c) => <option key={c} value={c}>{c === "chat" ? "Teams chat" : c === "video" ? "Teams video" : c[0].toUpperCase() + c.slice(1)}</option>)}
                          </select>
                        </label>
                        <label>When
                          <input value={slot} disabled={!!st}
                                 onChange={(e) => setEdits({ ...edits, [it.id]: { ...edits[it.id], slot: e.target.value } })} />
                        </label>
                        {st
                          ? <span className={`cv-status ${st.status}`}>{STATUS[st.status]}<small>{st.detail}</small></span>
                          : <button type="button" className="cv-btn-ghost" disabled={busy} onClick={() => approve([it.id])}>Approve</button>}
                      </div>
                      <p className="cv-out-msg">“{it.message}”</p>
                      {it.guardrail_notes.map((g) => <p key={g} className="cv-guard-note">⚑ {g}</p>)}
                      {st?.status === "accepted" && (
                        <button type="button" className="cp-primary cv-btn" onClick={() => onOpenClient(it.id)}>Prepare for the call →</button>
                      )}
                    </li>
                  );
                })}
              </ul>
              <div className="cv-drawer-actions">
                {pending.length > 0
                  ? <button type="button" className="cp-primary cv-btn" disabled={busy} onClick={() => approve(pending)}>Approve all ({pending.length})</button>
                  : <span className="cv-muted">All outreach approved{approved ? ` by ${approved.approved_by}` : ""}. {approved?.note}</span>}
              </div>
            </>}
          </div>
        )}
      </aside>
    </div>
  );
}
