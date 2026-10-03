"""命令行入口：python -m stateaudit [--machines DIR] [--out DIR]"""
from __future__ import annotations

import argparse
import sys

from .analyze import analyze
from .errors import SpecError
from .loader import load_machines
from .report import write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stateaudit", description="状态机可达性与死锁检测"
    )
    parser.add_argument("--machines", default="samples/machines", help="迁移表目录")
    parser.add_argument("--out", default="var", help="输出目录")
    args = parser.parse_args(argv)

    try:
        machines = load_machines(args.machines)
    except SpecError as exc:
        print(exc.format(), file=sys.stderr)
        return 2

    analyses = [analyze(machine) for machine in machines]
    analyses.sort(key=lambda a: a.machine.name)
    write_outputs(analyses, args.out)

    for analysis in analyses:
        states = len(analysis.machine.states)
        reachable = sum(analysis.reachable)
        problems = len(analysis.problems)
        print(f"{analysis.machine.name}\t状态={states}\t可达={reachable}\t问题={problems}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
