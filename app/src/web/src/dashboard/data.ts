import snapshot from "./snapshot.json";

export interface Company {
  id: string;
  name: string;
  sector: string;
  asOf: string;
  /** USD millions. Null means unavailable, never zero or a CAD amount. */
  exposure: number | null;
  commitment: number | null;
  revenue: number | null;
  revenuePeriod: string;
  walletPercent: number | null;
  limit: number | null;
  utilizationPercent: number | null;
  maturity: { year: string; amount: number }[];
  currency: string;
  fxRate: number | null;
  usdUnavailableReason: string;
  /** CAD millions; explicitly separate from the required USD contract. */
  exposureCad: number | null;
  commitmentCad: number | null;
  revenueCad: number | null;
  limitCad: number | null;
  limitUtilizedCad: number | null;
  walletRevenueCad: number | null;
  streetWalletCad: number | null;
  maturityCad: { year: string; amount: number }[];
  maturityBasis: string;
  commitmentBasis: string;
  evidence: { iq: string; status: string; text: string }[];
  opportunity: string;
  risk: string;
  dataQuality: string[];
  sources: string[];
}

export const companies: Company[] = snapshot.companies;
export const snapshotAsOf: string = snapshot.snapshotAsOf;
export const snapshotDisclaimer: string = snapshot.disclaimer;
export const snapshotUnits: string = snapshot.units;

const money = (amount: number | null): string =>
  amount === null ? "unavailable" : `CAD ${amount.toFixed(1)}m`;
const percent = (amount: number | null): string =>
  amount === null ? "unavailable" : `${amount.toFixed(1)}%`;
const normalize = (text: string): string =>
  text.toLowerCase().replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();

function topicFor(question: string, company: Company): string | undefined {
  let query = normalize(question);
  // Only whole supported requests are recognized, not arbitrary keyword matches.
  for (const label of [company.name, company.id]) {
    const normalized = normalize(label);
    if (query.endsWith(` for ${normalized}`)) query = query.slice(0, -normalized.length - 5);
    if (query.endsWith(` about ${normalized}`)) query = query.slice(0, -normalized.length - 7);
  }
  query = query.replace(/^(please )?(give me |show me |show |prepare |summarize |summarise |what are |what is )?(the |a |an )?/, "");
  const topics: Record<string, string[]> = {
    briefing: ["brief", "briefing", "client brief", "company brief", "client briefing", "summary", "overview", "snapshot", "meeting brief", "prepare a briefing", "prep me"],
    opportunities: ["opportunity", "opportunities", "growth opportunities", "cross sell opportunities", "wallet opportunities", "biggest opportunities", "where are the biggest opportunities"],
    risks: ["risk", "risks", "key risks", "credit risks", "risk summary"],
    maturity: ["maturity", "maturities", "maturity profile", "maturity ladder", "debt maturities", "upcoming maturities", "what matures next"],
  };
  return Object.keys(topics).find((topic) => topics[topic].includes(query));
}

export interface AnswerFigure { label: string; value: string }
export interface AnswerBlock {
  title: string;
  figures?: AnswerFigure[];
  lines?: string[];
  evidence?: { iq: string; status: string; text: string }[];
  /** Small qualifying note shown once under the block heading. */
  note?: string;
  /** Rendered folded away so provenance stays available without crowding. */
  collapsible?: boolean;
}
export interface Answer {
  company: string;
  asOf: string;
  supported: boolean;
  blocks: AnswerBlock[];
  footnote: string;
}

const SCOPE = "Supported topics: briefing, opportunities, risks and maturity only. Ask for one supported topic; freeform analysis, live news and external facts are unavailable.";
// Stated once per answer instead of on every line, so the reader can actually
// see the numbers. The dashboard header carries the full disclaimer.
const EVIDENCE_NOTE = "Records held in the snapshot; not live retrievals.";
const FOOTNOTE = "SYNTHETIC DEMO ONLY: every figure and record is invented. Not investment advice.";
const stripLiveNote = (text: string): string => text.replace(/\s*Not a live retrieval\.\s*$/, "");

/** Pure local lookup: no model, service, simulated tool execution or current clock. */
export function buildAnswer(company: Company | string, question: string): Answer {
  // Resolve the canonical snapshot entry, never trust caller-supplied financial fields.
  const id = typeof company === "string" ? company : company.id;
  const cached = snapshot.companies.find((entry) => entry.id === id || entry.name === id);
  if (!cached) {
    return {
      company: "Company not in this snapshot", asOf: snapshotAsOf, supported: false,
      blocks: [
        { title: "Supported questions", lines: [SCOPE] },
        { title: "Sources", collapsible: true, lines: ["local snapshot.json generated from data/fabric-iq CSVs and data/scenario_facts.py", snapshotUnits] },
      ],
      footnote: FOOTNOTE,
    };
  }
  const topic = topicFor(question, cached);
  const position: AnswerBlock = {
    title: "Position",
    figures: [
      { label: "Sector", value: cached.sector },
      { label: "Exposure", value: money(cached.exposureCad) },
      { label: "Facility amount", value: money(cached.commitmentCad) },
      { label: `Revenue · ${cached.revenuePeriod.split(" (")[0]}`, value: money(cached.revenueCad) },
      { label: "Wallet share (estimated)", value: percent(cached.walletPercent) },
      { label: "Single-name limit", value: `${money(cached.limitCad)} · ${percent(cached.utilizationPercent)} used` },
    ],
  };
  const maturities: AnswerBlock = {
    title: "Facility maturities",
    figures: cached.maturityCad.map((item) => ({ label: item.year, value: money(item.amount) })),
    note: cached.maturityCad.length ? undefined : "No maturity rows in this snapshot.",
  };
  const evidence: AnswerBlock = {
    title: "Evidence", note: EVIDENCE_NOTE,
    evidence: cached.evidence.map((item) => ({ ...item, text: stripLiveNote(item.text) })),
  };
  const basis: AnswerBlock = {
    title: "Basis and caveats", collapsible: true,
    lines: [
      cached.commitmentBasis,
      `Revenue period: ${cached.revenuePeriod}; relationship revenue, not issuer sales.`,
      `Wallet share uses wallet-table revenue ${money(cached.walletRevenueCad)} over estimated street wallet ${money(cached.streetWalletCad)}; not an average of product percentages.`,
      `Reported limit utilised: ${money(cached.limitUtilizedCad)}.`,
      cached.maturityBasis,
      "USD amounts unavailable (no supported FX rate); an empty USD array does not mean no maturities.",
      ...cached.dataQuality,
      snapshotUnits,
    ],
  };
  const sources: AnswerBlock = { title: "Sources", collapsible: true, lines: cached.sources };
  const blocks = topic === "briefing"
    ? [position, { title: "Opportunities", lines: [cached.opportunity] }, { title: "Risks", lines: [cached.risk] }, maturities, evidence, basis, sources]
    : topic === "opportunities"
      ? [{ title: "Opportunities", lines: [cached.opportunity] }, { title: "Constraints", lines: [cached.risk] }, evidence, basis, sources]
      : topic === "risks"
        ? [{ title: "Risks", lines: [cached.risk] }, evidence, basis, sources]
        : topic === "maturity"
          ? [maturities, basis, sources]
          : [{ title: "Supported questions", lines: [SCOPE] }, sources];
  return { company: cached.name, asOf: cached.asOf, supported: Boolean(topic), blocks, footnote: FOOTNOTE };
}

/** Flat transcript of the same answer: used for assertions and plain-text copy. */
export function answerQuestion(company: Company | string, question: string): string {
  const answer = buildAnswer(company, question);
  const parts = [`${answer.company} — snapshot ${answer.asOf}`];
  for (const block of answer.blocks) {
    const body: string[] = [];
    if (block.note) body.push(block.note);
    block.figures?.forEach((figure) => body.push(`${figure.label}: ${figure.value}`));
    block.lines?.forEach((line) => body.push(line));
    block.evidence?.forEach((item) => body.push(`${item.iq} (${item.status}): ${item.text}`));
    if (!body.length) continue;
    const heading = block.title === "Sources" ? "Sources:" : block.title;
    parts.push(`${heading}\n${body.map((line) => `  ${line}`).join("\n")}`);
  }
  parts.push(answer.footnote);
  return parts.join("\n\n");
}
