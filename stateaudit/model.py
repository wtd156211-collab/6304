"""迁移表与初始状态集合的读取、校验与规范顺序。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HEADER = ("当前状态", "条件", "目标状态")
_NAME_RE = re.compile(r"^[^\s,]+$")


class MachineError(Exception):
    """单台机器的校验错误（机名 + 行号）。"""

    def __init__(self, machine: str, line: int | None, message: str) -> None:
        self.machine = machine
        self.line = line
        self.message = message
        where = f"{machine}:{line}" if line is not None else machine
        super().__init__(f"{where}: {message}")


class MachineErrors(Exception):
    """一次加载中收集到的全部校验错误。"""

    def __init__(self, errors: list[MachineError]) -> None:
        self.errors = errors
        super().__init__("; ".join(str(e) for e in errors))


@dataclass(frozen=True)
class Row:
    line: int
    current: str
    condition: str
    target: str


@dataclass
class Machine:
    name: str
    initials: list[str]
    rows: list[Row]
    states: list[str]  # 规范顺序
    index: dict[str, int]  # 状态名 -> 规范顺序下标


def _check_token(machine: str, line: int | None, token: str, what: str) -> None:
    if not token:
        raise MachineError(machine, line, f"{what}trim 后为空")
    if not _NAME_RE.match(token):
        raise MachineError(machine, line, f"{what}含空白字符或半角逗号: {token!r}")
    if token == "->":
        raise MachineError(machine, line, f"{what}不得为 ->")


def _read_text(path: Path, name: str) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MachineError(name, None, f"不是合法 UTF-8: {exc}") from exc


def _parse_tsv(path: Path, name: str) -> list[Row]:
    rows: list[Row] = []
    header_seen = False
    for lineno, raw in enumerate(_read_text(path, name).splitlines(), 1):
        if not raw.strip():
            continue
        if raw.lstrip().startswith("#"):
            continue
        cols = [col.strip() for col in raw.split("\t")]
        if not header_seen:
            if tuple(cols) != HEADER:
                raise MachineError(
                    name, lineno, "第一个有效行必须是表头 当前状态\\t条件\\t目标状态"
                )
            header_seen = True
            continue
        if len(cols) != 3:
            raise MachineError(name, lineno, f"数据行必须正好 3 列，实际 {len(cols)} 列")
        for col, what in zip(cols, HEADER):
            _check_token(name, lineno, col, what)
        rows.append(Row(lineno, cols[0], cols[1], cols[2]))
    if not header_seen:
        raise MachineError(name, None, "迁移表为空或缺少表头")
    return rows


def _parse_init(path: Path, name: str) -> list[str]:
    states: list[str] = []
    seen: set[str] = set()
    for lineno, raw in enumerate(_read_text(path, name).splitlines(), 1):
        token = raw.strip()
        if not token:
            continue
        _check_token(name, lineno, token, "初始状态")
        if token not in seen:
            seen.add(token)
            states.append(token)
    if not states:
        raise MachineError(name, None, "初始状态集合为空，至少 1 个")
    return states


def build_machine(name: str, initials: list[str], rows: list[Row]) -> Machine:
    """按规范顺序建立状态表：先 .init 行序，再迁移行序（每行先当前后目标）。"""
    states: list[str] = []
    index: dict[str, int] = {}

    def add(state: str) -> None:
        if state not in index:
            index[state] = len(states)
            states.append(state)

    for state in initials:
        add(state)
    for row in rows:
        add(row.current)
        add(row.target)
    return Machine(name, list(initials), rows, states, index)


def load_machines(directory: str | Path) -> list[Machine]:
    """读取目录下全部状态机；任何校验失败汇总为 MachineErrors。"""
    directory = Path(directory)
    if not directory.is_dir():
        raise MachineErrors([MachineError(str(directory), None, "目录不存在")])
    tsvs = {p.stem: p for p in directory.glob("*.tsv")}
    inits = {p.stem: p for p in directory.glob("*.init")}
    if not tsvs:
        raise MachineErrors([MachineError(str(directory), None, "目录中没有任何 .tsv 迁移表")])
    machines: list[Machine] = []
    errors: list[MachineError] = []
    for name in sorted(set(tsvs) | set(inits)):
        try:
            if name not in tsvs:
                raise MachineError(name, None, "缺少配对的 .tsv 迁移表")
            if name not in inits:
                raise MachineError(name, None, "缺少配对的 .init 初始状态文件")
            rows = _parse_tsv(tsvs[name], name)
            initials = _parse_init(inits[name], name)
        except MachineError as exc:
            errors.append(exc)
            continue
        machines.append(build_machine(name, initials, rows))
    if errors:
        raise MachineErrors(errors)
    return machines
