"""迁移表 (.tsv) 与初始状态集合 (.init) 的读取和校验。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import SpecError

HEADER = ("当前状态", "条件", "目标状态")
_NAME_RE = re.compile(r"^[^\s,]+$")


@dataclass(frozen=True)
class Transition:
    """一条迁移行；line 是 .tsv 中的物理行号（1 起）。"""

    src: str
    cond: str
    dst: str
    line: int


@dataclass
class Machine:
    """一台状态机：states 为规范顺序（init 行序在前，再按数据行 src/dst 首次出现）。"""

    name: str
    states: list[str]
    initials: list[str]
    transitions: list[Transition]


def _validate_name(value: str, machine: str, line: int, kind: str) -> None:
    if not _NAME_RE.fullmatch(value):
        raise SpecError(machine, line, f"{kind}含空白字符或半角逗号: {value!r}")
    if value == "->":
        raise SpecError(machine, line, f"{kind}不得等于 '->'")


def _effective_lines(path: Path):
    """产出 (物理行号, 去 CRLF 的原始行)；空行与注释行（允许前导空格）跳过。"""
    text = path.read_text(encoding="utf-8-sig")
    for line_no, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        yield line_no, raw


def _parse_tsv(machine: str, path: Path) -> list[Transition]:
    transitions: list[Transition] = []
    header_seen = False
    for line_no, raw in _effective_lines(path):
        cols = [col.strip() for col in raw.split("\t")]
        if not header_seen:
            if tuple(cols) != HEADER:
                raise SpecError(
                    machine, line_no, "第一个有效行必须是表头: 当前状态\\t条件\\t目标状态"
                )
            header_seen = True
            continue
        if len(cols) != 3:
            raise SpecError(
                machine, line_no, f"数据行必须正好 3 列，实际为 {len(cols)} 列"
            )
        src, cond, dst = cols
        if not src or not cond or not dst:
            raise SpecError(machine, line_no, "数据行存在 trim 后为空的列")
        _validate_name(src, machine, line_no, "状态名")
        _validate_name(cond, machine, line_no, "条件名")
        _validate_name(dst, machine, line_no, "状态名")
        transitions.append(Transition(src, cond, dst, line_no))
    if not header_seen:
        raise SpecError(machine, None, "缺少表头行: 当前状态\\t条件\\t目标状态")
    return transitions


def _parse_init(machine: str, path: Path) -> list[str]:
    initials: list[str] = []
    seen: set[str] = set()
    text = path.read_text(encoding="utf-8-sig")
    for line_no, raw in enumerate(text.splitlines(), 1):
        state = raw.strip()
        if not state:
            continue
        _validate_name(state, machine, line_no, "初始状态名")
        if state not in seen:
            seen.add(state)
            initials.append(state)
    if not initials:
        raise SpecError(machine, None, ".init 至少要有 1 个初始状态")
    return initials


def _parse_machine(name: str, tsv_path: Path, init_path: Path) -> Machine:
    initials = _parse_init(name, init_path)
    transitions = _parse_tsv(name, tsv_path)
    states = list(initials)
    seen: set[str] = set(initials)
    for transition in transitions:
        for state in (transition.src, transition.dst):
            if state not in seen:
                seen.add(state)
                states.append(state)
    return Machine(name, states, initials, transitions)


def load_machines(directory: str | Path) -> list[Machine]:
    """读取目录下一一配对的 *.tsv / *.init，按机名 Unicode 码点升序返回。"""
    root = Path(directory)
    if not root.is_dir():
        raise SpecError(None, None, f"迁移表目录不存在: {directory}")
    tsv_paths = {p.stem: p for p in root.glob("*.tsv")}
    init_paths = {p.stem: p for p in root.glob("*.init")}
    if not tsv_paths:
        raise SpecError(None, None, f"目录中没有任何 .tsv 迁移表: {directory}")
    missing_init = sorted(tsv_paths.keys() - init_paths.keys())
    if missing_init:
        raise SpecError(missing_init[0], None, "缺少配对的 .init 文件")
    missing_tsv = sorted(init_paths.keys() - tsv_paths.keys())
    if missing_tsv:
        raise SpecError(missing_tsv[0], None, "缺少配对的 .tsv 文件")
    return [
        _parse_machine(name, tsv_paths[name], init_paths[name])
        for name in sorted(tsv_paths)
    ]
