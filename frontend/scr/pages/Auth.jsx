import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, auth } from "../api.js";
import { Logo } from "../components/Sidebar.jsx";

export default function Auth() {
  const nav = useNavigate();
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const d = await api(`/auth/${mode === "login" ? "login" : "register"}`, { method: "POST", body: { email, password } });
      auth.set(d.token);
      nav("/chat", { replace: true });
    } catch (e2) {
      setErr(e2.message || "Something went wrong.");
    } finally { setBusy(false); }
  };

  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <Logo />
        <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="muted">{mode === "login" ? "Log in to continue your analysis." : "Email and password only. No third-party sign-in."}</p>
        <form onSubmit={submit}>
          <label>Email<input type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label>
          <label>Password<input type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? 1 : 8} required value={password} onChange={(e) => setPassword(e.target.value)} />
            {mode === "register" && <small className="muted">At least 8 characters.</small>}</label>
          {err && <div className="form-error" role="alert">{err}</div>}
          <button className="btn btn-primary btn-block" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}</button>
        </form>
        <p className="auth-switch">
          {mode === "login" ? "New here?" : "Already have an account?"}{" "}
          <button className="link" onClick={() => { setMode(mode === "login" ? "register" : "login"); setErr(""); }}>{mode === "login" ? "Create an account" : "Log in"}</button>
        </p>
        <Link to="/" className="muted back">← Back to home</Link>
      </div>
    </div>
  );
}
