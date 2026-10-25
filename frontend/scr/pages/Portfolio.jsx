import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api.js";
import Sidebar from "../components/Sidebar.jsx";

export default function Portfolio() {
  const nav = useNavigate();
  const [user, setUser] = useState(null);
  const [chats, setChats] = useState([]);
  const [holdings, setHoldings] = useState([]);
  const [memory, setMemory] = useState([]);
  const [form, setForm] = useState({ symbol: "", quantity: "", avg_price: "", currency: "USD" });
  const [err, setErr] = useState("");
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    api("/auth/me").then((d) => setUser(d.user)).catch(() => {});
    api("/chats").then((d) => setChats(d.chats || [])).catch(() => {});
    api("/portfolio").then((d) => { setHoldings(d.holdings || []); setMemory(d.memory || []); }).catch((e) => setErr(e.message));
  }, []);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const add = async (e) => {
    e.preventDefault(); setErr("");
    try {
      const d = await api("/portfolio/holdings", { method: "PUT", body: form });
      setHoldings(d.holdings); setForm({ symbol: "", quantity: "", avg_price: "", currency: form.currency });
    } catch (e2) { setErr(e2.message); }
  };
  const remove = async (s) => { const d = await api(`/portfolio/holdings/${encodeURIComponent(s)}`, { method: "DELETE" }); setHoldings(d.holdings); };
  const forget = async (id) => { await api(`/memory/${id}`, { method: "DELETE" }); setMemory((m) => m.filter((x) => x.id !== id)); };

  return (
    <div className="app page-app">
      {drawer && <div className="scrim" onClick={() => setDrawer(false)} />}
      <div className={`sb-wrap ${drawer ? "open" : ""}`}>
        <Sidebar chats={chats} user={user} activeId={null} current="portfolio" onNavigate={() => setDrawer(false)}
          onNew={() => nav("/chat")} onDelete={async (id) => { await api(`/chats/${id}`, { method: "DELETE" }).catch(() => {}); setChats((c) => c.filter((x) => x.id !== id)); }} />
      </div>
      <main className="page">
        <div className="page-head">
          <button className="icon-btn only-mobile" onClick={() => setDrawer(true)} aria-label="Menu">☰</button>
          <h1>Portfolio</h1>
        </div>
        <p className="muted">Declare what you hold. Finix uses it for portfolio questions and never assumes holdings you haven't listed.</p>
        <form className="hold-form" onSubmit={add}>
          <input placeholder="Ticker e.g. AAPL" value={form.symbol} onChange={set("symbol")} required aria-label="Ticker" />
          <input placeholder="Quantity" type="number" step="any" min="0" value={form.quantity} onChange={set("quantity")} required aria-label="Quantity" />
          <input placeholder="Avg price (optional)" type="number" step="any" min="0" value={form.avg_price} onChange={set("avg_price")} aria-label="Average price" />
          <input placeholder="USD" maxLength={5} value={form.currency} onChange={set("currency")} aria-label="Currency" />
          <button className="btn btn-primary">Add / update</button>
        </form>
        {err && <div className="form-error">{err}</div>}
        <div className="card">
          <table className="tbl">
            <thead><tr><th>Symbol</th><th>Quantity</th><th>Avg price</th><th>Currency</th><th /></tr></thead>
            <tbody>
              {holdings.length === 0 && <tr><td colSpan={5} className="muted">No holdings declared yet.</td></tr>}
              {holdings.map((h) => (
                <tr key={h.symbol}><td><b>{h.symbol}</b></td><td>{h.quantity}</td><td>{h.avg_price ?? "—"}</td><td>{h.currency}</td>
                  <td className="r"><button className="link danger" onClick={() => remove(h.symbol)}>Remove</button></td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <h2>What Frank remembers</h2>
        <p className="muted">Condensed notes Frank keeps to personalise future answers. Delete anything you don't want kept.</p>
        <div className="card mem-list">
          {memory.length === 0 && <div className="muted pad">Nothing stored yet.</div>}
          {memory.map((m) => (
            <div className="mem" key={m.id}>
              <div><span className="mem-kind">{m.kind}</span><b>{m.topic}</b><p>{m.summary}</p></div>
              <button className="link danger" onClick={() => forget(m.id)}>Forget</button>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
