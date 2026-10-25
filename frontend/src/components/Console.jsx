import React, { useEffect, useRef, useState } from "react";

const AGENT_CLASS = { Finix: "a-finix", Rome: "a-rome", Kova: "a-kova", Dimon: "a-dimon", Frank: "a-frank", Mike: "a-mike" };
const PCT_KEYS = /(return|drawdown|cagr|volatility|vol$|var|ratio_pos|positive|share|weight|probability|shortfall)/i;
const NOT_PCT = /(sharpe|sortino|rsi|skew|kurt|beta|corr|price|sma|ema|macd|signal|band|data_frequency)/i;

function pretty(label) {
  const parts = String(label).split(".");
  const tail = parts.slice(-1)[0].replace(/_/g, " ");
  const head = parts.length > 1 ? parts[parts.length - 2] : "";
  return { head, tail };
}

function fmt(label, v) {
  if (typeof v === "number" && Number.isFinite(v)) {
    if (PCT_KEYS.test(label) && !NOT_PCT.test(label) && Math.abs(v) <= 5) return `${(v * 100).toFixed(2)}%`;
    return Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(Math.round(v * 10000) / 10000);
  }
  if (v === null || v === undefined) return "—";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

/** Auto-scroll "tail" behaviour: follows new content unless the user scrolls up. */
function useTail(dep) {
  const ref = useRef(null);
  const stick = useRef(true);
  const onScroll = () => {
    const el = ref.current;
    if (el) stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 36;
  };
  useEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [dep]);
  return { ref, onScroll, jump: () => { stick.current = true; const el = ref.current; if (el) el.scrollTop = el.scrollHeight; } };
}

function LogTab({ logs, running }) {
  const tail = useTail(logs.length);
  return (
    <div className="con-body" ref={tail.ref} onScroll={tail.onScroll} role="log" aria-live="off">
      {logs.length === 0 && <div className="con-empty">Agent activity will stream here when you send a message.</div>}
      {logs.map((l) => (
        <div className="log-line" key={l.id}>
          <span className="log-time">{l.t}</span>
          <span className={`log-agent ${AGENT_CLASS[l.agent] || ""}`}>{l.agent}</span>
          <span className="log-msg">{l.msg}</span>
        </div>
      ))}
      {running && <div className="log-line"><span className="cursor" /></div>}
    </div>
  );
}

function CalcCard({ c, index }) {
  const arg = c.args?.symbol || (c.args?.symbols || []).join(", ");
  return (
    <div className="calc-card" style={{ animationDelay: "0ms" }}>
      <div className="calc-head">
        <span className="calc-fn">{c.tool}<span className="calc-arg">{arg ? `(${arg})` : "()"}</span></span>
        <span className="calc-n">#{index + 1}</span>
      </div>
      {c.note && <div className="calc-note"><span className="calc-sigma">ƒ</span>{c.note}</div>}
      <div className="calc-rows">
        {(c.rows || []).map(([label, value], i) => {
          const p = pretty(label);
          return (
            <div className="calc-row" key={i} style={{ animationDelay: `${Math.min(i, 14) * 55}ms` }}>
              <span className="calc-k">{p.head && <i>{p.head}</i>}{p.tail}</span>
              <span className="calc-dots" />
              <span className={`calc-v ${typeof value === "number" ? (value < 0 ? "neg" : "pos") : ""}`}>{fmt(label, value)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CalcTab({ calcs, running }) {
  const tail = useTail(calcs.length);
  return (
    <div className="con-body" ref={tail.ref} onScroll={tail.onScroll}>
      {calcs.length === 0 && (
        <div className="con-empty">{running ? "Kova has not started calculating yet…" : "Calculations will scroll here live while Kova works (Sharpe, drawdown, RSI, correlations…)."}</div>
      )}
      {calcs.map((c, i) => <CalcCard key={c.id} c={c} index={i} />)}
      {running && calcs.length > 0 && <div className="log-line"><span className="cursor" /></div>}
    </div>
  );
}

export default function Console({ logs, calcs, running, tab, onTab }) {
  return (
    <section className="console" aria-label="Agent console">
      <div className="con-bar">
        <div className="seg" role="tablist" aria-label="Console view">
          <button role="tab" aria-selected={tab === "log"} className={tab === "log" ? "on" : ""} onClick={() => onTab("log")}>Live log</button>
          <button role="tab" aria-selected={tab === "calc"} className={tab === "calc" ? "on" : ""} onClick={() => onTab("calc")}>
            Calculations{calcs.length > 0 && <span className="seg-count">{calcs.length}</span>}
          </button>
        </div>
        <span className={`live-dot ${running ? "run" : ""}`}>{running ? "LIVE" : "IDLE"}</span>
      </div>
      {tab === "log" ? <LogTab logs={logs} running={running} /> : <CalcTab calcs={calcs} running={running} />}
    </section>
  );
}
