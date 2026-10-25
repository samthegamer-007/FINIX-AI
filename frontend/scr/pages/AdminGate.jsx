import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api.js";
import { Logo } from "../components/Sidebar.jsx";

export default function AdminGate() {
  const nav = useNavigate();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      const d = await api("/admin/login", { method: "POST", body: { username, password } });
      auth.setAdmin(d.token);
      nav("/admin-dashboard", { replace: true });
    } catch (e2) { setErr(e2.message); } finally { setBusy(false); }
  };
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <Logo />
        <h1>Admin access</h1>
        <p className="muted">Restricted to platform administrators.</p>
        <form onSubmit={submit}>
          <label>Username<input value={username} onChange={(e) => setU(e.target.value)} autoComplete="username" required /></label>
          <label>Password<input type="password" value={password} onChange={(e) => setP(e.target.value)} autoComplete="current-password" required /></label>
          {err && <div className="form-error" role="alert">{err}</div>}
          <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Checking…" : "Enter dashboard"}</button>
        </form>
      </div>
    </div>
  );
}
