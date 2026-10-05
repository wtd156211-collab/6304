"""可达性、强连通块与问题清单。全部 O(V+E)，迭代实现，不触递归。"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Machine


@dataclass
class Analysis:
    machine: Machine
    reachable: list[bool]  # 与 states 同序
    unreachable: list[str]  # 规范顺序
    traps: list[list[str]]  # 块内规范顺序；块间按块内最早状态
    trap_member: set[str]
    conflicts: list[tuple[str, str, list[str]]]  # (状态, 条件, 目标列表)
    conflict_keys: set[tuple[str, str]]
    terminals: list[str]  # 规范顺序
    problems: list[str]
    edges: list[tuple[int, str, int, bool]]  # (源下标, 条件, 目标下标, 是否冲突)


def _reach(adj: list[list[int]], seeds: list[int], n: int) -> list[bool]:
    seen = [False] * n
    stack = []
    for s in seeds:
        if not seen[s]:
            seen[s] = True
            stack.append(s)
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if not seen[v]:
                seen[v] = True
                stack.append(v)
    return seen


def _scc(adj: list[list[int]], n: int) -> list[list[int]]:
    """迭代版 Tarjan，返回强连通块列表（每块为状态下标列表）。"""
    index_of = [-1] * n
    low = [0] * n
    on_stack = [False] * n
    stack: list[int] = []
    comps: list[list[int]] = []
    counter = 0
    for root in range(n):
        if index_of[root] != -1:
            continue
        work = [[root, 0]]
        while work:
            frame = work[-1]
            v, pi = frame
            if pi == 0:
                index_of[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on_stack[v] = True
            descended = False
            i = pi
            while i < len(adj[v]):
                w = adj[v][i]
                if index_of[w] == -1:
                    frame[1] = i + 1
                    work.append([w, 0])
                    descended = True
                    break
                if on_stack[w] and index_of[w] < low[v]:
                    low[v] = index_of[w]
                i += 1
            if descended:
                continue
            if low[v] == index_of[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == v:
                        break
                comps.append(comp)
            work.pop()
            if work:
                parent = work[-1][0]
                if low[v] < low[parent]:
                    low[parent] = low[v]
    return comps


def analyze(machine: Machine) -> Analysis:
    n = len(machine.states)
    index = machine.index
    adj: list[list[int]] = [[] for _ in range(n)]
    outdeg = [0] * n
    for row in machine.rows:
        u = index[row.current]
        adj[u].append(index[row.target])
        outdeg[u] += 1

    reachable = _reach(adj, [index[s] for s in machine.initials], n)

    comps = _scc(adj, n)
    comp_id = [0] * n
    for ci, comp in enumerate(comps):
        for v in comp:
            comp_id[v] = ci
    sink = [True] * len(comps)
    self_loop = [False] * len(comps)
    for u in range(n):
        for v in adj[u]:
            if comp_id[u] != comp_id[v]:
                sink[comp_id[u]] = False
            elif u == v:
                self_loop[comp_id[u]] = True

    trap_blocks = []
    for ci, comp in enumerate(comps):
        if not sink[ci] or not reachable[comp[0]]:
            continue
        if len(comp) >= 2 or self_loop[ci]:
            trap_blocks.append(sorted(comp))
    trap_blocks.sort(key=lambda block: block[0])
    traps = [[machine.states[i] for i in block] for block in trap_blocks]
    trap_member = {s for block in traps for s in block}

    groups: dict[tuple[int, str], list] = {}
    for pos, row in enumerate(machine.rows):
        u = index[row.current]
        key = (u, row.condition)
        group = groups.get(key)
        if group is None:
            groups[key] = [pos, [row.target], {row.target}]
        elif row.target not in group[2]:
            group[1].append(row.target)
            group[2].add(row.target)
    conflict_rows = sorted(
        ((u, cond, g[0], g[1]) for (u, cond), g in groups.items() if len(g[1]) >= 2),
        key=lambda item: (item[0], item[2]),
    )
    conflicts = [(machine.states[u], cond, targets) for u, cond, _, targets in conflict_rows]
    conflict_keys = {(state, cond) for state, cond, _ in conflicts}

    states = machine.states
    unreachable = [states[i] for i in range(n) if not reachable[i]]
    terminals = [states[i] for i in range(n) if reachable[i] and outdeg[i] == 0]

    problems = [f"UNREACHABLE {s}" for s in unreachable]
    problems += ["TRAP " + ",".join(block) for block in traps]
    problems += [f"CONFLICT {u} {c} -> {','.join(ts)}" for u, c, ts in conflicts]
    problems += [f"TERMINAL {s}" for s in terminals]

    edges = [
        (index[r.current], r.condition, index[r.target], (r.current, r.condition) in conflict_keys)
        for r in machine.rows
    ]
    return Analysis(
        machine=machine,
        reachable=reachable,
        unreachable=unreachable,
        traps=traps,
        trap_member=trap_member,
        conflicts=conflicts,
        conflict_keys=conflict_keys,
        terminals=terminals,
        problems=problems,
        edges=edges,
    )
