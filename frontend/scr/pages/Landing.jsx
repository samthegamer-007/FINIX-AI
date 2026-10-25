import React from "react";
import { Link } from "react-router-dom";
import { Logo } from "../components/Sidebar.jsx";
import { auth } from "../api.js";

const AGENTS = [
  { n: "Finix", r: "Orchestrator", d: "The only agent you talk to. Plans the work, delegates, and writes the final answer." },
  { n: "Rome", r: "Data", d: "Fetches prices, fundamentals, news and web context. Raw data only, no maths." },
  { n: "Kova", r: "Quant", d: "Runs fixed, validated calculations: Sharpe, drawdown, RSI, VaR, correlation." },
  { n: "Dimon", r: "Decisions", d: "Weighs the numbers against the news and commits to a verdict with risks." },
  { n: "Frank", r: "Memory", d: "Remembers what matters about you, condensed and recalled only when relevant." },
  { n: "Mike", r: "Presenter", d: "Turns results into charts, PDF reports and CSV exports you can reply to." },
];

export default function Landing() {
  const cta = auth.get() ? "/chat" : "/auth";
  return (
    <div className="landing">
      <header className="l-nav"><Logo /><Link className="btn btn-ghost" to={cta}>{auth.get() ? "Open app" : "Log in"}</Link></header>
      <section className="hero">
        <div className="hero-glow" aria-hidden="true" />
        <p className="eyebrow">Multi-agent financial intelligence</p>
        <h1>Six specialists.<br /><span>One answer you can act on.</span></h1>
        <p className="lead">FINIX AI splits a market question across data, quant, decision, memory and presentation agents, then shows you every step, number and chart behind the verdict.</p>
        <div className="hero-cta">
          <Link className="btn btn-primary btn-lg" to="/auth">Get Started</Link>
          <span className="muted">Free to try. Informational only, not financial advice.</span>
        </div>
        <div className="hero-card" aria-hidden="true">
          <div className="hc-bar"><i /><i /><i /><span>live agent log</span></div>
          <div className="hc-line"><b className="a-finix">Finix</b> Plan: decision on AAPL → rome &gt; kova &gt; dimon &gt; mike</div>
          <div className="hc-line"><b className="a-kova">Kova</b> Running sharpe_ratio(AAPL)… <em>1.31</em></div>
          <div className="hc-line"><b className="a-dimon">Dimon</b> Verdict: hold (high confidence)</div>
          <div className="hc-line"><b className="a-mike">Mike</b> Created #Graph-04 · PDF report ready<span className="cursor" /></div>
        </div>
      </section>
      <section className="agents">
        <h2>The team</h2>
        <div className="agent-grid">
          {AGENTS.map((a) => (
            <article key={a.n} className="agent-card">
              <div className="agent-top"><span className={`agent-dot ${"a-" + a.n.toLowerCase()}`} /><h3>{a.n}</h3><span className="muted">{a.r}</span></div>
              <p>{a.d}</p>
            </article>
          ))}
        </div>
      </section>
      <footer className="l-foot">© FINIX AI · Informational only. Not financial advice.</footer>
    </div>
  );
}
