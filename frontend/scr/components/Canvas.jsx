import React, { useEffect, useState } from "react";

export function ChartCard({ chart, onReply, onZoom, flash }) {
  return (
    <figure className={`chart-card ${flash ? "flash" : ""}`} id={`chart-${chart.seq}`}>
      <figcaption>
        <span className="chart-tag">{chart.tag}</span>
        <span className="chart-title" title={chart.title}>{chart.title}</span>
        <button className="reply-btn" onClick={() => onReply(chart.tag)}>[Reply]</button>
      </figcaption>
      <button className="chart-img" onClick={() => onZoom(chart)} aria-label={`Zoom ${chart.title}`}>
        <img src={chart.url} alt={chart.title} loading="lazy" />
      </button>
    </figure>
  );
}

export function Lightbox({ chart, onClose, onReply }) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const k = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  if (!chart) return null;
  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-modal="true" aria-label={chart.title}>
      <div className="lb-bar" onClick={(e) => e.stopPropagation()}>
        <span className="chart-tag">{chart.tag}</span><span className="lb-title">{chart.title}</span>
        <div className="lb-actions">
          <button className="btn btn-ghost" onClick={() => setScale((s) => Math.max(0.5, s - 0.25))}>−</button>
          <span className="lb-zoom">{Math.round(scale * 100)}%</span>
          <button className="btn btn-ghost" onClick={() => setScale((s) => Math.min(3, s + 0.25))}>+</button>
          <button className="btn btn-ghost" onClick={() => { onReply(chart.tag); onClose(); }}>[Reply]</button>
          <a className="btn btn-ghost" href={chart.url} target="_blank" rel="noreferrer">Open</a>
          <button className="btn btn-ghost" onClick={onClose} aria-label="Close">✕</button>
        </div>
      </div>
      <div className="lb-stage" onClick={(e) => e.stopPropagation()}>
        <img src={chart.url} alt={chart.title} style={{ width: `${scale * 100}%`, maxWidth: scale > 1 ? "none" : "100%" }} />
      </div>
    </div>
  );
}

export default function Canvas({ charts, files, running, onReply, flashSeq }) {
  const [zoom, setZoom] = useState(null);
  return (
    <section className="canvas" aria-label="Visual workspace">
      <div className="panel-head">
        <span>Visual workspace</span>
        <span className="muted">{charts.length ? `${charts.length} chart${charts.length > 1 ? "s" : ""}` : ""}</span>
      </div>
      <div className="canvas-scroll">
        {charts.length === 0 && !running && (
          <div className="canvas-empty">
            <div className="empty-art" aria-hidden="true">
              <svg viewBox="0 0 120 70" width="140" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 60V8" /><path d="M6 60h108" /><path d="M14 46l20-16 18 10 26-26 24 14" /></svg>
            </div>
            <h3>Charts land here</h3>
            <p>Ask about a stock, a comparison or your portfolio. Price, line, histogram, heatmap and pie charts appear as the analysis needs them.</p>
          </div>
        )}
        {charts.length === 0 && running && <div className="skeleton-grid"><div className="sk" /><div className="sk" /></div>}
        <div className="chart-grid">
          {charts.map((c) => <ChartCard key={c.seq} chart={c} onReply={onReply} onZoom={setZoom} flash={flashSeq === c.seq} />)}
          {running && charts.length > 0 && <div className="chart-card sk-card"><div className="sk" /></div>}
        </div>
        {files.length > 0 && (
          <div className="file-row">
            {files.map((f) => (
              <a key={f.url} className="file-chip" href={f.url} target="_blank" rel="noreferrer" download={f.name}>
                <span className="file-kind">{(f.kind || "file").toUpperCase()}</span><span className="file-name">{f.name}</span><span>↓</span>
              </a>
            ))}
          </div>
        )}
      </div>
      <Lightbox chart={zoom} onClose={() => setZoom(null)} onReply={onReply} />
    </section>
  );
}
