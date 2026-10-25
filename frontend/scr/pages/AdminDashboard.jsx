import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api.js";
import { Logo } from "../components/Sidebar.jsx";

export default function AdminDashboard() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    if (!auth.getAdmin()) { nav("/auth", { replace: true }); return; }
    api("/admin/overview", { admin: true }).then(setData).catch((e) => setErr(e.message));
  }, [nav]);
  useEffect(() => { load(); }, [load]);

  const logout = () => { auth.clearAdmin(); nav("/auth", { replace: true }); };
  const envs = data ? Object.entries(data.env_status) : [];
  const missing = envs.filter(([, v]) => !v).length;

  return (
    <div className="admin">
      <header className="l-nav"><Logo /><div className="row"><span className="muted">Signed in as {data?.admin || "…"}</span><button className="btn btn-ghost" onClick={load}>Refresh</button><button className="btn btn-ghost" onClick={logout}>Log out</button></div></header>
      <main className="admin-main">
        <h1>System management</h1>
        {err && <div className="form-error">{err}</div>}
        {data && (
          <>
            <div className="stat-grid">
              {Object.entries(data.counts).map(([k, v]) => <div className="stat" key={k}><div className="stat-n">{v}</div><div className="stat-l">{k.replace("_", " ")}</div></div>)}
              <div className="stat"><div className="stat-n">{data.running_turns}</div><div className="stat-l">turns running</div></div>
            </div>
            <div className="two-col">
              <section className="card">
                <h2>Environment variables <span className={`pill ${missing ? "bad" : "ok"}`}>{missing ? `${missing} not set` : "all set"}</span></h2>
                <div className="env-list">
                  {envs.map(([k, v]) => <div className="env-row" key={k}><code>{k}</code><span className={`pill ${v ? "ok" : "bad"}`}>{v ? "set" : "not set"}</span></div>)}
                </div>
                <p className="muted small">Values are never shown. Change them in Render → Environment.</p>
              </section>
              <section className="card">
                <h2>Recent users</h2>
                <table className="tbl"><thead><tr><th>Email</th><th>Joined</th></tr></thead>
                  <tbody>{data.recent_users.map((u) => <tr key={u.id}><td>{u.email}</td><td className="muted">{new Date(u.created_at).toLocaleDateString()}</td></tr>)}</tbody></table>
              </section>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
