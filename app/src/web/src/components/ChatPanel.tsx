import { useEffect, useRef, useState } from "react";
import { Citations, Markdown } from "./Markdown";
import { SkillBar } from "./SkillBar";
import type { ChatMessage } from "../types";

interface Props {
  messages: ChatMessage[];
  busy: boolean;
  status: string;
  suggestions: string[];
  agentName: string;
  onSend: (q: string) => void;
  onStop: () => void;
}

export function ChatPanel({
  messages, busy, status, suggestions, agentName, onSend, onStop,
}: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  function submit(e?: React.FormEvent) {
    e?.preventDefault();
    const q = draft.trim();
    if (!q || busy) return;
    setDraft("");
    onSend(q);
  }

  return (
    <section className="chat-panel">
      <header className="chat-head">
        <div className="chat-brand">
          <span className="chat-mark" aria-hidden>◆</span>
          <div>
            <div className="chat-title">BMO Capital Markets Client Intelligence</div>
            <div className="chat-sub">
              Ask about exposure, limits, approvals and external signal
            </div>
          </div>
        </div>
        <span className="chat-agent" title={`Foundry agent: ${agentName}`}>
          Foundry agent
        </span>
      </header>

      <div className="chat-body">
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="empty-eyebrow">Capital markets client intelligence</div>
            <h2 className="empty-title">What do you need<br />to decide?</h2>
            <p className="empty-sub">
              Grounded across governed exposure and limits, the coverage team's
              own email and documents, the global policy corpus, and the live web.
            </p>
            <div className="suggestions">
              {suggestions.slice(0, 4).map((s) => (
                <button key={s} className="suggestion" onClick={() => onSend(s)}>
                  <span>{s}</span>
                  <span className="suggestion-arrow" aria-hidden>↗</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => {
          // Skills hang off a COMPLETED assistant answer only: offering to run
          // the pro-forma while the answer is still streaming invites a click
          // on a half-formed premise.
          const isLast = i === messages.length - 1;
          const showSkills = m.role === "assistant" && !m.streaming
            && m.content.trim().length > 0 && !(isLast && busy);
          return (
            <div className={`msg msg-${m.role}`} key={i}>
              <div className="msg-body">
                {m.role === "user" ? <p>{m.content}</p> : <Markdown text={m.content} />}
                {m.streaming && <span className="stream-caret" aria-hidden />}
              </div>
              {m.citations?.length ? <Citations items={m.citations} /> : null}
              {showSkills && <SkillBar answer={m.content} />}
            </div>
          );
        })}

        {/* The spinner is only meaningful before the first token lands. Once
            prose is streaming, the text itself is the progress indicator. */}
        {busy && !messages[messages.length - 1]?.streaming && (
          <div className="msg msg-assistant">
            <div className="thinking">
              <span className="dot" /><span className="dot" /><span className="dot" />
              <span className="thinking-text">{status || "Working…"}</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form className="chat-input" onSubmit={submit}>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about the client, the limits or the approvals…"
          disabled={busy}
          aria-label="Ask the agent"
        />
        {busy ? (
          <button type="button" className="btn-stop" onClick={onStop}>Stop</button>
        ) : (
          <button type="submit" className="btn-send" disabled={!draft.trim()}>
            Ask
          </button>
        )}
      </form>
    </section>
  );
}
