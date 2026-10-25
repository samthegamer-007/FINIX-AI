import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, streamTurn } from "../api.js";
import Sidebar, { Logo } from "../components/Sidebar.jsx";
import Canvas, { ChartCard, Lightbox } from "../components/Canvas.jsx";
import Console from "../components/Console.jsx";
import ChatPane from "../components/ChatPane.jsx";

function useMedia(q) {
  const [m, setM] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const h = () => setM(mq.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, [q]);
  return m;
}

const stamp = () => new Date().toLocaleTimeString([], { hour12: false });
let uid = 0;

export default function Chat() {
  const { chatId } = useParams();
  const nav = useNavigate();
  const mobile = useMedia("(max-width: 999px)");

  const [user, setUser] = useState(null);
  const [chats, setChats] = useState([]);
  const [messages, setMessages] = useState([]);
  const [charts, setCharts] = useState([]);
  const [liveFiles, setLiveFiles] = useState([]);
  const [logs, setLogs] = useState([]);
  const [calcs, setCalcs] = useState([]);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState("log");
  const [view, setView] = useState("chat");       // mobile only: client-side state, never a URL change
  const [drawer, setDrawer] = useState(false);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState([]);
  const [uploadError, setUploadError] = useState("");
  const [flashSeq, setFlashSeq] = useState(null);
  const [zoom, setZoom] = useState(null);
  const [loadError, setLoadError] = useState("");

  const inputRef = useRef(null);
  const skipLoad = useRef(null);
  const abortRef = useRef(null);

  const refreshChats = useCallback(() => api("/chats").then((d) => setChats(d.chats || [])).catch(() => {}), []);

  useEffect(() => {
    api("/auth/me").then((d) => setUser(d.user)).catch(() => {});
    refreshChats();
    return () => abortRef.current?.abort();
  }, [refreshChats]);

  useEffect(() => {
    setLoadError("");
    if (!chatId) { setMessages([]); setCharts([]); setLiveFiles([]); setLogs([]); setCalcs([]); return; }
    if (skipLoad.current === chatId) { skipLoad.current = null; return; }
    abortRef.current?.abort();
    setRunning(false); setLogs([]); setCalcs([]); setLiveFiles([]);
    api(`/chats/${chatId}`)
      .then((d) => { setMessages(d.messages || []); setCharts(d.charts || []); })
      .catch((e) => { setLoadError(e.message); if (e.status === 404) nav("/chat", { replace: true }); });
  }, [chatId, nav]);

  const files = useMemo(() => {
    const seen = new Map();
    [...messages.flatMap((m) => m.meta?.files || []), ...liveFiles].forEach((f) => seen.set(f.url, f));
    return [...seen.values()];
  }, [messages, liveFiles]);

  const reply = useCallback((tag) => {
    setInput((p) => (p.includes(tag) ? p : `${tag} ${p}`));
    if (mobile) setView("chat");
    setTimeout(() => inputRef.current?.focus(), 30);
  }, [mobile]);

  const focusTag = useCallback((tag) => {
    const c = charts.find((x) => x.tag.toLowerCase() === tag.toLowerCase());
    if (!c) return;
    if (mobile) setView("graph");
    setFlashSeq(c.seq);
    setTimeout(() => document.getElementById(`chart-${c.seq}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
    setTimeout(() => setFlashSeq(null), 1800);
  }, [charts, mobile]);

  const newChat = () => { abortRef.current?.abort(); setRunning(false); setInput(""); setPending([]); nav("/chat"); setView("chat"); };

  const deleteChat = async (id) => {
    if (!window.confirm("Delete this conversation?")) return;
    await api(`/chats/${id}`, { method: "DELETE" }).catch(() => {});
    setChats((cs) => cs.filter((c) => c.id !== id));
    if (id === chatId) nav("/chat", { replace: true });
  };

  const pickFile = (f) => {
    setUploadError("");
    if (!/\.(txt|csv|pdf)$/i.test(f.name)) { setUploadError("Only .txt, .csv and text-based .pdf files are supported right now."); return; }
    if (f.size > 5 * 1024 * 1024) { setUploadError("File too large (max 5 MB)."); return; }
    setPending((p) => (p.length >= 3 ? p : [...p, f]));
  };

  const send = async () => {
    const text = input.trim();
    if (!text || running) return;
    setUploadError("");
    let id = chatId;
    try {
      if (!id) {
        const d = await api("/chats", { method: "POST" });
        id = d.chat.id;
        skipLoad.current = id;
        setChats((cs) => [d.chat, ...cs]);
        nav(`/chat/${id}`);
      }
      const ids = [];
      for (const f of pending) {
        const form = new FormData();
        form.append("file", f);
        const r = await api(`/chats/${id}/upload`, { method: "POST", form });
        ids.push(r.upload.id);
      }
      setPending([]);
      setInput("");
      if (inputRef.current) inputRef.current.style.height = "auto";
      setMessages((m) => [...m, { id: `u${++uid}`, role: "user", content: text }]);
      setLogs([]); setCalcs([]); setLiveFiles([]); setTab("log");
      setRunning(true);
      const ctl = new AbortController();
      abortRef.current = ctl;
      await streamTurn(id, { message: text, attachment_ids: ids }, (kind, d) => {
        if (kind === "trace") setLogs((l) => [...l, { id: ++uid, t: stamp(), agent: d.agent, msg: d.msg }]);
        else if (kind === "calc") setCalcs((c) => [...c, { id: ++uid, ...d }]);
        else if (kind === "chart") setCharts((c) => (c.some((x) => x.seq === d.seq) ? c : [...c, d]));
        else if (kind === "file") setLiveFiles((f) => [...f, d]);
        else if (kind === "title") setChats((cs) => cs.map((c) => (c.id === id ? { ...c, title: d.title } : c)));
        else if (kind === "message") setMessages((m) => [...m, d]);
        else if (kind === "error") setMessages((m) => [...m, { id: `e${++uid}`, role: "assistant", error: true, content: d.message }]);
      }, ctl.signal);
    } catch (e) {
      if (e.name !== "AbortError") {
        setMessages((m) => [...m, { id: `e${++uid}`, role: "assistant", error: true, content: e.message || "Something went wrong." }]);
      }
    } finally {
      setRunning(false);
      refreshChats();
    }
  };

  const statusLine = logs.length ? `${logs[logs.length - 1].agent}: ${logs[logs.length - 1].msg}` : "Finix is starting…";
  const title = chats.find((c) => c.id === chatId)?.title || "New chat";

  const sidebar = (
    <Sidebar chats={chats} activeId={chatId} user={user} onNew={newChat} onDelete={deleteChat}
      onNavigate={() => setDrawer(false)} current="chat" />
  );

  const pane = (
    <ChatPane messages={messages} running={running} hasChat={!!chatId} input={input} setInput={setInput}
      inputRef={inputRef} onSend={send} onTag={focusTag} onBadge={() => setView("graph")}
      pendingFiles={pending} onPickFile={pickFile} onRemoveFile={(i) => setPending((p) => p.filter((_, k) => k !== i))}
      uploadError={uploadError || loadError} statusLine={statusLine} />
  );

  if (mobile) {
    return (
      <div className="app mobile">
        <header className="m-head">
          <button className="icon-btn" onClick={() => setDrawer(true)} aria-label="Menu">☰</button>
          <div className="m-title">{view === "graph" ? "Charts" : title}</div>
          <button className={`icon-btn bolt ${view === "graph" ? "on" : ""}`} aria-label="Toggle graph view"
            onClick={() => setView(view === "graph" ? "chat" : "graph")}>
            ⚡{charts.length > 0 && <span className="bolt-n">{charts.length}</span>}
          </button>
        </header>
        {drawer && <div className="scrim" onClick={() => setDrawer(false)} />}
        <div className={`drawer ${drawer ? "open" : ""}`}>{sidebar}</div>
        {view === "chat" ? pane : (
          <section className="m-graphs" aria-label="Chart stream">
            {charts.length === 0 && <div className="canvas-empty"><h3>No charts yet</h3><p>Ask Finix for an analysis and charts will stack up here.</p></div>}
            {charts.map((c) => <ChartCard key={c.seq} chart={c} onReply={reply} onZoom={setZoom} flash={flashSeq === c.seq} />)}
            {files.length > 0 && <div className="file-row">{files.map((f) => <a key={f.url} className="file-chip" href={f.url} target="_blank" rel="noreferrer" download={f.name}><span className="file-kind">{(f.kind || "file").toUpperCase()}</span><span className="file-name">{f.name}</span><span>↓</span></a>)}</div>}
            {running && <div className="m-status">{statusLine}</div>}
          </section>
        )}
        <Lightbox chart={zoom} onClose={() => setZoom(null)} onReply={reply} />
      </div>
    );
  }

  return (
    <div className="app desktop">
      {sidebar}
      <main className="center">
        <Canvas charts={charts} files={files} running={running} onReply={reply} flashSeq={flashSeq} />
        <Console logs={logs} calcs={calcs} running={running} tab={tab} onTab={setTab} />
      </main>
      {pane}
    </div>
  );
}
