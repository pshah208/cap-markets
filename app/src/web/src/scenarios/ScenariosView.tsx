/**
 * Scenarios - "what if the market moves?"
 *
 * Pick a preset or move the six factor sliders; the BFF's deterministic engine
 * (factor betas from the governed Fabric IQ table scenario_sensitivity) re-prices
 * every relationship: EBITDA -> covenants -> rating -> expected loss / capital ->
 * relationship value. The Scenario Analyst Foundry agent then writes the
 * committee brief, verifying positions in Fabric IQ and policy in Foundry IQ.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { apiGet, apiPost, streamSSE } from "../api";
import { Markdown } from "../components/Markdown";
import { MethodFlow } from "./MethodFlow";
import { SplitHandle, SplitRail, SplitToggle, useChatSplit } from "../components/ChatSplit";
import type { CSSProperties } from "react";
import type { ClientRun, Drivers, EmergingRisk, Library, ScenarioRun, WorldPulse, WorldTheme } from "./types";
import "./scenarios.css";

const DRIVER_LABEL: Record<keyof Drivers, string> = {
  revenue: "Revenue", expected_loss: "Expected loss", capital: "Capital charge", discount_rate: "Discount rate",
};

const m = (v: number, dp = 1) => `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(dp)}`;
const sm = (v: number, dp = 1) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(dp)}`;
const pct = (v: number | null) => (v === null ? "n/m" : `${sm(v)}%`);
const tone = (v: number) => (v > 0.005 ? "up" : v < -0.005 ? "down" : "flat");
const bandTone = (b: string) => (b === "Breach" ? "bad" : b === "Tight" ? "warn" : b === "Monitor" ? "watch" : "ok");
const fmtFactor = (v: number, unit: string) => (unit === "bp" ? `${sm(v, 0)}bp` : `${sm(v, 1)}%`);
// Colour a factor move by its effect on this (mostly commodity-linked, borrowing) book, not by its sign:
// higher rates, wider spreads and tariffs hurt; a weaker CAD (USD/CAD up) helps exporters.
const GOOD_DIR: Record<string, number> = {
  oil_pct: 1, gas_pct: 1, rates_bp: -1, spreads_bp: -1, usdcad_pct: 1, demand_pct: 1, tariff_pct: -1,
};

function Waterfall({ drivers, before, after }: { drivers: Drivers; before: number; after: number }) {
  const keys = Object.keys(DRIVER_LABEL) as (keyof Drivers)[];
  const max = Math.max(...keys.map((k) => Math.abs(drivers[k])), 0.01);
  return (
    <div className="sc-wf" role="table" aria-label="Relationship value bridge">
      <div className="sc-wf-row total" role="row"><span role="cell">Base relationship value</span><b role="cell">CAD {m(before)}m</b><span role="cell" /></div>
      {keys.map((k) => (
        <div key={k} className="sc-wf-row" role="row">
          <span role="cell">{DRIVER_LABEL[k]}</span>
          <b role="cell" className={`num t-${tone(drivers[k])}`}>{sm(drivers[k], 2)}m</b>
          <span role="cell" className="sc-bar" aria-hidden>
            <i className={tone(drivers[k])} style={{ width: `${(Math.abs(drivers[k]) / max) * 50}%` }} />
          </span>
        </div>
      ))}
      <div className="sc-wf-row total" role="row"><span role="cell">Scenario relationship value</span><b role="cell">CAD {m(after)}m</b><span role="cell" /></div>
    </div>
  );
}

function ClientRow({ c, maxAbs, open, onToggle }: { c: ClientRun; maxAbs: number; open: boolean; onToggle: () => void }) {
  const b = c.binding;
  return (
    <>
      <tr className={open ? "open" : ""}>
        <th scope="row">
          <button type="button" className="sc-link" aria-expanded={open} onClick={onToggle}>{c.name}</button>
          <small>{c.sector} · {c.tier}</small>
        </th>
        <td className={`num t-${tone(c.ebitda_pct)}`}>{sm(c.ebitda_pct)}%</td>
        <td>
          {b ? <><span className="num">{b.before.toFixed(2)}x → <b>{b.after.toFixed(2)}x</b></span> <small>vs {b.threshold.toFixed(2)}x</small>{" "}
            <span className={`sc-band b-${bandTone(b.band_after)}`}>{b.band_after}</span></> : <small>n/a</small>}
        </td>
        <td className="num">
          {c.rating_before}{c.notches !== 0 && <> → <b className={c.notches > 0 ? "t-down" : "t-up"}>{c.rating_after}</b></>}
          {c.notches !== 0 && <small> {c.notches > 0 ? `↓${c.notches}` : `↑${-c.notches}`}</small>}
        </td>
        <td className="num">{m(c.value_before_m, 2)} → <b>{m(c.value_after_m, 2)}</b></td>
        <td className="sc-delta">
          <span className="sc-bar" aria-hidden>
            <i className={tone(c.value_change_m)} style={{ width: `${(Math.abs(c.value_change_m) / maxAbs) * 50}%` }} />
          </span>
          <b className={`num t-${tone(c.value_change_m)}`}>{sm(c.value_change_m, 2)}m</b>
          <small>{pct(c.value_change_pct)}</small>
        </td>
      </tr>
      {open && (
        <tr className="sc-detail-row">
          <td colSpan={6}>
            <div className="sc-detail">
              <p><b>Why it moves.</b> {c.business_model}</p>
              <div className="sc-detail-grid">
                <span><small>Probability of default</small>{c.pd_before_pct}% → {c.pd_after_pct}%</span>
                <span><small>Exposure at default</small>CAD {m(c.ead_before_m)}m → {m(c.ead_after_m)}m{c.drawdown_m > 0 && <em> (+{m(c.drawdown_m)}m revolver draw)</em>}</span>
                <span><small>Expected loss / yr</small>{c.el_before_m.toFixed(2)} → {c.el_after_m.toFixed(2)}m</span>
                <span><small>Capital charge / yr</small>{c.capital_before_m.toFixed(2)} → {c.capital_after_m.toFixed(2)}m</span>
                <span><small>Revenue / yr</small>{c.revenue_before_m.toFixed(2)} → {c.revenue_after_m.toFixed(2)}m</span>
              </div>
              {c.covenants.map((k) => (
                <div key={k.covenant} className="sc-cov">
                  <span>{k.covenant}</span>
                  <span className="num">{k.before.toFixed(2)}x → <b>{k.after.toFixed(2)}x</b> vs {k.threshold.toFixed(2)}x · headroom {k.headroom_before} → {k.headroom_after}</span>
                  <span className={`sc-band b-${bandTone(k.band_after)}`}>{k.band_after}</span>
                </div>
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

const SEV_LABEL: Record<string, string> = { dormant: "Dormant", low: "Low", elevated: "Elevated", high: "High", severe: "Severe" };

function WorldEvents({ world, busy, error, selected, onPick, onRefresh }: {
  world: WorldPulse | null; busy: boolean; error: string; selected: string;
  onPick: (id: string) => void; onRefresh: () => void;
}) {
  const live = world?.status === "live";
  const when = world?.fetchedAt ? new Date(world.fetchedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "";
  return (
    <section className="sc-world" aria-label="World events with live Web IQ">
      <div className="sc-world-head">
        <h2>World events</h2>
        <span className={`sc-webiq ${busy ? "busy" : live ? "live" : "off"}`}>
          <i aria-hidden />{busy ? "Web IQ searching…" : live ? `Web IQ · ${when}${world?.stale ? " (stale)" : ""}` : "Governed baseline"}
        </span>
        <button type="button" className="sc-world-refresh" onClick={onRefresh} disabled={busy} title="Re-check the public web now" aria-label="Refresh from Web IQ">
          <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden className={busy ? "spin" : ""}>
            <path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9M13.5 2.5v3h-3" />
          </svg>
        </button>
      </div>
      <p className="sc-world-sub">
        Severity is read from today's public web; the shock applied is the governed preset scaled
        {world ? ` (low ×${world.intensity.low} · high ×${world.intensity.high} · severe ×${world.intensity.severe})` : ""}.
      </p>
      {(error || (world && !live && world.detail && !busy)) && <p className="sc-world-err">Web IQ unavailable - running the governed baseline.</p>}
      <div className="sc-presets" role="radiogroup" aria-label="World events">
        {!world && <><div className="skel skel-card sm" /><div className="skel skel-card sm" /><div className="skel skel-card sm" /></>}
        {world?.themes?.map((t, i) => (
          <button key={t.id} type="button" role="radio" aria-checked={selected === t.id} style={{ "--i": i } as CSSProperties}
                  className={`sc-wcard ${selected === t.id ? "on" : ""}${busy ? " loading" : ""}`} onClick={() => onPick(t.id)}>
            <span className="sc-wcard-top">
              <b>{t.name}</b>
              <span className={`sc-sev s-${t.severity}`}>{SEV_LABEL[t.severity]}</span>
            </span>
            {t.live && t.headline
              ? <small className="sc-wcard-news"><span className={`sc-dot d-${t.status}`} aria-label={t.status} />{t.headline}</small>
              : <small>{t.note}</small>}
            {t.live && (t.source || t.date) && <small className="sc-wcard-src">{[t.source, t.date].filter(Boolean).join(" · ")}</small>}
          </button>
        ))}
      </div>
    </section>
  );
}

function EmergingRadar({ items, selected, onRun }: {
  items: EmergingRisk[]; selected: string; onRun: (e: EmergingRisk) => void;
}) {
  if (!items.length) return null;
  return (
    <section className="sc-radar" aria-label="Emerging risks spotted by Web IQ">
      <div className="sc-world-head">
        <h2>Emerging risks</h2>
        <span className="sc-radar-tag">Web IQ radar · not yet governed</span>
      </div>
      <p className="sc-world-sub">
        Live risks outside the library. Run one through its closest governed scenario as a labelled proxy; to make it a
        scenario of its own, add it to the governed library (Fabric IQ).
      </p>
      <ul className="sc-radar-list">
        {items.map((e, i) => {
          const id = `emerging:${e.title}`;
          return (
            <li key={e.title} className={selected === id ? "on" : ""} style={{ "--i": i } as CSSProperties}>
              <span className="sc-wcard-top"><b>{e.title}</b><span className={`sc-sev s-${e.severity}`}>{SEV_LABEL[e.severity]}</span></span>
              <small className="sc-wcard-news">{e.headline}</small>
              {e.why && <small className="sc-radar-why">{e.why}</small>}
              <span className="sc-radar-foot">
                <small className="sc-wcard-src">{e.url ? <a href={e.url} target="_blank" rel="noreferrer">{e.source || "Source"} ↗</a> : e.source}{e.date ? ` · ${e.date}` : ""}</small>
                {e.closest
                  ? <button type="button" className="sc-radar-run" onClick={() => onRun(e)} aria-pressed={selected === id}
                            title={`Approximates this risk with the governed "${e.closest_name}" shock at ${e.severity} severity`}>
                      Proxy: {e.closest_name} ›
                    </button>
                  : <small className="sc-radar-none">No close proxy - needs a new governed scenario</small>}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function WorldBanner({ t }: { t: WorldTheme }) {
  return (
    <article className={`sc-wbanner s-${t.severity}`}>
      <div className="sc-wbanner-icon" aria-hidden>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
        </svg>
      </div>
      <div className="sc-wbanner-main">
        <small>{t.live ? "Live Web IQ · public web" : "Governed baseline · Web IQ not available"}</small>
        <b>{t.live && t.headline ? t.headline : t.note}</b>
        <span>{t.channels}</span>
        {t.live && (t.source || t.url) && (
          <span className="sc-wbanner-src">
            {t.url ? <a href={t.url} target="_blank" rel="noreferrer">{t.source || "Source"} ↗</a> : t.source}{t.date ? ` · ${t.date}` : ""}
          </span>
        )}
      </div>
      <div className="sc-wbanner-scale">
        <span className={`sc-sev s-${t.severity}`}>{SEV_LABEL[t.severity]}</span>
        <b>×{t.intensity}</b>
        <small>of the governed shock</small>
      </div>
    </article>
  );
}

function Analyst({ run, factors, hidden, worldId }: { run: ScenarioRun; factors: Record<string, number>; hidden?: boolean; worldId?: string | null }) {
  const [text, setText] = useState("");
  const [layers, setLayers] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [briefKey, setBriefKey] = useState("");
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => abort.current?.abort(), []);

  const key = `${run.name}|${JSON.stringify(factors)}`;
  const stale = !!briefKey && briefKey !== key;

  const brief = async () => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    setText(""); setLayers([]); setBusy(true); setStatus("Connecting to the Scenario Analyst…");
    setBriefKey(key);
    await streamSSE("/api/scenarios/narrate", { factors, name: run.name, worldId: worldId ?? null }, {
      onStatus: setStatus,
      onIQ: (iq) => setLayers((l) => (l.includes(iq) ? l : [...l, iq])),
      onToken: (t) => setText((a) => a + t),
      onMessage: (t) => setText(t),
      onError: (t, d) => setText(`**${t}**\n\n${d}`),
      onDone: () => { setBusy(false); setStatus(""); },
    }, ctrl.signal).catch(() => setBusy(false));
  };

  return (
    <aside className="sc-analyst" id="sc-analyst" hidden={hidden} aria-label="Scenario Analyst agent">
      <header>
        <span className="sc-analyst-mark" aria-hidden>✦</span>
        <div><b>Scenario Analyst</b><small>Foundry agent · Fabric IQ + Foundry IQ</small></div>
      </header>
      <p className="sc-muted">
        Turns this run into a committee-ready brief. The engine figures are given; the agent verifies covenant and
        limit positions in Fabric IQ and grounds the policy angle in the CP-015 house view.
        {worldId ? " For world events it also receives the public Web IQ headline behind the severity." : ""}
      </p>
      <button type="button" className="sc-primary" onClick={brief} disabled={busy}>
        {busy ? "Writing brief…" : text ? "Regenerate brief" : "Write committee brief"}
      </button>
      {stale && !busy && <p className="sc-stale">The scenario changed after this brief. Regenerate to refresh it.</p>}
      <div className="sc-analyst-body" aria-live="polite">
        {layers.length > 0 && <div className="sc-layers">{layers.map((l) => <span key={l} className={`sc-layer l-${l}`}>{l} IQ</span>)}</div>}
        {busy && !text && <div aria-busy="true"><div className="skel skel-line w90" /><div className="skel skel-line w75" /><div className="skel skel-line w60" /><small className="sc-muted">{status}</small></div>}
        {text && <div className="sc-analyst-text"><Markdown text={text} /></div>}
      </div>
    </aside>
  );
}

export function ScenariosView({ active, bankName }: { active: boolean; bankName: string }) {
  const [lib, setLib] = useState<Library | null>(null);
  const [factors, setFactors] = useState<Record<string, number>>({});
  const [presetId, setPresetId] = useState("oil-shock");
  const [run, setRun] = useState<ScenarioRun | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [showMethod, setShowMethod] = useState(false);
  const seq = useRef(0);
  const results = useRef<HTMLElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const chat = useChatSplit("cmci.scn.chat", 28, 20, 50);
  const [world, setWorld] = useState<WorldPulse | null>(null);
  const [worldBusy, setWorldBusy] = useState(false);
  const [worldErr, setWorldErr] = useState("");

  const loadWorld = (refresh = false) => {
    setWorldBusy(true); setWorldErr("");
    apiGet<WorldPulse>(`/api/scenarios/world${refresh ? "?refresh=true" : ""}`)
      .then((w) => setWorld(Array.isArray(w?.themes) ? w : null)).catch((e) => setWorldErr(String(e))).finally(() => setWorldBusy(false));
  };
  useEffect(() => {
    if (!active || world || worldBusy) return;
    apiGet<WorldPulse>("/api/scenarios/world?cached=true").then((w) => {
      if (!Array.isArray(w?.themes)) { loadWorld(); return; }
      setWorld(w);
      if (w.status !== "live") loadWorld();
    }).catch(() => loadWorld());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  useEffect(() => {
    if (!active || lib) return;
    apiGet<Library>("/api/scenarios/library").then((l) => {
      const first = l.presets.find((p) => p.id === "oil-shock") ?? l.presets[0];
      setLib(l);
      setPresetId(first.id);
      setFactors({ ...first.factors });
    }).catch((e) => setError(String(e)));
  }, [active, lib]);

  const theme: WorldTheme | undefined = world?.themes?.find((t) => t.id === presetId);
  const emerging: EmergingRisk | undefined = presetId.startsWith("emerging:")
    ? world?.emerging?.find((e) => `emerging:${e.title}` === presetId) : undefined;
  const name = theme
    ? `${theme.name} (${theme.live ? `Web IQ severity: ${theme.severity}` : "governed baseline"})`
    : emerging
      ? `Emerging: ${emerging.title} (proxy: ${emerging.closest_name}, ${emerging.severity})`
      : lib?.presets.find((p) => p.id === presetId)?.name ?? "Custom scenario";
  const runEmerging = (e: EmergingRisk) => {
    if (!e.proxy_factors) return;
    setPresetId(`emerging:${e.title}`);
    setFactors({ ...e.proxy_factors });
  };

  useEffect(() => {
    if (!lib || !Object.keys(factors).length) return;
    const id = ++seq.current;
    const t = window.setTimeout(() => {
      apiPost<ScenarioRun>("/api/scenarios/run", { factors, name })
        .then((r) => { if (id === seq.current) { setRun(r); setError(""); } })
        .catch((e) => setError(String(e)));
    }, 180);
    return () => window.clearTimeout(t);
  }, [lib, factors, name]);

  const maxAbs = useMemo(() => Math.max(0.01, ...(run?.clients ?? []).map((c) => Math.abs(c.value_change_m))), [run]);
  const sectorMax = useMemo(() => Math.max(0.01, ...(run?.sectors ?? []).map((s) => Math.abs(s.after - s.before))), [run]);
  const hero = run?.clients.find((c) => c.deal);
  const p = run?.portfolio;

  const pickPreset = (id: string) => {
    const t = world?.themes?.find((x) => x.id === id);
    const pr = lib?.presets.find((x) => x.id === id);
    if (!t && !pr) return;
    setPresetId(id);
    setFactors({ ...(t ? t.factors : pr!.factors) });
  };
  // Web IQ refresh changes a theme's severity: re-apply it if that theme is selected.
  useEffect(() => {
    const t = world?.themes?.find((x) => x.id === presetId);
    if (t) setFactors({ ...t.factors });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [world]);
  const nudge = (fid: string, v: number) => {
    setPresetId("custom");
    setFactors((f) => ({ ...f, [fid]: v }));
  };

  return (
    <section className="cp-dashboard sc-root" hidden={!active} aria-label="Scenario intelligence">
      <header className="cp-header">
        <div>
          <div className="cp-eyebrow">{bankName} · Scenario intelligence</div>
          <h1>What if the market moves?</h1>
          <p>Shock seven market factors and every relationship is re-priced: covenants, ratings, expected loss, capital and relationship value.</p>
        </div>
        <div className="cp-header-meta">
          <span className="cp-badge">Synthetic scenario · illustrative economics</span>
          <SplitToggle split={chat} controls="sc-analyst" />
          {lib && <span>As of <time dateTime={lib.as_of}>{lib.as_of}</time></span>}
          <button type="button" className={`sc-howbtn${showMethod ? " on" : ""}`} aria-expanded={showMethod}
                  onClick={() => { setShowMethod(!showMethod); if (!showMethod) results.current?.scrollTo({ top: 0, behavior: "smooth" }); }}>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
              <circle cx="5" cy="12" r="2" /><circle cx="12" cy="12" r="2" /><circle cx="19" cy="12" r="2" /><path d="M7 12h3M14 12h3" />
            </svg>
            {showMethod ? "Hide method" : "How it works"}
          </button>
        </div>
      </header>
      {error && <div className="sc-error" role="alert">Could not run the scenario: {error}</div>}

      <div ref={body} className={`sc-body${chat.open ? "" : " sc-collapsed"}`} style={{ "--split-w": `${chat.width}%` } as CSSProperties}>
        <nav className="sc-controls" aria-label="Scenario controls">
          <h2>Market scenarios</h2>
          <div className="sc-presets" role="radiogroup" aria-label="Market scenarios">
            {(lib?.presets ?? []).filter((pr) => pr.group !== "world").map((pr) => (
              <button key={pr.id} type="button" role="radio" aria-checked={presetId === pr.id}
                      className={presetId === pr.id ? "on" : ""} onClick={() => pickPreset(pr.id)}>
                <b>{pr.name}</b><small>{pr.note}</small>
              </button>
            ))}
            {presetId === "custom" && <div className="sc-custom">Custom scenario - adjusted by hand</div>}
          </div>
          <WorldEvents world={world} busy={worldBusy} error={worldErr} selected={presetId}
                       onPick={pickPreset} onRefresh={() => loadWorld(true)} />
          <EmergingRadar items={world?.emerging ?? []} selected={presetId} onRun={runEmerging} />
          <h2>Factors</h2>
          {(lib?.factors ?? []).map((f) => {
            const v = factors[f.id] ?? 0;
            return (
              <label key={f.id} className="sc-factor">
                <span className="sc-factor-head"><span>{f.label}</span><b className={`num t-${tone(v * (GOOD_DIR[f.id] ?? 1))}`}>{fmtFactor(v, f.unit)}</b></span>
                <input type="range" min={f.min} max={f.max} step={f.step} value={v}
                       onChange={(e) => nudge(f.id, Number(e.target.value))}
                       aria-valuetext={fmtFactor(v, f.unit)} />
                <span className="sc-range"><small>{fmtFactor(f.min, f.unit)}</small><small>{fmtFactor(f.max, f.unit)}</small></span>
              </label>
            );
          })}
          <button type="button" className="sc-reset" onClick={() => pickPreset("oil-shock")}>Reset to today's scenario</button>
        </nav>

        <main ref={results} className="sc-results" tabIndex={0} aria-label="Scenario results" aria-busy={!run}>
          {!run || !p ? (
            <div aria-busy="true"><div className="skel skel-title" /><div className="skel skel-card" /><div className="skel skel-card" /></div>
          ) : (
            <>
              {theme && <WorldBanner t={theme} />}
              {emerging && (
                <article className="sc-wbanner s-elevated sc-proxy">
                  <div className="sc-wbanner-icon" aria-hidden>≈</div>
                  <div className="sc-wbanner-main">
                    <small>Emerging risk · proxy run · not a governed scenario</small>
                    <b>{emerging.headline || emerging.title}</b>
                    <span>Approximated with the governed <b>{emerging.closest_name}</b> shock at {emerging.severity} severity. {emerging.why}</span>
                  </div>
                  <div className="sc-wbanner-scale"><span className={`sc-sev s-${emerging.severity}`}>{SEV_LABEL[emerging.severity]}</span><small>proxy</small></div>
                </article>
              )}
              {showMethod && lib && <MethodFlow run={run} lib={lib} initialId={open ?? run.clients[0]?.id} />}
              <div className="sc-kpis">
                <article className="sc-kpi hero">
                  <small>Relationship value · 3-yr PV</small>
                  <strong>CAD {m(p.value_after_m)}m</strong>
                  <span className={`t-${tone(p.value_change_m)}`}>{sm(p.value_change_m)}m ({sm(p.value_change_pct)}%) vs CAD {m(p.value_before_m)}m</span>
                </article>
                <article className={`sc-kpi ${p.breaches ? "bad" : p.tight ? "warn" : ""}`}>
                  <small>Covenants</small><strong>{p.breaches} breach{p.breaches === 1 ? "" : "es"}</strong><span>{p.tight} tight</span>
                </article>
                <article className={`sc-kpi ${p.downgrades ? "warn" : ""}`}>
                  <small>Rating migration</small><strong>{p.downgrades}↓ {p.upgrades}↑</strong><span>internal IG scale</span>
                </article>
                <article className="sc-kpi">
                  <small>Expected loss / yr</small><strong>CAD {p.el_after_m.toFixed(2)}m</strong><span>from {p.el_before_m.toFixed(2)}m</span>
                </article>
                <article className="sc-kpi">
                  <small>Exposure at default</small><strong>CAD {m(p.ead_after_m, 0)}m</strong>
                  <span>{p.ead_after_m > p.ead_before_m ? `+${m(p.ead_after_m - p.ead_before_m)}m revolver draws` : "no stress draws"}</span>
                </article>
              </div>

              <div className="sc-grid">
                <article className="sc-card">
                  <div className="sc-card-head"><h3>Value bridge</h3><span>CAD m · 3-yr PV</span></div>
                  <Waterfall drivers={p.drivers} before={p.value_before_m} after={p.value_after_m} />
                </article>
                <article className="sc-card">
                  <div className="sc-card-head"><h3>By sector</h3><span>relationship value change</span></div>
                  {run.sectors.map((s) => (
                    <div key={s.sector} className="sc-sector">
                      <span>{s.sector}<small> · {s.count}</small></span>
                      <span className="sc-bar" aria-hidden><i className={tone(s.after - s.before)} style={{ width: `${(Math.abs(s.after - s.before) / sectorMax) * 50}%` }} /></span>
                      <b className={`num t-${tone(s.after - s.before)}`}>{sm(s.after - s.before, 2)}m</b>
                    </div>
                  ))}
                  {hero?.deal && (
                    <p className="sc-callout">
                      <b>{hero.name} revolver re-cut.</b> On scenario EBITDA the largest increase that clears the leverage covenant is
                      {" "}<b>CAD {m(hero.deal.max_clearing_m)}m</b>; the full ask would run {hero.deal.ask_leverage}x.
                    </p>
                  )}
                </article>
              </div>

              <article className="sc-card">
                <div className="sc-card-head"><h3>Relationships, worst first</h3><span>select a name for the full re-pricing</span></div>
                <div className="sc-table-wrap">
                  <table className="sc-table">
                    <thead><tr><th scope="col">Client</th><th scope="col">EBITDA</th><th scope="col">Binding covenant</th>
                      <th scope="col">Rating</th><th scope="col">Value CAD m</th><th scope="col">Change</th></tr></thead>
                    <tbody>
                      {run.clients.map((c) => (
                        <ClientRow key={c.id} c={c} maxAbs={maxAbs} open={open === c.id} onToggle={() => setOpen(open === c.id ? null : c.id)} />
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
            </>
          )}
        </main>

        {chat.open ? <SplitHandle split={chat} container={body} controls="sc-analyst" label="Scenario Analyst" />
                   : <SplitRail split={chat} controls="sc-analyst" label="Scenario Analyst" />}
        {run ? <Analyst run={run} factors={factors} hidden={!chat.open} worldId={theme?.id ?? (emerging ? presetId : null)} /> : <aside className="sc-analyst" id="sc-analyst" hidden={!chat.open} aria-busy="true" />}
      </div>
    </section>
  );
}
