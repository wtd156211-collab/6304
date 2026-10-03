"""可达性、强连通块与问题清单分析。

口径（与 README 第二节一致）：
- 带条件的迁移一律视为可发生；自环计入出度但不扩张可达集。
- TRAP：可达汇块，且 |C| >= 2 或块内有自环。
- TERMINAL：可达且出度为 0。
- CONFLICT：同一 (状态, 条件) 去重后有 >= 2 个目标。
- UNREACHABLE 覆盖全部不可达状态，不与 TRAP / TERMINAL 重复。

全部遍历为迭代实现（BFS + 迭代 Tarjan），20,000 长链不触发递归。
"""
from __future__ import annotations

from dataclasses import dataclass

from .loader import Machine


@dataclass
class Analysis:
    machine: Machine
    reachable: list[bool]  # 与 machine.states 同序
    unreachable: list[str]  # 规范顺序
    traps: list[list[int]]  # 死循环块：状态下标，块内规范顺序，块间按最早状态排
    conflicts: list[tuple[int, str, list[str]]]  # (源状态下标, 条件, 去重目标名)
    terminals: list[int]  # 状态下标，规范顺序
    components: list[list[int]]  # 全部 SCC（状态下标）
    comp_of: list[int]  # 状态下标 -> SCC 编号
    problems: list[str]  # 已排版的问题行，顺序敏感


def _tarjan_scc(adj: list[list[int]]) -> list[list[int]]:
    """迭代版 Tarjan，返回 SCC 列表（每个 SCC 是状态下标列表）。"""
    n = len(adj)
    index_of = [-1] * n
    lowlink = [0] * n
    on_stack = [False] * n
    stack: list[int] = []
    counter = 0
    components: list[list[int]] = []
    for root in range(n):
        if index_of[root] != -1:
            continue
        work: list[tuple[int, int]] = [(root, 0)]
        while work:
            node, child_i = work[-1]
            if child_i == 0:
                index_of[node] = lowlink[node] = counter
                counter += 1
                stack.append(node)
                on_stack[node] = True
            descended = False
            i = child_i
            while i < len(adj[node]):
                nxt = adj[node][i]
                if index_of[nxt] == -1:
                    work[-1] = (node, i + 1)
                    work.append((nxt, 0))
                    descended = True
                    break
                if on_stack[nxt] and index_of[nxt] < lowlink[node]:
                    lowlink[node] = index_of[nxt]
                i += 1
            if descended:
                continue
            if lowlink[node] == index_of[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack[member] = False
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
            work.pop()
            if work:
                parent = work[-1][0]
                if lowlink[node] < lowlink[parent]:
                    lowlink[parent] = lowlink[node]
    return components


def analyze(machine: Machine) -> Analysis:
    states = machine.states
    n = len(states)
    index_of = {state: i for i, state in enumerate(states)}

    adj: list[list[int]] = [[] for _ in range(n)]
    outdeg = [0] * n
    has_self_loop = [False] * n
    for transition in machine.transitions:
        u = index_of[transition.src]
        v = index_of[transition.dst]
        adj[u].append(v)
        outdeg[u] += 1
        if u == v:
            has_self_loop[u] = True

    reachable = [False] * n
    queue = [index_of[state] for state in machine.initials]
    for i in queue:
        reachable[i] = True
    head = 0
    while head < len(queue):
        u = queue[head]
        head += 1
        for v in adj[u]:
            if not reachable[v]:
                reachable[v] = True
                queue.append(v)

    components = _tarjan_scc(adj)
    comp_of = [0] * n
    for comp_id, component in enumerate(components):
        for member in component:
            comp_of[member] = comp_id

    is_sink = [True] * len(components)
    for u in range(n):
        cu = comp_of[u]
        for v in adj[u]:
            if comp_of[v] != cu:
                is_sink[cu] = False
                break

    traps: list[list[int]] = []
    for component in components:
        comp_id = comp_of[component[0]]
        if not is_sink[comp_id]:
            continue
        if not any(reachable[member] for member in component):
            continue
        if len(component) >= 2 or any(has_self_loop[m] for m in component):
            traps.append(sorted(component))
    traps.sort(key=lambda component: component[0])

    unreachable = [states[i] for i in range(n) if not reachable[i]]
    terminals = [i for i in range(n) if reachable[i] and outdeg[i] == 0]

    # 冲突：按 (源状态, 条件) 聚合，目标去重且保留首次出现顺序。
    per_src: dict[int, dict[str, list]] = {}
    for row_order, transition in enumerate(machine.transitions):
        u = index_of[transition.src]
        per_cond = per_src.setdefault(u, {})
        entry = per_cond.get(transition.cond)
        if entry is None:
            per_cond[transition.cond] = [row_order, [transition.dst]]
        elif transition.dst not in entry[1]:
            entry[1].append(transition.dst)
    conflicts: list[tuple[int, str, list[str]]] = []
    for u in sorted(per_src):
        entries = sorted(per_src[u].items(), key=lambda item: item[1][0])
        for cond, (_, targets) in entries:
            if len(targets) >= 2:
                conflicts.append((u, cond, targets))

    problems: list[str] = []
    problems.extend(f"UNREACHABLE {state}" for state in unreachable)
    for component in traps:
        problems.append("TRAP " + ",".join(states[i] for i in component))
    for u, cond, targets in conflicts:
        problems.append(f"CONFLICT {states[u]} {cond} -> {','.join(targets)}")
    problems.extend(f"TERMINAL {states[i]}" for i in terminals)

    return Analysis(
        machine=machine,
        reachable=reachable,
        unreachable=unreachable,
        traps=traps,
        conflicts=conflicts,
        terminals=terminals,
        components=components,
        comp_of=comp_of,
        problems=problems,
    )
