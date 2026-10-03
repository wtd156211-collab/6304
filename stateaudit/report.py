"""产出逐行文本、report.json 与自包含 report.html。

图布局在 Python 侧完成（分层布局：SCC 缩点成 DAG 后按最长路径分层），
坐标随数据一起内嵌进 HTML，保证同一份迁移表两次生成的页面完全一致。
"""
from __future__ import annotations

import heapq
import json
from pathlib import Path

from .analyze import Analysis
from .html_template import HTML_TEMPLATE

_NODE_H = 36
_NODE_GAP_Y = 14
_COMP_GAP_Y = 46
_LAYER_GAP_X = 180
_MARGIN_X = 80
_MARGIN_BOTTOM = 80


def reachability_text(analysis: Analysis) -> str:
    states = analysis.machine.states
    return "".join(
        f"{state}\t{'可达' if analysis.reachable[i] else '不可达'}\n"
        for i, state in enumerate(states)
    )


def problems_text(analysis: Analysis) -> str:
    return "".join(line + "\n" for line in analysis.problems)


def _text_width(name: str) -> int:
    units = sum(2 if ord(ch) > 0x2E7F else 1 for ch in name)
    return max(48, units * 7 + 22)


def compute_layout(analysis: Analysis) -> dict:
    """分层布局：SCC 缩点 -> Kahn 拓扑 -> 最长路径分层；返回节点中心坐标与画布尺寸。"""
    machine = analysis.machine
    n = len(machine.states)
    index_of = {state: i for i, state in enumerate(machine.states)}
    components = analysis.components
    comp_of = analysis.comp_of

    succs: list[set[int]] = [set() for _ in components]
    preds: list[set[int]] = [set() for _ in components]
    self_loops = [0] * n
    for transition in machine.transitions:
        u = index_of[transition.src]
        v = index_of[transition.dst]
        if u == v:
            self_loops[u] += 1
            continue
        cu, cv = comp_of[u], comp_of[v]
        if cu != cv:
            succs[cu].add(cv)
            preds[cv].add(cu)

    comp_key = [min(component) for component in components]
    indeg = [len(p) for p in preds]
    layer = [0] * len(components)
    heap = [(comp_key[c], c) for c in range(len(components)) if indeg[c] == 0]
    heapq.heapify(heap)
    while heap:
        _, c = heapq.heappop(heap)
        for d in succs[c]:
            if layer[c] + 1 > layer[d]:
                layer[d] = layer[c] + 1
            indeg[d] -= 1
            if indeg[d] == 0:
                heapq.heappush(heap, (comp_key[d], d))

    layers: dict[int, list[int]] = {}
    for c in range(len(components)):
        layers.setdefault(layer[c], []).append(c)
    for comp_ids in layers.values():
        comp_ids.sort(key=lambda c: comp_key[c])

    node_w = [_text_width(state) for state in machine.states]
    max_w = max(node_w, default=48)

    comp_members = [sorted(component) for component in components]
    comp_height = [
        len(members) * (_NODE_H + _NODE_GAP_Y) - _NODE_GAP_Y
        for members in comp_members
    ]
    layer_height = {}
    for lay, comp_ids in layers.items():
        total = sum(comp_height[c] for c in comp_ids)
        total += _COMP_GAP_Y * (len(comp_ids) - 1)
        layer_height[lay] = total
    max_layer_h = max(layer_height.values(), default=0)

    max_self_loop = max(self_loops, default=0)
    margin_top = max(70, 34 + 20 * max(max_self_loop - 1, 0) + 40)

    nodes: list[dict] = [{} for _ in range(n)]
    for lay, comp_ids in layers.items():
        x_center = _MARGIN_X + lay * (max_w + _LAYER_GAP_X) + max_w / 2
        y = margin_top + (max_layer_h - layer_height[lay]) / 2
        for c in comp_ids:
            for member in comp_members[c]:
                nodes[member] = {
                    "x": round(x_center),
                    "y": round(y + _NODE_H / 2),
                    "w": node_w[member],
                    "h": _NODE_H,
                }
                y += _NODE_H + _NODE_GAP_Y
            y += _COMP_GAP_Y - _NODE_GAP_Y

    max_layer = max(layers, default=0)
    width = _MARGIN_X * 2 + max_layer * (max_w + _LAYER_GAP_X) + max_w
    height = margin_top + max_layer_h + _MARGIN_BOTTOM
    return {"nodes": nodes, "width": round(width), "height": round(height)}


def _machine_payload(analysis: Analysis) -> dict:
    machine = analysis.machine
    index_of = {state: i for i, state in enumerate(machine.states)}
    conflict_keys = {(src, cond) for src, cond, _ in analysis.conflicts}
    edges = [
        {
            "u": index_of[t.src],
            "v": index_of[t.dst],
            "c": t.cond,
            "k": 1 if (index_of[t.src], t.cond) in conflict_keys else 0,
        }
        for t in machine.transitions
    ]
    return {
        "name": machine.name,
        "states": machine.states,
        "reachable": analysis.reachable,
        "initials": [index_of[s] for s in machine.initials],
        "terminals": analysis.terminals,
        "traps": analysis.traps,
        "edges": edges,
        "problems": analysis.problems,
        "layout": compute_layout(analysis),
    }


def build_html(analyses: list[Analysis]) -> str:
    payload = {"machines": [_machine_payload(a) for a in analyses]}
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c")
    return HTML_TEMPLATE.replace("__DATA__", data)


def build_json(analyses: list[Analysis]) -> str:
    payload = {
        "machines": [
            {
                "name": a.machine.name,
                "states": a.machine.states,
                "reachable": a.reachable,
                "problems": a.problems,
            }
            for a in analyses
        ]
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_outputs(analyses: list[Analysis], out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for analysis in analyses:
        name = analysis.machine.name
        (out / f"{name}.reachability.txt").write_text(
            reachability_text(analysis), encoding="utf-8", newline=""
        )
        (out / f"{name}.problems.txt").write_text(
            problems_text(analysis), encoding="utf-8", newline=""
        )
    (out / "report.json").write_text(build_json(analyses), encoding="utf-8", newline="")
    (out / "report.html").write_text(build_html(analyses), encoding="utf-8", newline="")
