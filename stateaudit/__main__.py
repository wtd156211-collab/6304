"""命令行入口：python -m stateaudit [--machines DIR] [--out DIR]"""

from __future__ import annotations

import argparse
import sys

from .analysis import analyze
from .model import MachineErrors, load_machines
from .report import write_outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="stateaudit", description="状态机迁移表可达性与死锁分析"
    )
    parser.add_argument("--machines", default="samples/machines", help="迁移表目录")
    parser.add_argument("--out", default="var", help="输出目录")
    args = parser.parse_args(argv)

    try:
        machines = load_machines(args.machines)
    except MachineErrors as exc:
        for err in exc.errors:
            print(err, file=sys.stderr)
        return 2

    results = [analyze(m) for m in machines]
    write_outputs(results, args.out)
    for a in results:
        m = a.machine
        print(
            f"{m.name}\t状态={len(m.states)}\t"
            f"可达={sum(a.reachable)}\t问题={len(a.problems)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
