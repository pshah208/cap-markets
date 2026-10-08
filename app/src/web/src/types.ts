export type IQId = "work" | "fabric" | "foundry" | "web";
export type IQStatus = "idle" | "active" | "done";

export interface IQMeta {
  id: IQId;
  name: string;
  source: string;
  blurb: string;
}

export interface IQState extends IQMeta {
  status: IQStatus;
  detail: string;
}

export interface Citation {
  kind?: "url" | "file";
  text?: string;
  title?: string;
  url?: string;
  fileId?: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
  citations?: Citation[];
  layers?: IQId[];
  /** True while tokens are still arriving. Suppresses the skill bar and the
   *  citation block until the answer is complete. */
  streaming?: boolean;
}

export interface StoryColumnItem {
  name: string;
  detail: string;
}

export interface StoryColumn {
  title: string;
  tag: string;
  items: StoryColumnItem[];
}

/** A single number on the metrics board. `tone` drives the colour treatment. */
export interface StoryMetric {
  label: string;
  value: string;
  sub?: string;
  tone?: "good" | "warn" | "bad" | "neutral";
}

/** One side of a reveal slide - the wrong read, then what actually binds. */
export interface RevealSide {
  head: string;
  lines: string[];
}

export interface Chapter {
  id: string;
  title: string;
  kicker: string;
  layout: "persona" | "architecture" | "iq" | "metrics" | "reveal" | "diagram"
    | "telemetry" | "path";
  body: string;
  points?: string[];
  columns?: StoryColumn[];
  metrics?: StoryMetric[];
  wrong?: RevealSide;
  right?: RevealSide;
  assurances?: string[];
  note?: string;
  iq?: IQId | "all";
  prompt: string | null;
  expect?: string[];
  /** Replaces the IQ cards and expect list with a per-layer comparison. */
  layerTable?: LayerTable;
  /** Gates on the path to yes, rendered by the "path" layout. */
  pathSteps?: PathStep[];
  /** Optional jargon-free retelling, rendered under the slide. */
  plain?: PlainEnglish;
}

export interface LayerTableRow {
  iq: IQId;
  holds: string;
  tells: string;
  cannot: string;
}

export interface LayerTable {
  headers: [string, string, string, string];
  rows: LayerTableRow[];
}

/** State of the Fabric capacity behind Fabric IQ, from /api/fabric-capacity. */
export interface FabricCapacity {
  configured: boolean;
  name?: string;
  sku?: string;
  region?: string;
  rawState?: string;
  state: "active" | "paused" | "resuming" | "pausing" | "unknown";
  canOperate: boolean;
  error?: string;
}

/** Live, cached Web IQ answer from /api/web-pulse. */
export interface WebPulse {
  status: "live" | "unavailable";
  text?: string;
  citations?: Citation[];
  webUsed?: boolean;
  fetchedAt?: string;
  stale?: boolean;
  detail?: string;
}

/** One gate on the path to yes: what blocks, what clears it, who decides. */
export interface PathStep {
  constraint: string;
  clears: string;
  owner: string;
  tone?: "ok" | "warn" | "bad";
}

export interface Persona {
  name: string;
  title: string;
  org: string;
  goal: string;
  objectives: string[];
  points?: string[];
}

export interface RolePersona {
  goal: string;
  objectives: string[];
  points: string[];
}

export interface Story {
  persona: Persona;
  personaByRole?: Record<string, RolePersona>;
  chapters: Chapter[];
  suggestions: string[];
}

export interface Me {
  name: string;
  upn: string;
  oid: string;
  roles: string[];
  role: string;
  jobTitle: string;
  department: string;
}

export interface AppConfig {
  tenantId: string;
  apiScope: string;
  agentName: string;
  mockMode: boolean;
  bank: string;
  disclaimer: string;
}

/* ------------------------------------------------------------- skills --- */

export interface ProFormaResult {
  incremental_m: number;
  ebitda_m: number;
  net_debt_m: number;
  pro_forma_net_debt_m: number;
  current_leverage: number;
  pro_forma_leverage: number;
  threshold: number;
  headroom_turns: number;
  band: string;
  tone: "ok" | "warn" | "bad";
  clears: boolean;
  max_clearing_m: number;
  shrink_required_m: number;
  verdict?: string;
  ebitda_shock_pct?: number;
  base_ebitda_m?: number;
  ebitda_cushion_pct?: number;
}

export interface StressCell { shock: number; leverage: number; headroom: number; band: string; tone: "ok" | "warn" | "bad" }
export interface StressRow { incremental_m: number; facility_m: number; ebitda_cushion_pct: number; cells: StressCell[] }
export interface StressGrid { shocks: number[]; rows: StressRow[]; threshold: number }

export interface PaperSection {
  heading: string;
  rows?: [string, string, string][];
  table?: { head: string[]; rows: string[][] };
  source?: string;
  lines?: [string, string][];
}
export interface Paper {
  id: "cc" | "pm" | "cr";
  title: string;
  addressee: string;
  policies: string[];
  sections: PaperSection[];
  signoff: { role: string; decision: string; name: string; date: string }[];
}
export interface PaperBundle {
  as_of: string;
  inputs: { incrementalM?: number; incremental_m?: number; facility_m?: number; hold_m?: number; final_hold_m?: number; client_id?: string };
  status: string;
  confidential: string;
  papers: Paper[];
  kind?: "deal" | "review";
  notes?: string[];
}

export interface ClientStressCell { shock: number; value: number; headroom: number; band: string; tone: "ok" | "warn" | "bad" }
export interface ClientStressRow {
  covenant: string; kind: "leverage" | "coverage"; test: string; threshold: number; actual: number;
  prior: number; trend: string; cushion_pct: number; cells: ClientStressCell[];
}
export interface ClientStress {
  client: string; id: string; shocks: number[]; rows: ClientStressRow[];
  binding?: string; binding_cushion_pct?: number; debt_capacity_turns?: number | null;
  headline: string; basis?: string; hero?: boolean;
}

export interface LeveragePoint {
  as_of: string;
  leverage: number;
  rating: string;
}

export interface RadarEntry {
  client_id: string;
  client: string;
  threshold: number;
  actual: number;
  prior: number;
  headroom: number;
  utilisation_pct: number;
  status: string;
  next_test: string;
  moved: number;
  deteriorating: boolean;
  tone: "ok" | "warn" | "bad";
}

export interface RoomCard {
  client: { id: string; name: string; ticker: string; as_of: string; currency: string };
  meeting: {
    id: string; date: string; time_local: string; location: string; title: string;
    agenda: string[]; client_attendees: string[];
    attendees: { alias: string; name: string; title: string; department: string;
                 wall_status: string; restricted: boolean }[];
  };
  asks: { id: string; name: string; size: number | null; decision_by: string }[];
  binding: { what: string; position: string; trend: string; status: string; owner: string }[];
  restriction: { id: string; raised_by: string; raised_on: string; expires: string; effect: string };
  proforma: ProFormaResult;
  verdict: string;
  say: string[];
  do_not_say: string[];
  confidential: string;
}

export interface SkillCatalogue {
  client: { id: string; name: string; ticker: string; as_of: string; currency: string };
  covenant: {
    name: string; threshold: number; actual: number; prior: number;
    headroom_turns: number; next_test: string; source_facility: string;
  };
  financials: {
    adjusted_ebitda_ltm_m: number; total_net_debt_m: number;
    as_of: string; basis: string;
  };
  leverage_history: LeveragePoint[];
  opportunities: Record<string, Record<string, unknown>>;
  roomcard: RoomCard;
  radar: { as_of: string; entries: RadarEntry[]; tight_count: number; hero_id: string; note: string };
  stress?: StressGrid;
}

/* ------------------------------------------------- plain-English panel --- */
export interface PlainCard {
  icon: string;
  title: string;
  sub?: string;
  body: string;
}

export interface PlainGauge {
  label: string;
  sub?: string;
  value: string;
  /** 0-100. Drives the bar width only; `value` is the text shown. */
  pct: number;
  tone: "ok" | "warn" | "bad";
  caption: string;
}

export interface PlainEnglish {
  heading: string;
  lead?: string;
  cards?: PlainCard[];
  gauges?: PlainGauge[];
  punch?: string;
}

/* ------------------------------------------------- agent run telemetry --- */

/** One recorded agent run, as plotted on the chapter 12 charts. */
export interface AgentRunPoint {
  t: string;
  label: string;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  cost: number;
  cumulativeCost: number;
  latencyMs: number;
  ok: boolean;
  layers: IQId[];
}

export interface AgentLayerCost {
  id: IQId;
  name: string;
  runs: number;
  tokens: number;
  cost: number;
  pct: number;
}

export interface AgentRecentRun {
  t: string;
  label: string;
  ok: boolean;
  latencyMs: number;
  totalTokens: number;
  cost: number;
  layers: IQId[];
  toolCalls: number;
  model: string;
}

/** One Azure resource's actual billed cost over the window. */
export interface BilledItem {
  name: string;
  service: string;
  role: string;
  cost: number;
  pct: number;
  /** True when the charge scales with questions asked, false for provisioned capacity. */
  metered: boolean;
}

export interface BilledCost {
  available: boolean;
  detail: string;
  error: string;
  currency: string;
  windowDays: number;
  from: string;
  to: string;
  total: number;
  metered: number;
  fixed: number;
  fixedPct: number;
  items: BilledItem[];
}

/** Platform cost per question, once provisioned services are counted. */
export interface AllInCost {
  platformCost: number;
  costPerQuestion: number;
  tokenCostPerQuestion: number;
  /** How many times the token bill the whole platform costs. */
  multiple: number;
  basis: string;
}

export interface AgentMetrics {
  asOf: string;
  /** "foundry" when the figures came from the project's traces. */
  source: "foundry" | "unavailable";
  sourceDetail: string;
  sourceError: string;
  currency: string;
  model: string;
  windowDays: number;
  /** Runs this BFF served that Application Insights has not ingested yet. */
  pendingRuns: number;
  pricing: {
    model: string;
    inputPer1k: number;
    outputPer1k: number;
    currency: string;
    basis: string;
  };
  totals: {
    runs: number;
    okRuns: number;
    failedRuns: number;
    successPct: number;
    inputTokens: number;
    outputTokens: number;
    totalTokens: number;
    cost: number;
    costPerRun: number;
    tokensPerRun: number;
    avgLatencyMs: number;
    p95LatencyMs: number;
    avgToolCalls: number;
  };
  series: AgentRunPoint[];
  byLayer: AgentLayerCost[];
  recent: AgentRecentRun[];
  /** Actual Azure spend for the demo. Null when Cost Management is not wired up. */
  billed: BilledCost | null;
  allIn: AllInCost | null;
}
