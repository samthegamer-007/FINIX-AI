import React from "react";

// Tiny, safe markdown renderer (no HTML injection): headings, bullets, tables, bold/italic/code,
// and clickable #Graph-NN tags.
const TAG = /(#Graph-\d+)/gi;

function inline(text, onTag, key) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_|`[^`]+`)/g;
  let last = 0, m, n = 0;
  const pushPlain = (t) => {
    t.split(TAG).forEach((part, i) => {
      if (/^#Graph-\d+$/i.test(part)) {
        out.push(<button key={`${key}t${n++}`} className="tag-link" onClick={() => onTag && onTag(part)}>{part}</button>);
      } else if (part) out.push(part);
    });
  };
  while ((m = re.exec(text))) {
    if (m.index > last) pushPlain(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**") || tok.startsWith("__")) out.push(<strong key={`${key}b${n++}`}>{inline(tok.slice(2, -2), onTag, `${key}b${n}`)}</strong>);
    else if (tok.startsWith("`")) out.push(<code key={`${key}c${n++}`}>{tok.slice(1, -1)}</code>);
    else out.push(<em key={`${key}i${n++}`}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) pushPlain(text.slice(last));
  return out;
}

export default function Markdown({ text = "", onTag }) {
  const lines = String(text).replace(/\r/g, "").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const ln = lines[i];
    if (!ln.trim()) { i++; continue; }
    const h = ln.match(/^(#{1,4})\s+(.*)$/);
    if (h && !/^#Graph-/i.test(ln)) { blocks.push(<h4 key={i} className="md-h">{inline(h[2], onTag, i)}</h4>); i++; continue; }
    if (/^\s*[-*•]\s+/.test(ln)) {
      const items = [];
      while (i < lines.length && /^\s*[-*•]\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*[-*•]\s+/, "")); i++; }
      blocks.push(<ul key={`u${i}`}>{items.map((t, k) => <li key={k}>{inline(t, onTag, `${i}-${k}`)}</li>)}</ul>);
      continue;
    }
    if (ln.includes("|") && i + 1 < lines.length && /^\s*\|?[\s:-]+\|[\s|:-]*$/.test(lines[i + 1])) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(ln); i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|")) { rows.push(cells(lines[i])); i++; }
      blocks.push(
        <div key={`t${i}`} className="md-table"><table><thead><tr>{head.map((c, k) => <th key={k}>{inline(c, onTag, k)}</th>)}</tr></thead>
          <tbody>{rows.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j}>{inline(c, onTag, `${k}${j}`)}</td>)}</tr>)}</tbody></table></div>
      );
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^\s*[-*•]\s+/.test(lines[i]) && !/^#{1,4}\s/.test(lines[i])) { para.push(lines[i]); i++; }
    blocks.push(<p key={`p${i}`}>{inline(para.join(" "), onTag, `p${i}`)}</p>);
  }
  return <div className="md">{blocks}</div>;
}
