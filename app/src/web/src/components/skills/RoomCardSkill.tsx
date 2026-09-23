/**
 * The meeting room card.
 *
 * This is the artifact the demo's own persona goal asks for: *"Walk into
 * Thursday's Gibson Energy meeting knowing exactly what we can and cannot say."*
 * Everything on it is assembled server-side from the governed figures and the
 * policy corpus - nothing is written by the model - so it is safe to print and
 * carry into the room.
 *
 * It is deliberately INTERNAL. It carries limits, covenant headroom and the
 * restricted-list position, all confidential under CP-014, so the header says so
 * and the print stylesheet keeps the banner.
 */

import type { RoomCard } from "../../types";

export function RoomCardSkill({ card }: { card: RoomCard }) {
  const m = card.meeting;
  return (
    <div className="rc">
      <div className="rc-confidential">{card.confidential}</div>

      <header className="rc-head">
        <div>
          <h4>{card.client.name} <span className="rc-ticker">{card.client.ticker}</span></h4>
          <p className="rc-meta">
            {m.date} · {m.time_local} · {m.location}
          </p>
        </div>
        <div className="rc-ref">{m.id}</div>
      </header>

      {/* The single most important line on the card. */}
      <div className={`rc-verdict tone-${card.proforma.tone}`}>
        <span className="rc-verdict-tag">Before you commit to a number</span>
        {card.verdict}
      </div>

      <section className="rc-grid">
        <div className="rc-col">
          <h5>The three asks</h5>
          <ul className="rc-asks">
            {card.asks.map((a) => (
              <li key={a.id}>
                <span className="rc-ask-name">{a.name}</span>
                <span className="rc-ask-size">
                  {a.size ? `CAD ${a.size}m` : "—"}
                  {a.decision_by && <em> · by {a.decision_by}</em>}
                </span>
              </li>
            ))}
          </ul>

          <h5>What actually binds</h5>
          <ul className="rc-binding">
            {card.binding.map((b) => (
              <li key={b.what}>
                <span className={`rc-pill tone-${b.status === "Breach" ? "bad"
                  : b.status === "Amber" ? "warn" : "ok"}`}>{b.status}</span>
                <div>
                  <b>{b.what}</b>
                  <div className="rc-binding-pos">{b.position}</div>
                  {b.trend && <div className="rc-binding-trend">{b.trend}</div>}
                  <div className="rc-binding-owner">Owner: {b.owner}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="rc-col">
          <h5 className="rc-ok">Safe to discuss</h5>
          <ul className="rc-say">
            {card.say.map((s) => <li key={s}>{s}</li>)}
          </ul>

          <h5 className="rc-bad">Do not say</h5>
          <ul className="rc-notsay">
            {card.do_not_say.map((s) => <li key={s}>{s}</li>)}
          </ul>
        </div>
      </section>

      <section className="rc-restriction">
        <h5>Open restriction · {card.restriction.id}</h5>
        <p>{card.restriction.effect}</p>
        <p className="rc-restriction-meta">
          Raised by {card.restriction.raised_by} on {card.restriction.raised_on}.
          Expected expiry {card.restriction.expires} — an expectation, not an
          authorisation to resume (CP-008).
        </p>
      </section>

      <section className="rc-room">
        <h5>In the room</h5>
        <table className="rc-attendees">
          <tbody>
            {m.attendees.map((a) => (
              <tr key={a.alias} className={a.restricted ? "is-restricted" : ""}>
                <td className="rc-att-name">{a.name}</td>
                <td className="rc-att-title">{a.title}</td>
                <td className="rc-att-wall">
                  {a.restricted
                    ? <span className="rc-pill tone-warn">do not ask about the restriction</span>
                    : <span className="rc-pill tone-ok">public side</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="rc-client-side">
          Client side: {m.client_attendees.join(" · ")}
        </p>
      </section>

      <section className="rc-agenda">
        <h5>Agenda</h5>
        <ol>{m.agenda.map((a) => <li key={a}>{a}</li>)}</ol>
      </section>
    </div>
  );
}
