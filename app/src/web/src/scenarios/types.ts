export interface Factor { id: string; label: string; unit: string; min: number; max: number; step: number }
export interface Preset {
  id: string; name: string; note: string; factors: Record<string, number>;
  group?: "market" | "world"; channels?: string;
}

export type Severity = "dormant" | "low" | "elevated" | "high" | "severe";
export interface WorldTheme {
  id: string; name: string; note: string; channels: string;
  status: "active" | "emerging" | "dormant" | "unknown";
  severity: Severity; intensity: number;
  headline: string; date: string; source: string; url: string;
  base_factors: Record<string, number>; factors: Record<string, number>;
  live: boolean;
}
export interface EmergingRisk {
  title: string; severity: Severity; headline: string; why: string;
  date: string; source: string; url: string;
  closest: string | null; closest_name: string | null; proxy_factors: Record<string, number> | null;
}
export interface WorldPulse {
  status: "live" | "baseline"; detail?: string; stale?: boolean; fetchedAt?: string;
  themes: WorldTheme[]; emerging?: EmergingRisk[]; intensity: Record<Severity, number>;
}
export interface Library {
  factors: Factor[];
  presets: Preset[];
  valuation: Record<string, number>;
  as_of: string;
  source: string;
}

export interface CovenantMove {
  covenant: string; threshold: number; test: string;
  before: number; after: number; headroom_before: number; headroom_after: number;
  band_before: string; band_after: string; tone: "ok" | "warn" | "bad"; cushion_after: number;
}

export interface Drivers { revenue: number; expected_loss: number; capital: number; discount_rate: number }

export interface ClientRun {
  id: string; name: string; sector: string; tier: string;
  ebitda_pct: number; covenants: CovenantMove[]; binding: CovenantMove | null;
  rating_before: string; rating_after: string; notches: number;
  pd_before_pct: number; pd_after_pct: number;
  ead_before_m: number; ead_after_m: number; drawdown_m: number;
  revenue_before_m: number; revenue_after_m: number;
  el_before_m: number; el_after_m: number;
  capital_before_m: number; capital_after_m: number;
  value_before_m: number; value_after_m: number; value_change_m: number; value_change_pct: number | null;
  drivers: Drivers; business_model: string;
  deal?: { max_clearing_m: number; ask_leverage: number };
}

export interface ScenarioRun {
  name: string; factors: Record<string, number>; as_of: string;
  portfolio: {
    value_before_m: number; value_after_m: number; value_change_m: number; value_change_pct: number;
    revenue_before_m: number; revenue_after_m: number; el_before_m: number; el_after_m: number;
    ead_before_m: number; ead_after_m: number;
    breaches: number; tight: number; downgrades: number; upgrades: number; drivers: Drivers;
  };
  sectors: { sector: string; before: number; after: number; count: number; change_pct: number | null }[];
  clients: ClientRun[];
  method: string;
}
