import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  fetchConfig, fetchIQs, fetchMe, fetchStory, runDiagnostics, streamChat,
} from "./api";
import { account, authEnabled, login, logout } from "./auth";
import { ChatPanel } from "./components/ChatPanel";
import { IQPanel } from "./components/IQPanel";
import { StoryPanel } from "./components/StoryPanel";
import { Dashboard } from "./dashboard/Dashboard";
import type {
  AppConfig, ChatMessage, Citation, IQId, IQMeta, IQState, Me, Story,
} from "./types";

type Mode = "story" | "chat" | "dashboard";

/** Percentage of the viewport width given to the chat panel. */
const CHAT_WIDTH_KEY = "cmci.chatWidth";
const CHAT_WIDTH_DEFAULT = 50;
const CHAT_WIDTH_MIN = 20;
const CHAT_WIDTH_MAX = 80;

const clampChatWidth = (v: number) =>
  Math.min(CHAT_WIDTH_MAX, Math.max(CHAT_WIDTH_MIN, v));

function readStoredChatWidth() {
  try {
    const raw = window.localStorage.getItem(CHAT_WIDTH_KEY);
    const n = raw === null ? NaN : Number(raw);
    return Number.isFinite(n) ? clampChatWidth(n) : CHAT_WIDTH_DEFAULT;
  } catch {
    return CHAT_WIDTH_DEFAULT;
  }
}

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [story, setStory] = useState<Story | null>(null);
  const [iqMeta, setIqMeta] = useState<IQMeta[]>([]);
  const [iqs, setIqs] = useState<IQState[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [chapter, setChapter] = useState(0);
  const [mode, setMode] = useState<Mode>("story");
  const [me, setMe] = useState<Me | null>(null);
  const [bootError, setBootError] = useState("");
  const [diag, setDiag] = useState<unknown>(null);
  const [chatWidth, setChatWidth] = useState(readStoredChatWidth);
  const [resizing, setResizing] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(CHAT_WIDTH_KEY, String(chatWidth));
    } catch {
      /* storage unavailable (private mode) — the split just won't persist */
    }
  }, [chatWidth]);

  const nudgeChatWidth = useCallback((delta: number) => {
    setChatWidth((w) => clampChatWidth(w + delta));
  }, []);

  const signedIn = !authEnabled || Boolean(account());

  useEffect(() => {
    (async () => {
      try {
        const [c, s, m] = await Promise.all([fetchConfig(), fetchStory(), fetchIQs()]);
        setConfig(c);
        setStory(s);
        setIqMeta(m);
        setIqs(m.map((x) => ({ ...x, status: "idle", detail: "" })));
      } catch (e) {
        setBootError(String(e));
      }
    })();
  }, []);

  useEffect(() => {
    if (!signedIn) return;
    fetchMe().then(setMe).catch(() => setMe(null));
  }, [signedIn]);

  const resetIQs = useCallback(() => {
    setIqs(iqMeta.map((x) => ({ ...x, status: "idle", detail: "" })));
  }, [iqMeta]);

  const send = useCallback(async (question: string) => {
    if (busy) return;
    setMode("chat");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    resetIQs();
    setBusy(true);
    setStatus("");

    const layers: IQId[] = [];
    const controller = new AbortController();
    abortRef.current = controller;

    await streamChat(question, threadId, {
      onStatus: setStatus,
      onIQ: (iq, st, detail) => {
        if (st === "active" && !layers.includes(iq)) layers.push(iq);
        setIqs((prev) =>
          prev.map((x) => (x.id === iq ? { ...x, status: st, detail } : x)),
        );
      },
      onToken: (text: string) => {
        // Append to an in-flight assistant message, creating it on the first
        // chunk. The final `message` event replaces this text wholesale with
        // the complete answer and its citations, so a partial render can never
        // become the thing citations get attached to.
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          if (last?.role === "assistant" && last.streaming) {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + text },
            ];
          }
          return [
            ...prev,
            { role: "assistant", content: text, streaming: true, layers: [...layers] },
          ];
        });
      },
      onMessage: (text: string, citations: Citation[]) => {
        setMessages((prev) => {
          const last = prev[prev.length - 1];
          const done = {
            role: "assistant" as const,
            content: text,
            citations,
            layers: [...layers],
            streaming: false,
          };
          // Replace the streamed placeholder rather than appending a duplicate.
          if (last?.role === "assistant" && last.streaming) {
            return [...prev.slice(0, -1), done];
          }
          return [...prev, done];
        });
      },
      onError: (text, detail) => {
        setMessages((prev) => [
          ...prev,
          { role: "error", content: `${text}\n\n${detail}` },
        ]);
      },
      onDone: (payload) => {
        setBusy(false);
        setStatus("");
        if (typeof payload.threadId === "string") setThreadId(payload.threadId);
      },
    }, controller.signal).catch((e) => {
      if (e?.name !== "AbortError") {
        setMessages((prev) => [...prev, { role: "error", content: String(e) }]);
      }
      setBusy(false);
    });
  }, [busy, resetIQs, threadId]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    setBusy(false);
    setStatus("");
  }, []);

  const suggestions = useMemo(() => story?.suggestions ?? [], [story]);

  /**
   * The persona card describes whoever is actually signed in.
   *
   * Name and title come from Microsoft Graph (the four demo accounts carry real
   * displayName / jobTitle values in Entra). Goal and objectives come from the
   * app role in the user's token, so Corporate Banking sees the hold-sizing
   * framing and Global Markets sees the hedging framing. Falls back to the
   * story's default Coverage persona if Graph or the role claim is unavailable.
   */
  const persona = useMemo(() => {
    const base = story?.persona;
    if (!base) return null;
    if (!me) return base;
    const byRole = story?.personaByRole?.[me.role];
    return {
      org: base.org,
      name: me.name || base.name,
      title: me.jobTitle || base.title,
      goal: byRole?.goal ?? base.goal,
      objectives: byRole?.objectives ?? base.objectives,
      points: byRole?.points,
    };
  }, [story, me]);

  if (bootError) {
    return (
      <div className="boot-error">
        <h1>Could not reach the API</h1>
        <pre>{bootError}</pre>
        <p>Is the BFF running? Try <code>GET /health</code>.</p>
      </div>
    );
  }

  if (!config || !story) {
    return <div className="boot">Loading…</div>;
  }

  if (authEnabled && !signedIn) {
    return (
      <div className="signin">
        <div className="signin-card">
          <img className="signin-mark" src="/brand/cm-lockup.png" alt={config.bank} />
          <h1>Capital Markets Client Intelligence</h1>
          <p className="signin-sub">{config.bank} · Energy &amp; Midstream coverage</p>
          <p className="signin-why">
            Sign in with your work account. The agent answers using
            <strong> your</strong> email, Teams and document context — so it must
            know who you are before it can ground anything.
          </p>
          <button className="btn-primary" onClick={() => login()}>
            Sign in with Microsoft
          </button>
          <p className="signin-disclaimer">{config.disclaimer}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
       <header className="topbar portfolio-navigation">
        <div className="brand">
          <img className="brand-mark" src="/brand/cm-logo-white.png" alt="" aria-hidden />
          <span className="brand-name">{config.bank}</span>
          <span className="brand-divider" />
          <span className="brand-app">Capital Markets Client Intelligence</span>
        </div>

        <div className="topbar-right">
           <div className="mode-toggle" role="group" aria-label="Workspace">
            <button
              className={mode === "story" ? "on" : ""}
              onClick={() => setMode("story")}
               aria-pressed={mode === "story"}
            >Guided</button>
            <button
              className={mode === "chat" ? "on" : ""}
              onClick={() => setMode("chat")}
               aria-pressed={mode === "chat"}
             >Explore</button>
             <button
               className={mode === "dashboard" ? "on" : ""}
               onClick={() => setMode("dashboard")}
               aria-pressed={mode === "dashboard"}
             >Dashboard</button>
          </div>
          {config.mockMode && <span className="pill pill-warn">MOCK MODE</span>}
          {me && (
            <div className="who" title={me.upn}>
              <span className="who-avatar" aria-hidden>
                {me.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
              </span>
              <span className="who-text">
                <span className="who-name">{me.name}</span>
                {me.role && <span className="who-role">{me.role}</span>}
              </span>
            </div>
          )}
          {authEnabled && (
            <button className="btn-ghost" onClick={() => logout()}>Sign out</button>
          )}
        </div>
      </header>

      <div className="disclaimer-strip">{config.disclaimer}</div>

       <Dashboard active={mode === "dashboard"} />
       <main
        className={`layout layout-${mode}${resizing ? " resizing" : ""}`}
         style={{
           "--chat-width": `${chatWidth}vw`,
           ...(mode === "dashboard" ? { display: "none" } : {}),
         } as CSSProperties}
      >
        {mode === "story" ? (
          <StoryPanel
            story={story}
            persona={persona ?? story.persona}
            index={chapter}
            iqs={iqs}
            busy={busy}
            onPrev={() => setChapter((c) => Math.max(0, c - 1))}
            onNext={() => setChapter((c) => Math.min(story.chapters.length - 1, c + 1))}
            onRunPrompt={send}
          />
        ) : (
          <section className="explore-panel">
            <IQPanel iqs={iqs} />
            <div className="explore-suggestions">
              <div className="panel-head">
                <h2 className="panel-title">Try asking</h2>
              </div>
              {suggestions.map((s) => (
                <button key={s} className="suggestion" onClick={() => send(s)} disabled={busy}>
                  <span>{s}</span>
                  <span className="suggestion-arrow" aria-hidden>↗</span>
                </button>
              ))}
            </div>
            <details className="diag">
              <summary>Connection diagnostics</summary>
              <button
                className="btn-ghost"
                onClick={() => runDiagnostics().then(setDiag)}
              >Run checks</button>
              {diag ? <pre>{JSON.stringify(diag, null, 2)}</pre> : null}
            </details>
          </section>
        )}

        {/* Drag (or arrow-key) to rebalance the story/explore pane against the
            chat pane. Double-click restores the even split. */}
        <div
          className="resize-divider"
          role="separator"
          aria-label="Resize chat panel"
          aria-orientation="vertical"
          aria-valuemin={CHAT_WIDTH_MIN}
          aria-valuemax={CHAT_WIDTH_MAX}
          aria-valuenow={Math.round(chatWidth)}
          tabIndex={0}
          onPointerDown={(e) => {
            (e.target as HTMLElement).setPointerCapture(e.pointerId);
            setResizing(true);
          }}
          onPointerMove={(e) => {
            if (!(e.target as HTMLElement).hasPointerCapture(e.pointerId)) return;
            const w = ((window.innerWidth - e.clientX) / window.innerWidth) * 100;
            setChatWidth(clampChatWidth(w));
          }}
          onPointerUp={(e) => {
            (e.target as HTMLElement).releasePointerCapture(e.pointerId);
            setResizing(false);
          }}
          onPointerCancel={() => setResizing(false)}
          onDoubleClick={() => setChatWidth(CHAT_WIDTH_DEFAULT)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") { e.preventDefault(); nudgeChatWidth(2); }
            else if (e.key === "ArrowRight") { e.preventDefault(); nudgeChatWidth(-2); }
            else if (e.key === "Home") { e.preventDefault(); setChatWidth(CHAT_WIDTH_MIN); }
            else if (e.key === "End") { e.preventDefault(); setChatWidth(CHAT_WIDTH_MAX); }
            else if (e.key === "Enter") { e.preventDefault(); setChatWidth(CHAT_WIDTH_DEFAULT); }
          }}
        >
          <span className="resize-divider-bar" />
        </div>

        <ChatPanel
          messages={messages}
          busy={busy}
          status={status}
          suggestions={suggestions}
          agentName={config.agentName}
          onSend={send}
          onStop={stop}
        />
      </main>
    </div>
  );
}
