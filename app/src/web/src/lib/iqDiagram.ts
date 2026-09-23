/**
 * Content and structure for the per-layer architecture diagrams shown on the
 * four single-IQ story slides.
 *
 * Kept as data, separate from the renderer, so a presenter can re-word a box
 * without touching layout or animation code — the same split already used by
 * `flowScene.ts` for the four-IQ sequence.
 *
 * Every diagram is the same left-to-right sentence:
 *
 *     sources  →  core  →  outcomes  →  agents
 *
 * `outcomes` and `agents` are optional because the four layers genuinely differ
 * in shape: Foundry IQ carries its detail as a card grid inside the core and has
 * no separate outcomes column, and Work IQ ends at its outcomes with no agent
 * column. Rendering those as absent columns rather than empty ones keeps the
 * remaining columns wide enough to read at presenter distance.
 *
 * The wording is deliberately this deal, not the generic product pitch — the
 * boxes name Gibson Energy's covenant, the Control Room and CP-005 rather than
 * "your data" and "your policies", because the slides around them do too.
 */

import type { IQId } from "../types";

export interface DiagramOutcome {
  title: string;
  detail: string;
}

export interface DiagramCard {
  title: string;
  detail: string;
  /** Spans the full width of the core card grid. */
  wide?: boolean;
}

export interface DiagramSpec {
  id: IQId;
  /** Heading above the diagram, e.g. "Work IQ". */
  title: string;
  subtitle: string;
  sources: {
    label: string;
    /** Optional sentence under the column label. */
    lede?: string;
    tiles: string[];
    /** Tiles that should span the full column width, e.g. Web IQ's "Browse". */
    wideTiles?: string[];
    foot?: string;
  };
  core: {
    title: string;
    detail: string;
    /** Small emphasised strips under the core title. */
    notes?: string[];
    /** Card grid rendered inside the core, used by Foundry IQ. */
    cards?: DiagramCard[];
  };
  outcomes?: {
    items: DiagramOutcome[];
    foot?: string;
  };
  agents?: {
    title: string;
    detail: string;
    foot?: string;
    items?: string;
  };
  /** Footer bar, rendered after a shield glyph. */
  assurances: string[];
  /**
   * Narration for each stream stage, read out by the caption line as the
   * animation advances. One entry per connector, in left-to-right order.
   */
  stages: string[];
}

export const DIAGRAMS: Record<IQId, DiagramSpec> = {
  work: {
    id: "work",
    title: "Work IQ",
    subtitle: "How the coverage team already reasoned, in context",
    sources: {
      label: "Microsoft 365 work context",
      tiles: ["Outlook", "Teams", "SharePoint", "Files", "People & roles", "Calendar"],
    },
    core: {
      title: "Work IQ",
      detail: "People · documents · communication · workflows",
      notes: [
        "Persistent memory of the desk's own argument",
        "Permission-aware with Microsoft Entra",
      ],
    },
    outcomes: {
      items: [
        {
          title: "Control Room briefing found",
          detail: "What CR-2026-0184 restricted, and until when",
        },
        {
          title: "Coverage debate reconstructed",
          detail: "Who committed what, to whom, over two weeks",
        },
      ],
      foot: "Deal context · what the desk already said before any number",
    },
    assurances: [
      "Microsoft Entra identity",
      "Permission-aware retrieval",
      "Organizational memory",
    ],
    stages: [
      "Reading Microsoft 365 through Graph — mail, Teams, files and calendar, filtered to what this user may see.",
      "Work IQ assembles two weeks of disagreement into a briefing and a set of standing commitments.",
    ],
  },

  fabric: {
    id: "fabric",
    title: "Fabric IQ",
    subtitle: "Governed client data, one shared meaning",
    sources: {
      label: "Enterprise data sources",
      tiles: [
        "Facilities",
        "Exposures",
        "Covenants",
        "Sector envelopes",
        "Client master",
        "Ratings feed",
      ],
      foot: "Structured, unstructured, batch, SaaS, and real-time data",
    },
    core: {
      title: "OneLake",
      detail: "Mirroring · connectors · shortcuts",
      notes: ["Unified and governed"],
    },
    outcomes: {
      items: [
        { title: "Ontology", detail: "Clients, facilities, limits and the links between them" },
        { title: "Semantic model", detail: "Governed measures — utilisation, headroom, leverage" },
      ],
    },
    agents: {
      title: "Fabric IQ",
      detail: "Agents reason in covenants and limits, not raw tables",
    },
    assurances: [
      "OneLake",
      "Governance",
      "Microsoft Entra identity",
      "Security carried from source",
    ],
    stages: [
      "Ten Delta tables land in OneLake by mirroring, connectors and shortcuts — no copy, no warehouse to reconcile.",
      "The ontology and semantic model turn tables into business concepts: exposure, headroom, leverage covenant.",
      "The agent queries those concepts, so the covenant is checked even when nobody thought to open it.",
    ],
  },

  foundry: {
    id: "foundry",
    title: "Foundry IQ",
    subtitle: "Unlock governed credit and conduct policy for the desk",
    sources: {
      label: "Enterprise operating knowledge",
      lede: "Published credit policy, control-room procedure and conduct standards.",
      tiles: [
        "Credit policy",
        "Control room procedure",
        "Conduct standards",
        "Sector envelopes",
        "Approval matrices",
        "Regulatory guidance",
      ],
    },
    core: {
      title: "Foundry IQ",
      detail: "Permission-aware knowledge and grounded retrieval",
      cards: [
        {
          title: "Reusable knowledge base",
          detail: "One governed policy domain, shared by every agent.",
        },
        {
          title: "Agentic retrieval",
          detail: "Plan searches and return the clause that actually governs.",
        },
        {
          title: "Citations",
          detail: "Every refusal links back to the policy that requires it.",
        },
        {
          title: "Enterprise security",
          detail: "Identity and source permissions stay enforced end to end.",
          wide: true,
        },
      ],
    },
    agents: {
      title: "Policy gates applied",
      detail: "A reasonable-sounding route is only available when policy says so",
      foot: "Ground every credit decision",
      items: "Coverage · credit · control room · risk",
    },
    assurances: [
      "Microsoft Entra identity",
      "Permission-aware retrieval",
      "Grounded answers",
      "Citations",
    ],
    stages: [
      "Scattered policy — credit, conduct, control room, sector envelopes — is prepared once into a governed domain.",
      "Agentic retrieval names CP-005, CP-002 and CP-008 with citations, and names who decides instead of the desk.",
    ],
  },

  web: {
    id: "web",
    title: "Web IQ",
    subtitle: "Current public context on a real, listed issuer",
    sources: {
      label: "Grounding APIs",
      tiles: ["Web", "News", "Ratings coverage", "Filings"],
      wideTiles: ["Browse"],
    },
    core: {
      title: "Web IQ",
      detail: "Web grounding built for multi-step agents",
    },
    outcomes: {
      items: [
        { title: "Current conditions", detail: "Public events that change what we can say" },
        { title: "Source links", detail: "Evidence the MD can inspect before Thursday" },
      ],
    },
    agents: {
      title: "External operating context",
      detail: "What changed outside the bank, kept separate from internal figures",
    },
    assurances: [
      "Current public sources",
      "Source links",
      "Domain controls",
      "Grounded responses",
    ],
    stages: [
      "The only layer that leaves the tenant — grounding APIs reach current public sources on a real TSX issuer.",
      "Results come back dated and source-linked, so a rating can be checked rather than trusted.",
      "Public facts stay on the public side; the internal placeholder is never quoted as a rating.",
    ],
  },
};

/** Number of animated connectors a spec renders, left to right. */
export function stageCount(spec: DiagramSpec): number {
  return 1 + (spec.outcomes ? 1 : 0) + (spec.agents ? 1 : 0);
}
