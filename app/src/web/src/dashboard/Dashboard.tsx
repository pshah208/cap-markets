import { useEffect, useRef, useState, type CSSProperties } from "react";
import { buildAnswer, companies, snapshotAsOf, snapshotDisclaimer, snapshotUnits, type Answer, type AnswerBlock, type Company } from "./data";
import { apiPost } from "../api";
import { SkillModal, useSkillCatalogue } from "../components/SkillBar";
import { ClientStressSkill } from "../components/skills/ClientStressSkill";
import { ClientPapersSkill, PapersSkill } from "../components/skills/PapersSkill";
import { ProFormaSkill } from "../components/skills/ProFormaSkill";
import type { ProFormaResult } from "../types";
import { apiGet as coverageGet } from "../api";
import { CoverageOverview } from "../coverage/CoverageOverview";
import { SplitHandle, SplitRail, SplitToggle, useChatSplit } from "../components/ChatSplit";
import { TriageFlow } from "../coverage/TriageFlow";
import { ClientWorkspace } from "../coverage/ClientWorkspace";
import type { CoverageOverview as Overview, OutreachResult } from "../coverage/types";
import { MissionPanel, type EvidenceSnap, type Layer, type MissionKind } from "../components/MissionPanel";
import "./dashboard.css";
import "../coverage/coverage.css";

type SortKey = "name" | "sector" | "exposureCad" | "commitmentCad" | "revenueCad" | "walletPercent" | "utilizationPercent";
type Exchange = { question: string; answer: Answer };
const number = new Intl.NumberFormat("en-CA", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const money = (value: number | null) => value === null ? "Unavailable" : number.format(value);
const percent = (value: number | null) => value === null ? "Unavailable" : `${value.toFixed(1)}%`;
const actions = [
  ["Prepare briefing", "briefing"],
  ["Explore opportunities", "opportunities"],
  ["Review risks", "risks"],
  ["Explain maturities", "maturity"],
] as const;
/** The three Dashboard actions that need an agent. "Explain maturities" stays a snapshot lookup. */
const missionActions: [string, MissionKind][] = [["Prepare briefing", "briefing"], ["Explore opportunities", "opportunities"], ["Review risks", "risks"]];
type BoardClient = { id: string; conflict: boolean; lines: { line: string; stance: string }[] };
type MissionStats = { decided: number; changed: number; agreed: number; approved: number; blocked: number;
  recent: { client: string; kind: string; rulesFlag: string; rulesReason: string; decision: string }[] };
const EV_LAYERS: { id: Layer; name: string; recorded: string }[] = [
  { id: "fabric", name: "Fabric IQ", recorded: "Fabric IQ" }, { id: "work", name: "Work IQ", recorded: "Work IQ" },
  { id: "foundry", name: "Foundry IQ", recorded: "Foundry IQ" }, { id: "web", name: "Web IQ", recorded: "Web IQ" },
];
const hhmm = (iso: string) => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-CA", { hour: "2-digit", minute: "2-digit" }); };

/** One evidence card: live from the last agent mission when there is one, else the recorded snapshot text. */
function EvidenceCard({ layer, snap, recorded, onRun }: {
  layer: (typeof EV_LAYERS)[number]; snap: EvidenceSnap | null;
  recorded?: { iq: string; status: string; text: string }; onRun: () => void;
}) {
  const live = snap?.layers?.[layer.id];
  if (snap?.layers && live) {
    return (
      <article className={`cp-card cp-ev-live cp-ev-${layer.id}`}>
        <div className="cp-evidence-title">
          <h3>{layer.name}</h3>
          <span className="cp-badge cp-badge-live">{live.used ? `live · retrieved ${hhmm(snap.at)}` : "not called this run"}</span>
        </div>
        {live.results.length ? (
          <ul className="cp-ev-list">{live.results.map((r, i) => <li key={i}><span>{r.title}</span>{r.meta && <small>{r.meta.startsWith("http") ? <a href={r.meta} target="_blank" rel="noreferrer">source</a> : r.meta}</small>}</li>)}</ul>
        ) : <p className="cp-ev-empty">{live.used ? "Searched - nothing returned for this client." : "The agent did not use this layer on this run."}</p>}
        {live.queries.length > 0 && <details className="cp-ev-q"><summary>What the agent asked ({live.queries.length})</summary><ul>{live.queries.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
        {layer.id === "work" && snap.restricted && <p className="cp-ev-note">Restricted name (CR-2026-0184): subjects only, no senders or content.</p>}
        <p className="cp-ev-foot">{snap.agent} · {snap.kind} mission · run <code>{snap.runId}</code></p>
      </article>
    );
  }
  return (
    <article className="cp-card cp-recorded">
      <div className="cp-evidence-title"><h3>{layer.name.replace(" IQ", "")} <small>(recorded)</small></h3><span className="cp-badge">{recorded?.status ?? "none"} · not retrieved</span></div>
      <p>{recorded?.text ?? "No recorded evidence for this layer."}</p>
      <button type="button" className="cp-ev-run" onClick={onRun}>Run a mission to retrieve live ↑</button>
    </article>
  );
}

function sum(rows: Company[], key: "exposureCad" | "commitmentCad" | "revenueCad") {
  const known = rows.map(row => row[key]).filter((value): value is number => value !== null);
  return { value: known.length ? known.reduce((total, value) => total + value, 0) : null, known: known.length };
}

function BlockBody({ block }: { block: AnswerBlock }) {
  return <>
    {block.note && <p className="cp-block-note">{block.note}</p>}
    {block.figures?.length ? <dl className="cp-figures">{block.figures.map(figure =>
      <div key={figure.label}><dt>{figure.label}</dt><dd>{figure.value}</dd></div>)}</dl> : null}
    {block.lines?.map((line, index) => <p className="cp-block-line" key={index}>{line}</p>)}
    {block.evidence?.length ? <ul className="cp-evidence-list">{block.evidence.map(item =>
      <li key={item.iq}>
        <span className={`cp-ev-badge${item.status === "unavailable" ? " cp-ev-off" : ""}`}>{item.iq.replace(" IQ", "")}</span>
        <span>{item.text}</span>
      </li>)}</ul> : null}
  </>;
}

function AnswerBlockView({ block }: { block: AnswerBlock }) {
  if (!block.note && !block.figures?.length && !block.lines?.length && !block.evidence?.length) return null;
  if (block.collapsible) {
    return <details className="cp-block cp-block-fold"><summary>{block.title}</summary><BlockBody block={block} /></details>;
  }
  return <section className="cp-block"><h4>{block.title}</h4><BlockBody block={block} /></section>;
}

export function Dashboard({ active, bankName, userName = "" }: { active: boolean; bankName: string; userName?: string }) {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [triageOpen, setTriageOpen] = useState(false);
  const [outreach, setOutreach] = useState<OutreachResult | null>(null);
  const [wsId, setWsId] = useState<string | null>(null);
  const [guardApproved, setGuardApproved] = useState<Record<string, boolean>>({});
  const [board, setBoard] = useState<Record<string, BoardClient>>({});
  const [mstats, setMstats] = useState<MissionStats | null>(null);
  const [missionKind, setMissionKind] = useState<MissionKind>("briefing");
  const missionRef = useRef<HTMLDivElement>(null);
  const loadStats = () => { coverageGet<MissionStats>("/api/missions/stats").then(setMstats).catch(() => undefined); };
  useEffect(() => {
    if (!active) return;
    coverageGet<{ clients: BoardClient[] }>("/api/missions/board")
      .then((b) => setBoard(Object.fromEntries(b.clients.map((x) => [x.id, x])))).catch(() => undefined);
    loadStats();
  }, [active]);
  const openMission = (k: MissionKind) => {
    setMissionKind(k);
    window.setTimeout(() => missionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 40);
  };
  const disagree = Object.values(board).filter((b) => b.conflict).length;
  const [evidence, setEvidence] = useState<Record<string, EvidenceSnap>>({});
  const latestChange = mstats?.recent.find((r) => r.rulesFlag === "CHANGED");
  useEffect(() => {
    if (!active || overview) return;
    coverageGet<Overview>("/api/coverage/overview").then(setOverview).catch(() => undefined);
  }, [active, overview]);
  const openClient = (id: string) => { setTriageOpen(false); setSelectedId(id); setWsId(id); };
  const [selectedId, setSelectedId] = useState(companies[0].id);
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; direction: 1 | -1 }>({ key: "exposureCad", direction: -1 });
  const chat = useChatSplit("cmci.dash.chat", 34, 22, 60);
  const chatOpen = chat.open;
  const [view, setView] = useState<"accounts" | "coverage">("accounts");
  const [conversations, setConversations] = useState<Record<string, Exchange[]>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [skill, setSkill] = useState<"stress" | "papers" | null>(null);
  const catalogue = useSkillCatalogue();
  const heroId = catalogue?.client?.id ?? "CLI-1001";
  const shell = useRef<HTMLDivElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const selected = companies.find(company => company.id === selectedId)!;
  useEffect(() => {
    if (!active || evidence[selectedId]) return;
    coverageGet<EvidenceSnap>(`/api/missions/evidence/${selectedId}`)
      .then((e) => { if (e?.layers) setEvidence((prev) => ({ ...prev, [e.clientId]: e })); }).catch(() => undefined);
  }, [active, selectedId]);
  const conversation = conversations[selectedId] ?? [];
  const visible = companies.filter(company =>
    (sector === "all" || company.sector === sector) &&
    `${company.name} ${company.id} ${company.sector}`.toLowerCase().includes(search.trim().toLowerCase()),
  ).sort((a, b) => {
    const left = a[sort.key], right = b[sort.key];
    if (left === null) return right === null ? 0 : 1;
    if (right === null) return -1;
    return (typeof left === "number" && typeof right === "number" ? left - right : String(left).localeCompare(String(right))) * sort.direction;
  });
  const exposure = sum(visible, "exposureCad");
  const periods = [...new Set(visible.map(company => company.revenuePeriod))];
  const sectors = [...new Set(companies.map(company => company.sector))].sort();
  const sectorTotals = sectors.map(name => ({ name, ...sum(visible.filter(company => company.sector === name), "exposureCad") }))
    .filter(item => visible.some(company => company.sector === item.name));
  const maturity = new Map<string, number>();
  visible.forEach(company => company.maturityCad.forEach(item => maturity.set(item.year, (maturity.get(item.year) ?? 0) + item.amount)));
  const maturityRows = [...maturity.entries()].sort(([a], [b]) => a.localeCompare(b));
  const maxMaturity = Math.max(1, ...maturityRows.map(([, amount]) => amount));
  const missingMaturity = visible.filter(company => !company.maturityCad.length).length;

  useEffect(() => {
    if (active && chatOpen && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [active, chatOpen, selectedId, conversation.length]);

  function ask(question: string) {
    if (!question.trim()) return;
    const exchange = { question: question.trim(), answer: buildAnswer(selected, question.trim()) };
    setConversations(previous => ({ ...previous, [selectedId]: [...(previous[selectedId] ?? []), exchange] }));
    chat.setOpen(true);
  }
  function sortBy(key: SortKey) {
    setSort(previous => ({ key, direction: previous.key === key && previous.direction === 1 ? -1 : 1 }));
  }
  const columns: { key: SortKey; label: string }[] = [
    { key: "name", label: "Company" }, { key: "sector", label: "Sector" },
    { key: "exposureCad", label: "Exposure" }, { key: "commitmentCad", label: "Facility amount" },
    { key: "revenueCad", label: "Revenue · FY26 YTD" }, { key: "walletPercent", label: "Wallet %" },
    { key: "utilizationPercent", label: "Limit used %" },
  ];

  return (
    <section className="cp-dashboard" hidden={!active} aria-label="Portfolio snapshot dashboard">
      <header className="cp-header">
        <div><div className="cp-eyebrow">{bankName} · Client Intelligence</div><h1>Portfolio at a glance</h1>
          <p>Ten-company coverage universe · Decision support</p></div>
        <div className="cp-header-meta"><span className="cp-badge">Synthetic demo</span>
          <span>Snapshot <time dateTime={snapshotAsOf}>{snapshotAsOf}</time></span>
          <SplitToggle split={chat} controls={wsId ? "cv-ai-panel" : "cp-snapshot-chat"} /></div>
      </header>
      <div className="cp-disclaimer">{snapshotDisclaimer}</div>
      {wsId ? (
        <ClientWorkspace clientId={wsId} onBack={() => setWsId(null)} split={chat}
                         guardApproved={!!guardApproved[wsId]}
                         onGuardApproved={() => setGuardApproved((g) => ({ ...g, [wsId]: true }))} />
      ) : (
      <>
      <nav className="cp-views" aria-label="Dashboard views">
        <div role="tablist" aria-label="Dashboard views">
          {([["accounts", "Accounts overview", "Market pulse, alerts and today's actions"], ["coverage", "Coverage overview", "Portfolio table, concentration and company evidence"]] as const).map(([id, label, hint]) => (
            <button key={id} type="button" role="tab" id={`cp-tab-${id}`} aria-selected={view === id} aria-controls="cp-view-panel"
                    className={view === id ? "on" : ""} onClick={() => setView(id)}>
              <b>{label}</b><small>{hint}</small>
            </button>
          ))}
        </div>
      </nav>
      <div ref={shell} className={`cp-workspace${chatOpen ? "" : " cp-chat-collapsed"}`} style={{ "--split-w": `${chat.width}%` } as CSSProperties}>
        <main className="cp-portfolio" id="cp-view-panel" role="tabpanel" aria-labelledby={`cp-tab-${view}`} tabIndex={0}>
          {view === "accounts" ? (overview
            ? <CoverageOverview data={overview} userName={userName} onReviewImpact={() => setTriageOpen(true)} onOpenClient={openClient} onShowCoverage={() => setView("coverage")} />
            : <div aria-busy="true" className="cv-overview"><div className="skel skel-title" /><div className="skel skel-card" /></div>) : <div className="cp-view-coverage">
          <div className="cp-section-heading"><div><h2>Coverage overview</h2><p>All monetary figures in CAD millions · USD unavailable (no FX rate) · <b className="cp-det">Deterministic</b> governed snapshot - an API returns all of this, no agent involved</p></div>
            <span className="cp-badge">{visible.length} of {companies.length} companies</span></div>
          <div className="cp-filters">
            <label>Search coverage<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Company, ID or sector" /></label>
            <label>Sector<select value={sector} onChange={event => setSector(event.target.value)}><option value="all">All sectors</option>{sectors.map(name => <option key={name}>{name}</option>)}</select></label>
            <button type="button" onClick={() => { setSearch(""); setSector("all"); }}>Reset filters</button>
          </div>
          <div className="cp-kpis">
            {([{ key: "exposureCad", label: "Drawn / risk exposure" }, { key: "commitmentCad", label: "Facility amount" }, { key: "revenueCad", label: "Relationship revenue" }] as const).map(metric => {
              const total = sum(visible, metric.key);
              const mixedPeriod = metric.key === "revenueCad" && periods.length > 1;
              return <article className="cp-card cp-kpi" key={metric.key}><h3>{metric.label}</h3>
                <strong>{mixedPeriod ? "Mixed FY scopes" : money(total.value)}</strong><span>CAD millions · filtered companies</span>
                <small>{mixedPeriod ? "Not summed across different periods" : `${total.known}/${visible.length} values available${total.known < visible.length ? " · partial subtotal" : ""}`}</small>
              </article>;
            })}
            <article className="cp-card cp-kpi cp-kpi-agent" title="Decided agent missions where the agent's call differed from the rules-based answer (audit log, all replicas)">
              <h3>Agent changed the answer</h3>
              <strong>{mstats ? `${mstats.changed} of ${mstats.decided}` : "–"}</strong>
              <span>decided agent missions · audit log</span>
              <small>{Object.keys(board).length ? `Business lines disagree on ${disagree} of ${Object.keys(board).length} clients` : " "}
                {latestChange ? ` · latest: ${latestChange.client.split(" ")[0]} - ${latestChange.rulesReason}` : ""}</small>
            </article>
          </div>
          <p className="cp-note">Revenue: {periods.length ? periods.join("; ") : "no companies in filter"}. Relationship revenue, not issuer sales. Facility amounts include uncommitted and derivative lines; not all legally committed lending.</p>
          <div className="cp-card cp-table-card">
            <div className="cp-table-scroll" tabIndex={0} role="region" aria-label="Coverage table, scroll horizontally for all metrics">
              <table><caption>Company coverage · CAD millions unless % · select a company for evidence</caption>
                <thead><tr>{columns.map(column => <th key={column.key} scope="col" aria-sort={sort.key === column.key ? sort.direction === 1 ? "ascending" : "descending" : "none"}>
                  <button type="button" onClick={() => sortBy(column.key)}>{column.label} {sort.key === column.key ? sort.direction === 1 ? "↑" : "↓" : "↕"}</button>
                </th>)}<th scope="col" title="Fabric IQ line_positions: do DCM, Credit, Markets, the Control Room and KYC agree?">Business lines</th></tr></thead>
                <tbody>{visible.map(company => <tr key={company.id} className={selectedId === company.id ? "cp-selected" : ""}>
                  <th scope="row"><button type="button" aria-pressed={selectedId === company.id} onClick={() => setSelectedId(company.id)}>{company.name}<small>{company.id}{selectedId === company.id ? " · Selected" : ""}</small></button></th>
                  <td>{company.sector}</td><td>{money(company.exposureCad)}</td><td>{money(company.commitmentCad)}</td><td>{money(company.revenueCad)}</td>
                  <td>{percent(company.walletPercent)}</td><td>{percent(company.utilizationPercent)}</td>
                  <td>{board[company.id]
                    ? <button type="button" className={`cp-lines ${board[company.id].conflict ? "cp-lines-bad" : "cp-lines-ok"}`}
                              title={board[company.id].lines.map((l) => `${l.line}: ${l.stance}`).join("\n")}
                              onClick={() => { setSelectedId(company.id); openMission("opportunities"); }}>
                        {board[company.id].conflict ? "Disagree" : "Agree"}<small>{board[company.id].lines.length} lines</small>
                      </button>
                    : <span className="cp-muted">–</span>}</td>
                </tr>)}</tbody>
              </table>
            </div>
            {!visible.length && <p className="cp-empty" role="status">No companies match. Reset filters to restore coverage; selected-company context is preserved.</p>}
          </div>
          <div className="cp-chart-grid">
            <article className="cp-card"><h3>Sector concentration</h3><p>Share of filtered known CAD exposure</p>
              {sectorTotals.map(item => <div className="cp-chart-row" key={item.name}><div><span>{item.name}</span><strong>{item.value === null || exposure.value === null || exposure.value === 0 ? "Unavailable" : percent(item.value / exposure.value * 100)}</strong></div>
                <div className="cp-track"><span style={{ width: `${item.value !== null && exposure.value ? item.value / exposure.value * 100 : 0}%` }} /></div><small>CAD {money(item.value)}m</small></div>)}
              {!sectorTotals.length && <p>No concentration data for this filter.</p>}
              {exposure.known < visible.length && <p className="cp-note">Partial exposure coverage; missing values excluded, not treated as zero.</p>}
            </article>
            <article className="cp-card"><h3>Facility maturity ladder</h3><p>Filtered facility amounts · CAD millions · calendar year</p>
              {maturityRows.map(([year, amount]) => <div className="cp-chart-row" key={year}><div><span>{year}</span><strong>{money(amount)}</strong></div>
                <div className="cp-track"><span style={{ width: `${amount / maxMaturity * 100}%` }} /></div></div>)}
              {!maturityRows.length && <p>Maturity data unavailable for this filter.</p>}
              {!!missingMaturity && <p className="cp-note">{missingMaturity} companies without maturity data; totals are partial.</p>}
              <p className="cp-note">Undated facility rows treated as this snapshot. Includes letters of credit, uncommitted and derivative lines; not drawn exposure, issuer-wide debt or refinancing pipeline.</p>
            </article>
          </div>
          <section className="cp-detail" aria-label="Selected company evidence">
            <div className="cp-section-heading"><div><div className="cp-eyebrow">Selected relationship</div><h2>{selected.name}</h2><p>{selected.sector} · {selected.id} · As of {selected.asOf}</p></div></div>
            {!visible.some(company => company.id === selectedId) && <p className="cp-outside" role="status">Selected company is outside the current filter. Evidence and chat remain scoped to {selected.name}; filtered totals exclude it.</p>}
            <div className="cp-actions cp-actions-split">
              {missionActions.map(([label, kind]) => <button type="button" key={kind} className={`cp-agent-btn${missionKind === kind ? " on" : ""}`} onClick={() => openMission(kind)}>{label}<small>agent mission</small></button>)}
              <button type="button" className="cp-lookup-btn" onClick={() => ask("maturity")}>Explain maturities<small>snapshot lookup · no agent</small></button>
            </div>
            <div ref={missionRef} className="cp-mission-wrap">
              <MissionPanel clientId={selectedId} kind={missionKind} onKind={setMissionKind} onDecided={loadStats}
                            onEvidence={(snap) => setEvidence((prev) => ({ ...prev, [snap.clientId]: snap }))} />
            </div>
            <div className="cp-skill-actions">
              <button type="button" className="cp-skill" onClick={() => setSkill("stress")}>Stress-test it</button>
              <button type="button" className="cp-skill" onClick={() => setSkill("papers")}>
                {selected.id === heroId ? "Draft the approval papers" : "Draft the credit papers"}
              </button>
              <span className="cp-skill-note">
                {selected.id === heroId
                  ? "Live deal: full CP-005 pro-forma and the three approval papers."
                  : "From this company's covenants, limits, rating and findings · drafts with human sign-off."}
              </span>
            </div>
            <div className="cp-chart-grid">
              <article className="cp-card"><h3>Opportunity · not approval</h3><p>{selected.opportunity}</p></article>
              <article className="cp-card"><h3>Risk & constraints</h3><p>{selected.risk}</p></article>
            </div>
            {evidence[selectedId]?.layers
              ? <h3 className="cp-recorded-head">Evidence by layer · live <span>what {evidence[selectedId].agent} actually retrieved on its last mission for {selected.name} · {new Date(evidence[selectedId].at).toLocaleString("en-CA")}</span></h3>
              : <h3 className="cp-recorded-head">Recorded evidence <span>snapshot records, not live retrievals - run an agent mission above and these cards fill with what the agent actually retrieved</span></h3>}
            <div className="cp-evidence-grid">{EV_LAYERS.map((layer) => (
              <EvidenceCard key={layer.id} layer={layer} snap={evidence[selectedId] ?? null}
                            recorded={selected.evidence.find((e) => e.iq === layer.recorded)} onRun={() => openMission(missionKind)} />
            ))}</div>
            <details className="cp-card"><summary>Source scope & data quality</summary><p>{snapshotUnits}</p><p>{selected.commitmentBasis}</p><p>{selected.maturityBasis}</p><p>{selected.revenuePeriod}</p>
              <p>Wallet share uses wallet-table revenue / estimated street wallet; limit utilization uses reported utilized / single-name limit. Neither is a portfolio average.</p>
              {selected.dataQuality.length ? <ul>{selected.dataQuality.map(item => <li key={item}>{item}</li>)}</ul> : <p>No additional source caveats recorded; all evidence remains synthetic.</p>}
              <ul>{selected.sources.map(source => <li key={source}>{source}</li>)}</ul>
            </details>
          </section>
          </div>}
        </main>
        {chatOpen ? <SplitHandle split={chat} container={shell} controls="cp-snapshot-chat" /> : <SplitRail split={chat} controls="cp-snapshot-chat" />}
        <aside id="cp-snapshot-chat" className="cp-chat" hidden={!chatOpen} aria-label="Independent company conversation">
          <header className="cp-chat-header"><div className="cp-eyebrow">Snapshot lookup · no agent</div><h2>{selected.name}</h2><p>As of {selected.asOf} · keyword lookup over the governed snapshot. For live, grounded answers run an agent mission.</p></header>
          <div className="cp-chat-log" ref={log} role="log" aria-label={`Answers for ${selected.name}`} aria-live="polite" tabIndex={0}>
            {!conversation.length && <div className="cp-chat-welcome"><h3>Start with the evidence.</h3><p>Ask for a briefing, opportunities, risks or maturity. Other freeform questions receive a scope explanation, not invented answers.</p><p>This company's conversation stays separate from other companies and live chat.</p></div>}
            {conversation.map((exchange, index) => <div className="cp-exchange" key={index}><div className="cp-question"><strong>You</strong><p>{exchange.question}</p></div><article className="cp-answer"><header className="cp-answer-head"><strong>{exchange.answer.company}</strong><span className="cp-answer-meta">Snapshot {exchange.answer.asOf}</span></header>{exchange.answer.blocks.map(block => <AnswerBlockView block={block} key={block.title} />)}<p className="cp-footnote">{exchange.answer.footnote}</p></article></div>)}
          </div>
          <div className="cp-composer"><div className="cp-actions">{actions.map(([label, question]) => <button type="button" key={question} onClick={() => ask(question)}>{label}</button>)}</div>
            <form onSubmit={event => { event.preventDefault(); ask(drafts[selectedId] ?? ""); setDrafts(previous => ({ ...previous, [selectedId]: "" })); }}>
              <label htmlFor="cp-question-input">Ask about {selected.name}</label>
              <textarea id="cp-question-input" rows={3} value={drafts[selectedId] ?? ""} placeholder="e.g. What are the key risks?" onChange={event => setDrafts(previous => ({ ...previous, [selectedId]: event.target.value }))} />
              <div className="cp-submit-row"><small>Snapshot lookup - deterministic, no agent</small><button className="cp-primary" type="submit" disabled={!(drafts[selectedId] ?? "").trim()}>Ask</button></div>
            </form>
          </div>
        </aside>
      </div>
      </>
      )}

      {triageOpen && (
        <TriageFlow onClose={() => setTriageOpen(false)} onOpenClient={openClient}
                    approved={outreach} onApproved={setOutreach} />
      )}

      {skill === "stress" && (
        <SkillModal title={`Covenant stress test — ${selected.name}`} onClose={() => setSkill(null)} wide={selected.id !== heroId}>
          {selected.id === heroId && catalogue
            ? <ProFormaSkill catalogue={catalogue} result={null}
                onRun={(incrementalM, ebitdaShockPct) =>
                  apiPost<ProFormaResult>("/api/skills/proforma", { incrementalM, ebitdaShockPct })} />
            : <ClientStressSkill clientId={selected.id} />}
        </SkillModal>
      )}
      {skill === "papers" && (
        <SkillModal title={`${selected.id === heroId ? "Approval papers" : "Credit papers"} — ${selected.name}`} onClose={() => setSkill(null)} wide>
          {selected.id === heroId && catalogue
            ? <PapersSkill catalogue={catalogue} />
            : <ClientPapersSkill clientId={selected.id} />}
        </SkillModal>
      )}
    </section>
  );
}
