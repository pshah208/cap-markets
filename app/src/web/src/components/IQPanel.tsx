import type { ReactNode } from "react";
import type { IQState } from "../types";

/* One stroke weight, one grid (24px, 1.75 stroke) so the four layers read as a
   set and take their colour from the layer - not four unrelated emoji. */
const svg = (children: ReactNode) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
       strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
);

const ICON: Record<string, ReactNode> = {
  // conversation: two offset message bubbles
  work: svg(<>
    <path d="M4 5h11a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9l-4 3v-3H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z" />
    <path d="M17 9h3a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-1v2l-3-2h-4" />
  </>),
  // governed data: stacked cylinder
  fabric: svg(<>
    <ellipse cx="12" cy="5.5" rx="7.5" ry="2.75" />
    <path d="M4.5 5.5v6.5c0 1.5 3.4 2.75 7.5 2.75s7.5-1.25 7.5-2.75V5.5" />
    <path d="M4.5 12v6.5c0 1.5 3.4 2.75 7.5 2.75s7.5-1.25 7.5-2.75V12" />
  </>),
  // policy: a ruled document with a check
  foundry: svg(<>
    <path d="M6 3h8l4 4v14H6z" />
    <path d="M14 3v4h4" />
    <path d="M9 12h6M9 15.5h3.5" />
    <path d="m12.5 18.5 1.5 1.5 3-3" />
  </>),
  // live web: globe with meridian
  web: svg(<>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18" />
    <path d="M12 3c2.5 2.7 3.75 5.7 3.75 9S14.5 18.3 12 21c-2.5-2.7-3.75-5.7-3.75-9S9.5 5.7 12 3z" />
  </>),
};

/** The systems each layer reaches, mirrored in the story panel. */
const SOURCES: Record<string, string[]> = {
  work: ["Outlook", "Teams", "SharePoint", "Files"],
  fabric: ["OneLake", "Semantic model", "Covenants"],
  foundry: ["AI Search", "Policy corpus", "CP-001…014"],
  web: ["Bing", "News", "Ratings"],
};

export function IQCard({ iq }: { iq: IQState }) {
  return (
    <div className={`iq-card iq-${iq.id} status-${iq.status}`}>
      <div className="iq-card-head">
        <span className="iq-icon-wrap" aria-hidden>
          <span className="iq-icon">{ICON[iq.id]}</span>
        </span>
        <div className="iq-head-text">
          <div className="iq-name">{iq.name}</div>
          <div className="iq-source">{iq.source}</div>
        </div>
        <span className={`iq-badge badge-${iq.status}`}>
          {iq.status === "active" ? "ACTIVE" : iq.status === "done" ? "USED" : "IDLE"}
        </span>
      </div>

      <div className="iq-blurb">{iq.blurb}</div>

      <div className="iq-chips">
        {(SOURCES[iq.id] ?? []).map((s) => (
          <span className="iq-chip" key={s}>{s}</span>
        ))}
      </div>

      {iq.detail && <div className="iq-detail">{iq.detail}</div>}
      {iq.status === "active" && <div className="iq-pulse-bar" />}
    </div>
  );
}

export function IQPanel({ iqs }: { iqs: IQState[] }) {
  const used = iqs.filter((i) => i.status !== "idle").length;
  return (
    <section className="iq-panel">
      <div className="panel-head">
        <h2 className="panel-title">Microsoft intelligence layers</h2>
        <span className="panel-count">{used} of {iqs.length} engaged</span>
      </div>
      <p className="panel-sub">
        These light up from the agent's actual tool calls — nothing here is scripted.
      </p>
      <div className="iq-grid">
        {iqs.map((iq) => (
          <IQCard key={iq.id} iq={iq} />
        ))}
      </div>
    </section>
  );
}
