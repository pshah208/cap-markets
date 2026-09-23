import { useEffect, useRef, useState, type CSSProperties } from "react";
import { buildAnswer, companies, snapshotAsOf, snapshotDisclaimer, snapshotUnits, type Answer, type AnswerBlock, type Company } from "./data";
import "./dashboard.css";

type SortKey = "name" | "sector" | "exposureCad" | "commitmentCad" | "revenueCad" | "walletPercent" | "utilizationPercent";
type Exchange = { question: string; answer: Answer };
const number = new Intl.NumberFormat("en-CA", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const money = (value: number | null) => value === null ? "Unavailable" : number.format(value);
const percent = (value: number | null) => value === null ? "Unavailable" : `${value.toFixed(1)}%`;
const clamp = (value: number) => Math.min(80, Math.max(20, value));
const actions = [
  ["Prepare briefing", "briefing"],
  ["Explore opportunities", "opportunities"],
  ["Review risks", "risks"],
  ["Explain maturities", "maturity"],
] as const;

function initialTheme(): "light" | "dark" {
  const query = new URLSearchParams(window.location.search).get("scoutTheme");
  return query === "light" || query === "dark" ? query
    : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
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

export function Dashboard({ active }: { active: boolean }) {
  const [theme, setTheme] = useState(initialTheme);
  const [selectedId, setSelectedId] = useState(companies[0].id);
  const [search, setSearch] = useState("");
  const [sector, setSector] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; direction: 1 | -1 }>({ key: "exposureCad", direction: -1 });
  const [chatOpen, setChatOpen] = useState(true);
  const [chatWidth, setChatWidth] = useState(36);
  const [conversations, setConversations] = useState<Record<string, Exchange[]>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const shell = useRef<HTMLDivElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const selected = companies.find(company => company.id === selectedId)!;
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
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const update = () => setTheme(initialTheme());
    media.addEventListener("change", update);
    window.addEventListener("popstate", update);
    return () => { media.removeEventListener("change", update); window.removeEventListener("popstate", update); };
  }, []);
  useEffect(() => {
    if (active && chatOpen && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [active, chatOpen, selectedId, conversation.length]);

  function ask(question: string) {
    if (!question.trim()) return;
    const exchange = { question: question.trim(), answer: buildAnswer(selected, question.trim()) };
    setConversations(previous => ({ ...previous, [selectedId]: [...(previous[selectedId] ?? []), exchange] }));
    setChatOpen(true);
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
    <section className="cp-dashboard" data-theme={theme} hidden={!active} aria-label="Cached portfolio dashboard">
      <header className="cp-header">
        <div><div className="cp-eyebrow">BMO Capital Markets · Client Intelligence</div><h1>Portfolio at a glance</h1>
          <p>Ten-company coverage universe · Offline decision support</p></div>
        <div className="cp-header-meta"><span className="cp-badge">Synthetic demo</span>
          <span>Snapshot <time dateTime={snapshotAsOf}>{snapshotAsOf}</time></span>
          <button type="button" aria-expanded={chatOpen} aria-controls="cp-cached-chat" onClick={() => setChatOpen(!chatOpen)}>
            {chatOpen ? "Collapse chat" : "Expand chat"}
          </button></div>
      </header>
      <div className="cp-disclaimer">{snapshotDisclaimer}</div>
      <div ref={shell} className={`cp-workspace${chatOpen ? "" : " cp-chat-collapsed"}`} style={{ "--cp-chat-width": `${chatWidth}vw` } as CSSProperties}>
        <main className="cp-portfolio" tabIndex={0} aria-label="Portfolio, independently scrollable">
          <div className="cp-section-heading"><div><h2>Coverage overview</h2><p>All monetary figures in CAD millions · USD unavailable (no FX rate)</p></div>
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
          </div>
          <p className="cp-note">Revenue: {periods.length ? periods.join("; ") : "no companies in filter"}. Relationship revenue, not issuer sales. Facility amounts include uncommitted and derivative lines; not all legally committed lending.</p>
          <div className="cp-card cp-table-card">
            <div className="cp-table-scroll" tabIndex={0} role="region" aria-label="Coverage table, scroll horizontally for all metrics">
              <table><caption>Company coverage · CAD millions unless % · select a company for evidence</caption>
                <thead><tr>{columns.map(column => <th key={column.key} scope="col" aria-sort={sort.key === column.key ? sort.direction === 1 ? "ascending" : "descending" : "none"}>
                  <button type="button" onClick={() => sortBy(column.key)}>{column.label} {sort.key === column.key ? sort.direction === 1 ? "↑" : "↓" : "↕"}</button>
                </th>)}</tr></thead>
                <tbody>{visible.map(company => <tr key={company.id} className={selectedId === company.id ? "cp-selected" : ""}>
                  <th scope="row"><button type="button" aria-pressed={selectedId === company.id} onClick={() => setSelectedId(company.id)}>{company.name}<small>{company.id}{selectedId === company.id ? " · Selected" : ""}</small></button></th>
                  <td>{company.sector}</td><td>{money(company.exposureCad)}</td><td>{money(company.commitmentCad)}</td><td>{money(company.revenueCad)}</td>
                  <td>{percent(company.walletPercent)}</td><td>{percent(company.utilizationPercent)}</td>
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
            <div className="cp-actions">{actions.map(([label, question]) => <button type="button" key={question} onClick={() => ask(question)}>{label} ↗</button>)}</div>
            <div className="cp-chart-grid">
              <article className="cp-card"><h3>Opportunity · not approval</h3><p>{selected.opportunity}</p></article>
              <article className="cp-card"><h3>Risk & constraints</h3><p>{selected.risk}</p></article>
            </div>
            <div className="cp-evidence-grid">{selected.evidence.map(item => <article className="cp-card" key={item.iq}><div className="cp-evidence-title"><h3>{item.iq}</h3><span className="cp-badge">{item.status}</span></div><p>{item.text}</p></article>)}</div>
            <details className="cp-card"><summary>Source scope & data quality</summary><p>{snapshotUnits}</p><p>{selected.commitmentBasis}</p><p>{selected.maturityBasis}</p><p>{selected.revenuePeriod}</p>
              <p>Wallet share uses wallet-table revenue / estimated street wallet; limit utilization uses reported utilized / single-name limit. Neither is a portfolio average.</p>
              {selected.dataQuality.length ? <ul>{selected.dataQuality.map(item => <li key={item}>{item}</li>)}</ul> : <p>No additional source caveats recorded; all evidence remains synthetic.</p>}
              <ul>{selected.sources.map(source => <li key={source}>{source}</li>)}</ul>
            </details>
          </section>
        </main>
        {chatOpen && <div className="cp-divider" role="separator" tabIndex={0} aria-label="Resize cached chat; arrows adjust two viewport percentage points, Home minimum, End maximum, Enter reset"
          aria-orientation="vertical" aria-valuemin={20} aria-valuemax={80} aria-valuenow={chatWidth} aria-valuetext={`${chatWidth} viewport percent chat width`} aria-controls="cp-cached-chat"
          onDoubleClick={() => setChatWidth(36)}
          onKeyDown={event => {
            const next = event.key === "ArrowLeft" || event.key === "ArrowUp" ? chatWidth + 2
              : event.key === "ArrowRight" || event.key === "ArrowDown" ? chatWidth - 2
              : event.key === "Home" ? 20 : event.key === "End" ? 80 : event.key === "Enter" ? 36 : null;
            if (next !== null) { event.preventDefault(); setChatWidth(clamp(next)); }
          }}
          onPointerDown={event => { event.preventDefault(); event.currentTarget.focus(); event.currentTarget.setPointerCapture(event.pointerId); }}
          onPointerMove={event => {
            if (event.currentTarget.hasPointerCapture(event.pointerId) && shell.current) setChatWidth(clamp(Math.round((shell.current.getBoundingClientRect().right - event.clientX) / window.innerWidth * 100)));
          }}
          onPointerUp={event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        ><span /></div>}
        <aside id="cp-cached-chat" className="cp-chat" hidden={!chatOpen} aria-label="Independent cached company conversation">
          <header className="cp-chat-header"><div className="cp-eyebrow">Cached conversation · no API calls</div><h2>{selected.name}</h2><p>As of {selected.asOf}</p></header>
          <div className="cp-chat-log" ref={log} role="log" aria-label={`Cached answers for ${selected.name}`} aria-live="polite" tabIndex={0}>
            {!conversation.length && <div className="cp-chat-welcome"><span className="cp-badge">Local snapshot</span><h3>Start with the evidence.</h3><p>Ask for a briefing, opportunities, risks or maturity. Other freeform questions receive a scope explanation, not invented answers.</p><p>This company's conversation stays separate from other companies and live chat.</p></div>}
            {conversation.map((exchange, index) => <div className="cp-exchange" key={index}><div className="cp-question"><strong>You</strong><p>{exchange.question}</p></div><article className="cp-answer"><header className="cp-answer-head"><strong>{exchange.answer.company}</strong><span className="cp-answer-meta">Snapshot {exchange.answer.asOf}</span></header>{exchange.answer.blocks.map(block => <AnswerBlockView block={block} key={block.title} />)}<p className="cp-footnote">{exchange.answer.footnote}</p></article></div>)}
          </div>
          <div className="cp-composer"><div className="cp-actions">{actions.map(([label, question]) => <button type="button" key={question} onClick={() => ask(question)}>{label}</button>)}</div>
            <form onSubmit={event => { event.preventDefault(); ask(drafts[selectedId] ?? ""); setDrafts(previous => ({ ...previous, [selectedId]: "" })); }}>
              <label htmlFor="cp-question-input">Ask about {selected.name}</label>
              <textarea id="cp-question-input" rows={3} value={drafts[selectedId] ?? ""} placeholder="e.g. What are the key risks?" onChange={event => setDrafts(previous => ({ ...previous, [selectedId]: event.target.value }))} />
              <div className="cp-submit-row"><small>Local answers only · no live retrieval</small><button className="cp-primary" type="submit" disabled={!(drafts[selectedId] ?? "").trim()}>Ask</button></div>
            </form>
          </div>
        </aside>
      </div>
    </section>
  );
}
