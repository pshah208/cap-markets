/**
 * Covenant stress for any company in the book.
 *
 * Gibson has net debt and EBITDA in the dataset, so it gets the full pro-forma
 * (ProFormaSkill). The other companies only carry their covenant ratios, so the
 * shock is applied to the ratios directly - exact, because net debt and interest
 * do not move with EBITDA - and debt capacity is shown in turns, not CAD.
 */

import { useEffect, useState } from "react";
import { apiGet } from "../../api";
import type { ClientStress } from "../../types";

export function ClientStressSkill({ clientId }: { clientId: string }) {
  const [data, setData] = useState<ClientStress | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setData(null);
    apiGet<ClientStress>(`/api/skills/client/${clientId}/stress`)
      .then((d) => { if (alive) { setData(d); setError(""); } })
      .catch((e) => { if (alive) setError(String(e)); });
    return () => { alive = false; };
  }, [clientId]);

  if (error) return <div className="papers-error">{error}</div>;
  if (!data) {
    return <div aria-busy="true"><div className="skel skel-title" /><div className="skel skel-line w90" /><div className="skel skel-line w75" /></div>;
  }

  const tone = (data.binding_cushion_pct ?? 100) < 5 ? "bad" : (data.binding_cushion_pct ?? 100) < 15 ? "warn" : "ok";

  return (
    <div className="pf">
      <div className={`pf-verdict tone-${tone}`}>
        <div className="pf-figures">
          <div><b>{data.binding_cushion_pct !== undefined ? `${data.binding_cushion_pct.toFixed(1)}%` : "—"}</b><span>EBITDA cushion</span></div>
          <div>
            <b>{data.debt_capacity_turns !== null && data.debt_capacity_turns !== undefined ? `${data.debt_capacity_turns.toFixed(2)}x` : "—"}</b>
            <span>debt capacity (turns)</span>
          </div>
          <div><b>{data.rows.length}</b><span>EBITDA-linked covenants</span></div>
        </div>
        <p className="pf-statement">{data.headline}</p>
      </div>

      {data.rows.length > 0 && (
        <div className="pf-grid-wrap">
          <div className="pf-grid-title">Covenant ratio under an Adjusted EBITDA shock</div>
          <table className="pf-grid">
            <thead>
              <tr>
                <th scope="col">Covenant</th>
                <th scope="col">Cushion</th>
                {data.shocks.map((s) => <th scope="col" key={s}>{s === 0 ? "Today" : `EBITDA ${s}%`}</th>)}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={r.covenant}>
                  <th scope="row">
                    {r.covenant}
                    <em>{r.test} {r.threshold}x · prior {r.prior}x · {r.trend}</em>
                  </th>
                  <td className={r.cushion_pct < 5 ? "tone-bad" : r.cushion_pct < 15 ? "tone-warn" : ""}>
                    {r.cushion_pct.toFixed(1)}%
                  </td>
                  {r.cells.map((c) => (
                    <td key={c.shock} className={`tone-${c.tone}`} title={`${c.band}, ${c.headroom} turns`}>
                      {c.value.toFixed(2)}x
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="pf-grid-note">{data.basis}</p>
        </div>
      )}

      <p className="pf-foot">
        Bands per CP-005: Comfortable &gt; 0.75 turns, Monitor 0.35–0.75, Tight &lt; 0.35, Breach ≤ 0.
        Any incremental commitment still needs a fully drawn pro-forma by Credit Risk before it is offered.
        Confidential under CP-014.
      </p>
    </div>
  );
}
