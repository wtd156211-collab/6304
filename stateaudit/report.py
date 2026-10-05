"""输出：逐行文本文件、report.json、单文件 report.html。"""

from __future__ import annotations

import json
from pathlib import Path

from .analysis import Analysis
from .web import render_html


def _write(path: Path, text: str) -> None:
    # UTF-8 无 BOM、LF、显式 newline 杜绝平台换行翻译。
    path.write_text(text, encoding="utf-8", newline="")


def write_outputs(results: list[Analysis], out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    json_machines = []
    html_machines = []
    for a in results:
        m = a.machine
        reach_text = "".join(
            f"{s}\t{'可达' if ok else '不可达'}\n" for s, ok in zip(m.states, a.reachable)
        )
        _write(out / f"{m.name}.reachability.txt", reach_text)
        _write(out / f"{m.name}.problems.txt", "".join(f"{p}\n" for p in a.problems))

        json_machines.append(
            {
                "name": m.name,
                "states": m.states,
                "reachable": a.reachable,
                "problems": a.problems,
            }
        )
        html_machines.append(
            {
                "name": m.name,
                "states": m.states,
                "reachable": a.reachable,
                "problems": a.problems,
                "initial": [m.index[s] for s in m.initials],
                "edges": a.edges,
                "traps": [[m.index[s] for s in block] for block in a.traps],
            }
        )

    report = {"machines": json_machines}
    _write(out / "report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _write(out / "report.html", render_html({"machines": html_machines}))
