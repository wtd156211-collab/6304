"""report.html 的单文件模板；__DATA__ 占位符会被引擎输出的 JSON 替换。"""

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>状态机审计报告</title>
<style>
body { font-family: system-ui, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 0; color: #202124; background: #fff; }
header { padding: 14px 24px; border-bottom: 1px solid #e0e0e0; position: sticky; top: 0; background: #fff; z-index: 10; }
h1 { font-size: 20px; margin: 0 0 8px; }
h2 { font-size: 17px; margin: 0 0 6px; }
h3 { font-size: 14px; margin: 14px 0 6px; }
nav a { margin-right: 14px; font-size: 13px; }
.legend { font-size: 12px; color: #5f6368; margin-top: 6px; }
.legend b { font-weight: 600; }
section { padding: 16px 24px 24px; border-bottom: 1px solid #eee; }
.summary { font-size: 13px; color: #5f6368; margin: 0 0 10px; }
.hint { font-size: 12px; color: #9aa0a6; margin: 4px 0 0; }
.graph { width: 100%; height: 560px; border: 1px solid #e0e0e0; border-radius: 8px; background: #fafafa; touch-action: none; cursor: grab; }
.graph:active { cursor: grabbing; }
.edge { fill: none; stroke: #5f6368; stroke-width: 1.4; }
.edge.conflict { stroke: #d93025; stroke-width: 2.2; }
.arrow { fill: #5f6368; }
.arrow-conflict { fill: #d93025; }
.edge-label { font-size: 11px; fill: #5f6368; text-anchor: middle; paint-order: stroke; stroke: #fafafa; stroke-width: 3; }
.edge-label.conflict { fill: #d93025; font-weight: 600; }
.node rect { fill: #e8f0fe; stroke: #1a73e8; stroke-width: 1.4; }
.node text { font-size: 13px; text-anchor: middle; dominant-baseline: central; fill: #202124; }
.node.unreachable rect { fill: #f1f3f4; stroke: #9aa0a6; stroke-dasharray: 4 3; }
.node.unreachable text { fill: #9aa0a6; }
.node.terminal rect { stroke: #188038; stroke-width: 2.6; }
.initial-marker { fill: #1a73e8; }
.trap-region { fill: rgba(217, 48, 37, .07); stroke: #d93025; stroke-width: 1.6; stroke-dasharray: 8 5; }
.trap-label { fill: #d93025; font-size: 12px; font-weight: 700; }
.cols { display: flex; gap: 40px; flex-wrap: wrap; }
table { border-collapse: collapse; }
th, td { border: 1px solid #e0e0e0; padding: 4px 14px; font-size: 13px; text-align: left; }
tr.unreachable td { color: #9aa0a6; background: #f8f9fa; }
ol.problems { margin: 6px 0 0; padding-left: 22px; }
ol.problems li { margin: 2px 0; }
ol.problems code { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; font-size: 12.5px; }
p.ok { color: #188038; font-size: 13px; }
</style>
</head>
<body>
<header>
<h1>状态机审计报告</h1>
<nav id="nav"></nav>
<div class="legend">
<b>图例</b>：
灰虚线节点 = 不可达（UNREACHABLE）｜
红虚线框 = 死循环块（TRAP，进去出不来）｜
红边 = 冲突迁移（CONFLICT，同条件多目标）｜
绿框节点 = 终止状态（TERMINAL）｜
蓝三角 = 初始状态。
拖拽平移，滚轮缩放，双击复位。
</div>
</header>
<main id="machines"></main>
<script type="module">
const DATA = __DATA__;

const esc = s => String(s).replace(/[&<>"']/g, c => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
));
const R = v => Math.round(v * 10) / 10;

function borderPoint(node, tx, ty) {
  const dx = tx - node.x, dy = ty - node.y;
  const rx = node.w / 2 + 2, ry = node.h / 2 + 2;
  const t = 1 / Math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry));
  return { x: node.x + dx * t, y: node.y + dy * t };
}

function drawGraph(svg, m, mi) {
  const nodes = m.layout.nodes;
  svg.setAttribute("viewBox", `0 0 ${m.layout.width} ${m.layout.height}`);
  const defs = `<defs>
    <marker id="arr${mi}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arrow"/></marker>
    <marker id="arrc${mi}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="arrow-conflict"/></marker>
  </defs>`;

  const trapParts = [];
  for (const trap of m.traps) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const i of trap) {
      const nd = nodes[i];
      x0 = Math.min(x0, nd.x - nd.w / 2); y0 = Math.min(y0, nd.y - nd.h / 2);
      x1 = Math.max(x1, nd.x + nd.w / 2); y1 = Math.max(y1, nd.y + nd.h / 2);
    }
    const p = 26;
    trapParts.push(`<rect class="trap-region" x="${R(x0 - p)}" y="${R(y0 - p)}" width="${R(x1 - x0 + 2 * p)}" height="${R(y1 - y0 + 2 * p)}" rx="22"/>`);
    trapParts.push(`<text class="trap-label" x="${R(x0 - p + 10)}" y="${R(y0 - p + 18)}">TRAP</text>`);
  }

  const groups = new Map();
  for (const e of m.edges) {
    const key = e.u <= e.v ? e.u + "|" + e.v : e.v + "|" + e.u;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(e);
  }
  const edgeParts = [], labelParts = [];
  for (const list of groups.values()) {
    const k = list.length;
    list.forEach((e, i) => {
      const cls = e.k ? "edge conflict" : "edge";
      const lcls = e.k ? "edge-label conflict" : "edge-label";
      const marker = e.k ? `arrc${mi}` : `arr${mi}`;
      if (e.u === e.v) {
        const nd = nodes[e.u];
        const h = 34 + i * 20;
        const xa = nd.x - 12, xb = nd.x + 12, y = nd.y - nd.h / 2;
        edgeParts.push(`<path class="${cls}" marker-end="url(#${marker})" d="M ${R(xa)} ${R(y)} C ${R(xa)} ${R(y - h)}, ${R(xb)} ${R(y - h)}, ${R(xb)} ${R(y - 1)}"/>`);
        labelParts.push(`<text class="${lcls}" x="${R(nd.x)}" y="${R(y - h - 5)}">${esc(e.c)}</text>`);
        return;
      }
      const a = nodes[e.u], b = nodes[e.v];
      const off = (i - (k - 1) / 2) * 26;
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = Math.hypot(dx, dy) || 1;
      const cx = (a.x + b.x) / 2 - (dy / len) * off;
      const cy = (a.y + b.y) / 2 + (dx / len) * off;
      const p0 = borderPoint(a, cx, cy), p1 = borderPoint(b, cx, cy);
      edgeParts.push(`<path class="${cls}" marker-end="url(#${marker})" d="M ${R(p0.x)} ${R(p0.y)} Q ${R(cx)} ${R(cy)} ${R(p1.x)} ${R(p1.y)}"/>`);
      const lx = 0.25 * p0.x + 0.5 * cx + 0.25 * p1.x;
      const ly = 0.25 * p0.y + 0.5 * cy + 0.25 * p1.y;
      labelParts.push(`<text class="${lcls}" x="${R(lx)}" y="${R(ly)}">${esc(e.c)}</text>`);
    });
  }

  const termSet = new Set(m.terminals);
  const initSet = new Set(m.initials);
  const nodeParts = [];
  m.states.forEach((s, i) => {
    const nd = nodes[i];
    const cls = ["node"];
    if (!m.reachable[i]) cls.push("unreachable");
    if (termSet.has(i)) cls.push("terminal");
    const x = nd.x - nd.w / 2, y = nd.y - nd.h / 2;
    const marker = initSet.has(i)
      ? `<path class="initial-marker" d="M ${R(x - 16)} ${R(nd.y - 7)} L ${R(x - 16)} ${R(nd.y + 7)} L ${R(x - 5)} ${R(nd.y)} z"/>`
      : "";
    nodeParts.push(`${marker}<g class="${cls.join(" ")}"><rect x="${R(x)}" y="${R(y)}" width="${R(nd.w)}" height="${R(nd.h)}" rx="17"/><text x="${R(nd.x)}" y="${R(nd.y)}">${esc(s)}</text></g>`);
  });

  svg.innerHTML = defs + '<g class="viewport">'
    + trapParts.join("") + edgeParts.join("") + labelParts.join("") + nodeParts.join("")
    + "</g>";
}

function enablePanZoom(svg) {
  const vp = svg.querySelector(".viewport");
  let scale = 1, tx = 0, ty = 0;
  const apply = () => vp.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);
  const toSvg = ev => {
    const pt = svg.createSVGPoint();
    pt.x = ev.clientX; pt.y = ev.clientY;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  };
  svg.addEventListener("wheel", ev => {
    ev.preventDefault();
    const f = ev.deltaY < 0 ? 1.2 : 1 / 1.2;
    const p = toSvg(ev);
    tx = tx + scale * p.x * (1 - f);
    ty = ty + scale * p.y * (1 - f);
    scale *= f;
    apply();
  }, { passive: false });
  let drag = null;
  svg.addEventListener("pointerdown", ev => {
    drag = { x: ev.clientX, y: ev.clientY, tx, ty };
    svg.setPointerCapture(ev.pointerId);
  });
  svg.addEventListener("pointermove", ev => {
    if (!drag) return;
    const rect = svg.getBoundingClientRect();
    const unit = svg.viewBox.baseVal.width / rect.width;
    tx = drag.tx + (ev.clientX - drag.x) * unit;
    ty = drag.ty + (ev.clientY - drag.y) * unit;
    apply();
  });
  svg.addEventListener("pointerup", () => { drag = null; });
  svg.addEventListener("pointercancel", () => { drag = null; });
  svg.addEventListener("dblclick", () => { scale = 1; tx = 0; ty = 0; apply(); });
}

function renderMachine(m, mi) {
  const section = document.createElement("section");
  section.id = "m" + mi;
  const reachCount = m.reachable.filter(Boolean).length;
  const rows = m.states.map((s, i) =>
    `<tr class="${m.reachable[i] ? "" : "unreachable"}"><td>${esc(s)}</td><td>${m.reachable[i] ? "可达" : "不可达"}</td></tr>`
  ).join("");
  const problems = m.problems.length
    ? `<ol class="problems">${m.problems.map(p => `<li><code>${esc(p)}</code></li>`).join("")}</ol>`
    : '<p class="ok">无问题</p>';
  section.innerHTML = `
    <h2>${esc(m.name)}</h2>
    <p class="summary">状态=${m.states.length}　可达=${reachCount}　问题=${m.problems.length}</p>
    <svg class="graph" preserveAspectRatio="xMidYMid meet"></svg>
    <p class="hint">上图标记与下方清单均来自 stateaudit 引擎输出。</p>
    <div class="cols">
      <div><h3>状态表（规范顺序）</h3>
        <table><thead><tr><th>状态</th><th>可达性</th></tr></thead><tbody>${rows}</tbody></table>
      </div>
      <div><h3>问题清单</h3>${problems}</div>
    </div>`;
  return section;
}

const nav = document.getElementById("nav");
const main = document.getElementById("machines");
DATA.machines.forEach((m, mi) => {
  const link = document.createElement("a");
  link.href = "#m" + mi;
  link.textContent = m.name;
  nav.appendChild(link);
  const section = renderMachine(m, mi);
  main.appendChild(section);
  const svg = section.querySelector("svg.graph");
  drawGraph(svg, m, mi);
  enablePanZoom(svg);
});
</script>
</body>
</html>
"""
