/**
 * Approval papers - the step after "path to yes".
 *
 * Drafts the three papers the gates on slide 11 need: Credit Committee
 * submission, Portfolio Management offset plan and Control Room clearance
 * request. Everything is built server-side from governed figures; this
 * component chooses the inputs, shows the drafts with a source on every line,
 * and downloads them as Word. Nothing here approves anything - each paper ends
 * with an empty human sign-off block.
 */

import { useEffect, useState } from "react";
import { apiDownload, apiPost } from "../../api";
import type { Paper, PaperBundle, PaperSection, SkillCatalogue } from "../../types";

const PRESETS: { label: string; inc: number }[] = [
  { label: "Resized · +150m", inc: 150 },
  { label: "Largest that clears · +195m", inc: 195 },
  { label: "As asked · +250m", inc: 250 },
];

function Section({ s }: { s: PaperSection }) {
  return (
    <section className="paper-section">
      <h5>{s.heading}</h5>
      {s.rows && (
        <table className="paper-rows">
          <tbody>
            {s.rows.map(([k, v, src]) => (
              <tr key={k}>
                <th scope="row">{k}</th>
                <td>{v}</td>
                <td className="paper-src">{src}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {s.table && (
        <table className="paper-rows paper-table">
          <thead><tr>{s.table.head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
          <tbody>
            {s.table.rows.map((r) => (
              <tr key={r[0]} className={r[3] === "Breach" ? "tone-bad" : ""}>
                {r.map((c, i) => <td key={i}>{c}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {s.source && <p className="paper-src">Source: {s.source}</p>}
      {s.lines && (
        <ul className="paper-lines">
          {s.lines.map(([t, src]) => (
            <li key={t}>{t} <span className="paper-src">[{src}]</span></li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Tabs + paper + human sign-off + downloads, for any paper bundle. */
export function PaperBundleView({ bundle, onDownload, downloading }: {
  bundle: PaperBundle;
  onDownload: (which: string) => void;
  downloading: boolean;
}) {
  const [tab, setTab] = useState<Paper["id"]>(bundle.papers[0]?.id ?? "cc");
  const paper = bundle.papers.find((p) => p.id === tab) ?? bundle.papers[0];
  const n = bundle.papers.length;

  return (
    <>
      <div className="papers-status">{bundle.status}</div>
      {n > 1 && (
        <div className="papers-tabs" role="tablist">
          {bundle.papers.map((p) => (
            <button
              key={p.id} role="tab" aria-selected={paper?.id === p.id}
              className={paper?.id === p.id ? "on" : ""} onClick={() => setTab(p.id)}
            >{p.addressee}</button>
          ))}
        </div>
      )}

      {paper && (
        <article className="paper">
          <h4>{paper.title}</h4>
          <div className="paper-meta">
            To {paper.addressee} · as at {bundle.as_of} · {paper.policies.join(", ")}
          </div>
          {paper.sections.map((s) => <Section key={s.heading} s={s} />)}
          <section className="paper-section">
            <h5>Approval — human sign-off</h5>
            <table className="paper-rows paper-signoff">
              <thead><tr><th>Role</th><th>Decision</th><th>Name</th><th>Date</th></tr></thead>
              <tbody>
                {paper.signoff.map((s) => (
                  <tr key={s.role}><td>{s.role}</td><td /><td /><td /></tr>
                ))}
              </tbody>
            </table>
          </section>
          <p className="paper-confidential">{bundle.confidential}</p>
        </article>
      )}
      {bundle.notes?.map((t) => <p key={t} className="paper-src">{t}</p>)}

      <div className="papers-actions">
        <button className="btn-primary" disabled={downloading} onClick={() => onDownload(paper?.id ?? "cc")}>
          Download this paper (.docx)
        </button>
        {n > 1 && (
          <button className="papers-all" disabled={downloading} onClick={() => onDownload("all")}>
            Download all {n}
          </button>
        )}
      </div>
    </>
  );
}

export function PapersSkill({ catalogue }: { catalogue: SkillCatalogue }) {
  const rev = catalogue.opportunities.revolver_upsize as Record<string, number>;
  const currentHold = Number(rev?.bank_current_hold_m ?? 165);

  const [inc, setInc] = useState(150);
  const [finalHold, setFinalHold] = useState(currentHold);
  const [bundle, setBundle] = useState<PaperBundle | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);

  const body = { incrementalM: inc, finalHoldM: finalHold };

  useEffect(() => {
    let alive = true;
    apiPost<PaperBundle>("/api/skills/papers", body)
      .then((b) => { if (alive) { setBundle(b); setError(""); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inc, finalHold]);

  const download = async (which: string) => {
    setDownloading(true);
    try {
      await apiDownload(`/api/skills/papers/docx?which=${which}`, body, "approval-papers.docx");
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="papers">
      <div className="papers-controls">
        <div className="pf-presets">
          {PRESETS.map((p) => (
            <button key={p.inc} className={inc === p.inc ? "on" : ""} onClick={() => setInc(p.inc)}>
              {p.label}
            </button>
          ))}
        </div>
        <label className="papers-hold">
          Target final hold after sell-down
          <input
            type="number" min={0} max={400} step={5} value={finalHold}
            onChange={(e) => setFinalHold(Number(e.target.value))}
          />
          <span>CAD m · {currentHold}m keeps the sector neutral</span>
        </label>
      </div>

      {error && <div className="papers-error">{error}</div>}
      {bundle && <PaperBundleView key={`${inc}-${finalHold}`} bundle={bundle} onDownload={download} downloading={downloading} />}
    </div>
  );
}

/** Credit papers for any company in the book, from its own governed figures. */
export function ClientPapersSkill({ clientId }: { clientId: string }) {
  const [bundle, setBundle] = useState<PaperBundle | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    let alive = true;
    setBundle(null);
    apiPost<PaperBundle>(`/api/skills/client/${clientId}/papers`, {})
      .then((b) => { if (alive) { setBundle(b); setError(""); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [clientId]);

  const download = async (which: string) => {
    setDownloading(true);
    try {
      await apiDownload(`/api/skills/client/${clientId}/papers/docx?which=${which}`, {}, "credit-papers.docx");
    } catch (e) {
      setError(String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="papers">
      {error && <div className="papers-error">{error}</div>}
      {!bundle && !error && (
        <div aria-busy="true"><div className="skel skel-title" /><div className="skel skel-line w90" /><div className="skel skel-line w75" /></div>
      )}
      {bundle && <PaperBundleView key={clientId} bundle={bundle} onDownload={download} downloading={downloading} />}
    </div>
  );
}
