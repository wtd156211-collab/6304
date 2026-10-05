"""单文件 HTML 报告：内联数据与样式，原生 ES module 渲染，file:// 直接打开。"""

from __future__ import annotations

import json

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>状态机迁移表评审报告</title>
<style>
body { font-family: "PingFang SC", "Microsoft YaHei", system-ui, sans-serif; margin: 0; color: #222; }
header { padding: 14px 20px; background: #1f2933; color: #fff; }
header h1 { font-size: 18px; margin: 0 0 8px; }
nav a { color: #9fd3ff; margin-right: 14px; font-size: 13px; }
.legend { padding: 8px 20px; font-size: 12px; color: #555; background: #f4f4f4; border-bottom: 1px solid #ddd; }
.swatch { display: inline-block; width: 12px; height: 12px; vertical-align: -2px; margin: 0 4px 0 14px; }
section.machine { padding: 16px 20px 30px; border-bottom: 2px solid #ccc; }
section.machine h2 { font-size: 16px; margin: 4px 0; }
.summary { color: #555; font-size: 13px; margin-bottom: 10px; }
.graph-wrap { overflow: auto; max-height: 70vh; border: 1px solid #ddd; background: #fafafa; margin-bottom: 14px; }
.edge { stroke: #9aa0a6; stroke-width: 1.4; fill: none; }
.edge.conflict { stroke: #d62728; stroke-width: 2.2; }
.edge-label { font-size: 10px; fill: #666; }
.edge-label.conflict { fill: #d62728; font-weight: 700; }
.trap-region { fill: rgba(214, 39, 40, 0.07); stroke: #d62728; stroke-width: 1.6; stroke-dasharray: 7 4; }
.trap-label { font-size: 11px; fill: #d62728; font-weight: 700; }
.node rect { fill: #fff; stroke: #5f6368; stroke-width: 1.4; }
.node text { font-size: 12px; fill: #222; }
.node.unreachable rect { fill: #d7d7d7; stroke: #a0a0a0; }
.node.unreachable text { fill: #808080; }
.node.initial rect { stroke: #188038; stroke-width: 2.8; }
.columns { display: flex; gap: 32px; flex-wrap: wrap; }
.columns > div { min-width: 280px; }
h3 { font-size: 14px; margin: 8px 0; }
table { border-collapse: collapse; font-size: 13px; }
th, td { border: 1px solid #ddd; padding: 3px 12px; text-align: left; }
tr.unreachable td { color: #999; background: #f2f2f2; }
ul.problems { font-size: 13px; padding-left: 18px; margin: 4px 0; }
ul.problems li { margin: 2px 0; }
code { font-family: ui-monospace, Consolas, monospace; }
</style>
</head>
<body>
<header>
<h1>状态机迁移表评审报告</h1>
<nav id="nav"></nav>
</header>
<div class="legend">图例：<span class="swatch" style="background:#fff"></span>可达
<span class="swatch" style="background:#d7d7d7"></span>不可达
<span class="swatch" style="background:#fff;border:2px solid #188038"></span>初始状态
<span class="swatch" style="background:#fff;border:2px solid #d62728"></span>冲突迁移（红边）
<span class="swatch" style="background:rgba(214,39,40,0.15);border:1px dashed #d62728"></span>死循环块 TRAP（红虚线框）</div>
<main id="app"></main>
<script type="module">
const DATA = __DATA__;

const SVGNS = "http://www.w3.org/2000/svg";
const NODE_W = 150, NODE_H = 40, GAP_X = 36, GAP_Y = 84, PAD = 48;

function svgEl(tag, attrs, text) {
  const node = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

function layout(m) {
  const n = m.states.length;
  const adj = Array.from({ length: n }, () => []);
  for (const e of m.edges) adj[e[0]].push(e[2]);
  const layer = new Array(n).fill(-1);
  let maxLayer = 0;
  const queue = [];
  let head = 0;
  const seed = (s, l) => {
    if (layer[s] < 0) {
      layer[s] = l;
      if (l > maxLayer) maxLayer = l;
      queue.push(s);
    }
  };
  for (const s of m.initial) seed(s, 0);
  const drain = () => {
    while (head < queue.length) {
      const u = queue[head++];
      for (const v of adj[u]) seed(v, layer[u] + 1);
    }
  };
  drain();
  for (let s = 0; s < n; s++) if (layer[s] < 0) { seed(s, maxLayer + 1); drain(); }
  const layers = [];
  for (let s = 0; s < n; s++) (layers[layer[s]] ??= []).push(s);
  let maxWidth = 1;
  for (const members of layers) maxWidth = Math.max(maxWidth, members.length);
  const W = PAD * 2 + maxWidth * (NODE_W + GAP_X) - GAP_X;
  const H = PAD * 2 + layers.length * (NODE_H + GAP_Y) - GAP_Y;
  const pos = new Array(n);
  layers.forEach((members, l) => {
    const rowW = members.length * (NODE_W + GAP_X) - GAP_X;
    const x0 = (W - rowW) / 2;
    members.forEach((s, i) => {
      pos[s] = { x: x0 + i * (NODE_W + GAP_X) + NODE_W / 2, y: PAD + l * (NODE_H + GAP_Y) + NODE_H / 2 };
    });
  });
  return { pos, W, H };
}

function renderGraph(m, idx) {
  const { pos, W, H } = layout(m);
  const svg = svgEl("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}` });
  const defs = svgEl("defs", {});
  const mk = (id, color) => {
    const marker = svgEl("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5,
      markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" });
    marker.appendChild(svgEl("path", { d: "M 0 0 L 10 5 L 0 10 z", fill: color }));
    return marker;
  };
  defs.appendChild(mk(`arrow-${idx}`, "#9aa0a6"));
  defs.appendChild(mk(`arrow-c-${idx}`, "#d62728"));
  svg.appendChild(defs);

  for (const block of m.traps) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const s of block) {
      const p = pos[s];
      x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y);
      x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y);
    }
    const pad = 26;
    svg.appendChild(svgEl("rect", {
      x: x0 - NODE_W / 2 - pad, y: y0 - NODE_H / 2 - pad,
      width: x1 - x0 + NODE_W + 2 * pad, height: y1 - y0 + NODE_H + 2 * pad,
      rx: 18, class: "trap-region" }));
    svg.appendChild(svgEl("text", { x: x0 - NODE_W / 2 - pad + 10,
      y: y0 - NODE_H / 2 - pad + 17, class: "trap-label" }, "TRAP"));
  }

  const merged = new Map();
  for (const [u, cond, v, conflict] of m.edges) {
    const key = u + ">" + v;
    let e = merged.get(key);
    if (!e) { e = { u, v, conds: [], conflict: false }; merged.set(key, e); }
    if (!e.conds.includes(cond)) e.conds.push(cond);
    if (conflict) e.conflict = true;
  }
  for (const e of merged.values()) {
    const p1 = pos[e.u], p2 = pos[e.v];
    const cls = "edge" + (e.conflict ? " conflict" : "");
    const lcls = "edge-label" + (e.conflict ? " conflict" : "");
    const arrow = `url(#${e.conflict ? `arrow-c-${idx}` : `arrow-${idx}`})`;
    const label = e.conds.join(",");
    if (e.u === e.v) {
      const y = p1.y - NODE_H / 2;
      svg.appendChild(svgEl("path", {
        d: `M ${p1.x - 16} ${y} C ${p1.x - 16} ${y - 46}, ${p1.x + 16} ${y - 46}, ${p1.x + 16} ${y - 2}`,
        class: cls, "marker-end": arrow }));
      svg.appendChild(svgEl("text", { x: p1.x, y: y - 52, "text-anchor": "middle", class: lcls }, label));
    } else {
      const dx = p2.x - p1.x, dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy) || 1;
      const sx = p1.x + dx / len * 30, sy = p1.y + dy / len * 24;
      const tx = p2.x - dx / len * 38, ty = p2.y - dy / len * 28;
      svg.appendChild(svgEl("line", { x1: sx, y1: sy, x2: tx, y2: ty, class: cls, "marker-end": arrow }));
      svg.appendChild(svgEl("text", { x: (sx + tx) / 2, y: (sy + ty) / 2 - 5,
        "text-anchor": "middle", class: lcls }, label));
    }
  }

  const initialSet = new Set(m.initial);
  m.states.forEach((name, s) => {
    const p = pos[s];
    const cls = "node" + (m.reachable[s] ? "" : " unreachable") + (initialSet.has(s) ? " initial" : "");
    const g = svgEl("g", { class: cls });
    g.appendChild(svgEl("title", {}, name));
    g.appendChild(svgEl("rect", { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2,
      width: NODE_W, height: NODE_H, rx: 8 }));
    g.appendChild(svgEl("text", { x: p.x, y: p.y + 4, "text-anchor": "middle" }, name));
    svg.appendChild(g);
  });
  return svg;
}

function renderMachine(m, idx) {
  const sec = document.createElement("section");
  sec.className = "machine";
  sec.id = `m-${idx}`;
  const h2 = document.createElement("h2");
  h2.textContent = m.name;
  sec.appendChild(h2);
  const r = m.reachable.filter(Boolean).length;
  const summary = document.createElement("div");
  summary.className = "summary";
  summary.textContent = `状态=${m.states.length} 可达=${r} 问题=${m.problems.length}`;
  sec.appendChild(summary);
  const wrap = document.createElement("div");
  wrap.className = "graph-wrap";
  wrap.appendChild(renderGraph(m, idx));
  sec.appendChild(wrap);

  const cols = document.createElement("div");
  cols.className = "columns";
  const left = document.createElement("div");
  const h3a = document.createElement("h3");
  h3a.textContent = "状态表";
  left.appendChild(h3a);
  const table = document.createElement("table");
  const head = document.createElement("tr");
  for (const t of ["状态", "可达性"]) {
    const th = document.createElement("th");
    th.textContent = t;
    head.appendChild(th);
  }
  table.appendChild(head);
  m.states.forEach((name, i) => {
    const tr = document.createElement("tr");
    if (!m.reachable[i]) tr.className = "unreachable";
    const td1 = document.createElement("td");
    td1.textContent = name;
    const td2 = document.createElement("td");
    td2.textContent = m.reachable[i] ? "可达" : "不可达";
    tr.appendChild(td1);
    tr.appendChild(td2);
    table.appendChild(tr);
  });
  left.appendChild(table);
  cols.appendChild(left);

  const right = document.createElement("div");
  const h3b = document.createElement("h3");
  h3b.textContent = "问题清单";
  right.appendChild(h3b);
  const ul = document.createElement("ul");
  ul.className = "problems";
  if (m.problems.length === 0) {
    const li = document.createElement("li");
    li.textContent = "（无问题）";
    ul.appendChild(li);
  } else {
    for (const p of m.problems) {
      const li = document.createElement("li");
      const code = document.createElement("code");
      code.textContent = p;
      li.appendChild(code);
      ul.appendChild(li);
    }
  }
  right.appendChild(ul);
  cols.appendChild(right);
  sec.appendChild(cols);
  return sec;
}

const nav = document.getElementById("nav");
const app = document.getElementById("app");
DATA.machines.forEach((m, idx) => {
  const a = document.createElement("a");
  a.href = `#m-${idx}`;
  a.textContent = m.name;
  nav.appendChild(a);
  app.appendChild(renderMachine(m, idx));
});
</script>
</body>
</html>
"""


def render_html(payload: dict) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")
    return _TEMPLATE.replace("__DATA__", data)
