// Thin API client. Same origin as the Flask app (no CORS). Tokens live in browser storage;
// real authorisation is always enforced server-side.
const UK = "finix_token";
const AK = "finix_admin_token";

export const auth = {
  get: () => { try { return localStorage.getItem(UK) || ""; } catch { return ""; } },
  set: (t) => { try { localStorage.setItem(UK, t); } catch { /* ignore */ } },
  clear: () => { try { localStorage.removeItem(UK); } catch { /* ignore */ } },
  getAdmin: () => { try { return sessionStorage.getItem(AK) || ""; } catch { return ""; } },
  setAdmin: (t) => { try { sessionStorage.setItem(AK, t); } catch { /* ignore */ } },
  clearAdmin: () => { try { sessionStorage.removeItem(AK); } catch { /* ignore */ } },
};

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function parse(res) {
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { /* non-JSON body */ }
  if (!res.ok) throw new ApiError((data && data.error) || `Request failed (${res.status})`, res.status);
  return data || {};
}

export async function api(path, { method = "GET", body, admin = false, form } = {}) {
  const headers = {};
  const token = admin ? auth.getAdmin() : auth.get();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  const res = await fetch(`/api${path}`, { method, headers, body: payload });
  try {
    return await parse(res);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) {
      if (admin) { auth.clearAdmin(); window.location.assign("/auth"); }
      else if (!path.startsWith("/auth/login") && !path.startsWith("/auth/register")) {
        auth.clear(); window.location.assign("/auth");
      }
    }
    throw e;
  }
}

/** POST /chats/:id/stream and dispatch SSE events: start, trace, calc, chart, file, title, message, error, done. */
export async function streamTurn(chatId, body, onEvent, signal) {
  const res = await fetch(`/api/chats/${chatId}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${auth.get()}` },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) await parse(res);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      let kind = "message";
      const data = [];
      for (const line of block.split("\n")) {
        if (line.startsWith(":")) continue;
        if (line.startsWith("event:")) kind = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trim());
      }
      if (!data.length) continue;
      try { onEvent(kind, JSON.parse(data.join("\n"))); } catch { /* skip malformed event */ }
    }
  }
}
