import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { auth } from "../api.js";

export function Logo({ small }) {
  return (
    <Link to="/" className={`logo ${small ? "logo-sm" : ""}`} aria-label="FINIX AI home">
      <span className="logo-mark"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M3 17l5-6 4 3 8-9" /><path d="M15 5h5v5" /></svg></span>
      <span className="logo-text">FINIX<em>AI</em></span>
    </Link>
  );
}

export default function Sidebar({ chats, activeId, user, onNew, onDelete, onNavigate, current }) {
  const nav = useNavigate();
  const go = (to) => { onNavigate && onNavigate(); nav(to); };
  const logout = () => { auth.clear(); nav("/auth", { replace: true }); };
  return (
    <aside className="sidebar">
      <div className="sb-top"><Logo /></div>
      <button className="btn btn-primary sb-new" onClick={() => { onNavigate && onNavigate(); onNew(); }}>+ New chat</button>
      <div className="sb-label">Chats</div>
      <nav className="sb-list" aria-label="Chat history">
        {chats.length === 0 && <div className="sb-empty">No conversations yet.</div>}
        {chats.map((c) => (
          <div key={c.id} className={`sb-item ${c.id === activeId ? "active" : ""}`}>
            <button className="sb-link" onClick={() => go(`/chat/${c.id}`)} title={c.title}>{c.title}</button>
            <button className="sb-del" aria-label="Delete chat" onClick={() => onDelete(c.id)}>×</button>
          </div>
        ))}
      </nav>
      <div className="sb-bottom">
        <button className={`sb-nav ${current === "portfolio" ? "active" : ""}`} onClick={() => go("/portfolio")}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 7h18v13H3z" /><path d="M8 7V4h8v3" /></svg> Portfolio
        </button>
        <div className="sb-user">
          <div className="avatar">{(user?.email || "?")[0].toUpperCase()}</div>
          <div className="sb-email" title={user?.email}>{user?.email || "…"}</div>
          <button className="sb-out" onClick={logout} title="Log out" aria-label="Log out">⎋</button>
        </div>
      </div>
    </aside>
  );
}
