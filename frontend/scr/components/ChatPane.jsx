import React, { useEffect, useRef } from "react";
import Markdown from "./Markdown.jsx";

const STARTERS = [
  "Should I hold AAPL? Give me a PDF report.",
  "Compare NVDA vs AMD over the last year with charts.",
  "How risky is my declared portfolio?",
  "Is RELIANCE.NS overbought right now?",
];

const STANCE = { buy: "up", add: "up", hold: "mid", neutral: "mid", reduce: "down", sell: "down", avoid: "down", rebalance: "mid" };

function Bubble({ m, onTag, onBadge }) {
  const charts = m.meta?.charts || [];
  const files = m.meta?.files || [];
  const dec = m.meta?.decision;
  if (m.role === "user") return <div className="msg user"><div className="bubble">{m.content}</div></div>;
  return (
    <div className="msg assistant">
      <div className={`bubble ${m.error ? "err" : ""}`}>
        {charts.length > 0 && (
          <button className="viz-badge" onClick={onBadge} title="Open charts" aria-label={`${charts.length} charts`}>⚡ {charts.length}</button>
        )}
        {dec?.stance && <span className={`stance ${STANCE[dec.stance] || "mid"}`}>{String(dec.stance).toUpperCase()}{dec.confidence ? ` · ${dec.confidence}` : ""}</span>}
        <Markdown text={m.content} onTag={onTag} />
        {charts.length > 0 && (
          <div className="chip-row">
            {charts.map((c) => <button key={c.tag} className="chip" onClick={() => onTag(c.tag)}>{c.tag}<span>{c.title}</span></button>)}
          </div>
        )}
        {files.length > 0 && (
          <div className="chip-row">
            {files.map((f) => <a key={f.url} className="chip file" href={f.url} target="_blank" rel="noreferrer" download={f.name}>↓ <span>{f.name}</span></a>)}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ChatPane({ messages, running, hasChat, input, setInput, inputRef, onSend, onTag, onBadge, pendingFiles, onPickFile, onRemoveFile, uploadError, statusLine }) {
  const endRef = useRef(null);
  const fileRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [messages.length, running]);

  const keyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
  };

  return (
    <section className="chat-pane" aria-label="Conversation">
      <div className="msgs">
        {messages.length === 0 && !hasChat && (
          <div className="hub">
            <h2>What should we analyse?</h2>
            <p>Finix coordinates Rome, Kova, Dimon, Frank and Mike to research, calculate, decide and visualise.</p>
            <div className="starters">
              {STARTERS.map((s) => <button key={s} className="starter" onClick={() => { setInput(s); inputRef.current?.focus(); }}>{s}</button>)}
            </div>
          </div>
        )}
        {messages.map((m, i) => <Bubble key={m.id || i} m={m} onTag={onTag} onBadge={onBadge} />)}
        {running && (
          <div className="msg assistant"><div className="bubble typing" aria-live="polite">
            <span className="dots"><i /><i /><i /></span><span className="typing-text">{statusLine || "Working…"}</span>
          </div></div>
        )}
        <div ref={endRef} />
      </div>
      <div className="composer">
        {pendingFiles.length > 0 && (
          <div className="pending">
            {pendingFiles.map((f, i) => <span className="pend-chip" key={i}>{f.name}<button onClick={() => onRemoveFile(i)} aria-label="Remove file">×</button></span>)}
          </div>
        )}
        {uploadError && <div className="form-error">{uploadError}</div>}
        <div className="input-bar">
          <button className="icon-btn" onClick={() => fileRef.current?.click()} title="Attach a .txt, .csv or text PDF (max 5 MB)" aria-label="Attach file">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8L12 2zM19 14l.9 2.6L22.5 17.5l-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9L19 14z" /></svg>
          </button>
          <input ref={fileRef} type="file" accept=".txt,.csv,.pdf" hidden onChange={(e) => { if (e.target.files[0]) onPickFile(e.target.files[0]); e.target.value = ""; }} />
          <textarea ref={inputRef} rows={1} value={input} placeholder="Ask Finix anything…"
            onChange={(e) => { setInput(e.target.value); e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 140)}px`; }}
            onKeyDown={keyDown} maxLength={4000} aria-label="Message" />
          <button className="send-btn" onClick={onSend} disabled={running || !input.trim()} aria-label="Send">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
          </button>
        </div>
        <div className="disclaimer">Informational only. Not financial advice.</div>
      </div>
    </section>
  );
}
