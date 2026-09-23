import type { IQState } from "../types";

const ICON: Record<string, string> = {
  work: "✉️",
  fabric: "🗄️",
  foundry: "🧠",
  web: "🌐",
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
