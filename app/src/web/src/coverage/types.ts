/* Coverage workflow types - mirror app/src/bff/app/coverage.py. */

export type Tone = "ok" | "warn" | "bad";

export interface PulseRow { name: string; level: string; change: string; dir: "up" | "down"; bad?: boolean }
export interface PulsePanel { panel: string; rows: PulseRow[] }

export interface Person { alias: string; name: string; title: string; wall_status: string }

export interface Relationship {
  id: string; name: string; sector: string; tier: string; exposure_m: number; revenue_ytd_m: number;
  health: "healthy" | "attention" | "at_risk"; score: number; affected: boolean;
  ebitda_shock_pct: number; owner: Person;
}

export interface ReviewItem { date: string; client_id: string | null; client: string; kind: string; detail: string }

export interface CoverageOverview {
  as_of: string; time_local: string;
  scenario: { id: string; title: string; headline: string; alert: string; pulse: PulsePanel[] };
  affected_count: number;
  kpis: {
    exposure_m: number; committed_m: number; revenue_ytd_m: number; revenue_yoy_pct: number | null;
    relationships: number; health: { healthy: number; attention: number; at_risk: number };
    stressed_breaches: number;
  };
  tiers: { tier: string; exposure_m: number; count: number }[];
  relationships: Relationship[];
  reviews: ReviewItem[];
  sources: string[];
}

export interface CovImpact {
  covenant: string; threshold: number; test: string; before: number; after: number;
  headroom_after: number; band_before: string; band_after: string; tone: Tone;
  cushion_before: number; cushion_after: number;
}

export interface DealRecut {
  ask_m: number; max_clearing_before_m: number; max_clearing_after_m: number;
  ask_leverage_after: number; resized_150_leverage_after: number; resized_150_clears: boolean;
}

export interface SeverityPart { factor: string; points: number; detail: string }

export interface PseChange { before: number; after: number; limit: number; pct_after: number; change: number }

export interface TriageItem {
  id: string; name: string; tier: string; sector: string; score: number; affected: boolean;
  parts: SeverityPart[]; driver: string; ebitda_shock_pct: number; binding: CovImpact | null;
  deal?: DealRecut | null; pse?: PseChange | null;
}

export interface Triage { as_of: string; threshold: number; method: string; items: TriageItem[] }

export interface OutreachItem {
  id: string; name: string; score: number; contact_role: string; channel: string; channel_detail: string;
  slot: string; caller: Person; message: string; guardrail_notes: string[];
}
export interface OutreachPlan { as_of: string; items: OutreachItem[]; channels: string[] }
export interface OutreachStatus { id: string; status: "accepted" | "awaiting" | "tomorrow"; detail: string; channel: string; slot: string }
export interface OutreachResult { approved_by: string; items: OutreachStatus[]; note: string }

export interface PostureItem { label: string; value: string; sub: string; tone: Tone }

export interface Workspace {
  id: string; name: string; ticker: string; sector: string; sub_sector: string; tier: string; as_of: string;
  owner: Person; banker: Person; contact_role: string; channel_detail: string; slot: string;
  exposure_m: number; committed_m: number; revenue_ytd_m: number; wallet_share_pct: number | null;
  severity: { score: number; affected: boolean; parts: SeverityPart[] };
  impact: { client_id: string; ebitda_shock_pct: number; driver: string; covenants: CovImpact[];
            binding: CovImpact | null; deal?: DealRecut; pse?: PseChange };
  posture: PostureItem[];
  allocation: { product: string; exposure_m: number; pct: number }[];
  engagement: { date: string; kind: string; title: string; source: string }[];
  trades: { date: string; product: string; description: string; notional_m: number; status: string }[];
  restricted: boolean;
  prompts: { label: string; prompt: string }[];
}

export interface Guardrails {
  id: string; name: string; can_say: string[]; needs_disclaimer: string[]; needs_approval: string[];
  never_say: string[]; sources: string[]; house_view: { topic: string; view: string }[];
}

export interface CallTurn {
  speaker: string; kind: "open" | "question" | "answer"; text: string;
  sources?: string[]; disclaimer?: string; internal?: string;
}
export interface CallScript {
  id: string; name: string; contact_role: string; channel_detail: string; slot: string;
  turns: CallTurn[]; next_steps: string[];
}

export interface Wrapup {
  id: string; name: string; status: string; cowork_prompt: string;
  memo: { title: string; sections: { heading: string; lines: string[] }[]; prepared_by: string };
  email: { subject: string; body: string; to_note: string };
}
