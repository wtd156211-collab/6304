"""stateaudit 的 unittest 测试套件。

运行：python -m unittest discover -s tests -v
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from stateaudit import SpecError, analyze, load_machines
from stateaudit.__main__ import main
from stateaudit.loader import Machine, Transition
from stateaudit.report import (
    build_html,
    build_json,
    problems_text,
    reachability_text,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"
HEADER = "当前状态\t条件\t目标状态\n"


def make_machine(name, initials, rows):
    """rows: (src, cond, dst) 三元组列表，直接构造 Machine（绕过文件解析）。"""
    transitions = [
        Transition(src, cond, dst, i + 2) for i, (src, cond, dst) in enumerate(rows)
    ]
    states = list(initials)
    seen = set(initials)
    for src, _, dst in rows:
        for s in (src, dst):
            if s not in seen:
                seen.add(s)
                states.append(s)
    return Machine(name, states, list(initials), transitions)


def write_machine(directory, name, tsv_text, init_text):
    directory = Path(directory)
    (directory / f"{name}.tsv").write_text(tsv_text, encoding="utf-8")
    (directory / f"{name}.init").write_text(init_text, encoding="utf-8")


class GoldenSamplesTest(unittest.TestCase):
    """六台样例机的输出必须与 samples/expected 逐字节一致。"""

    def test_samples_match_expected(self):
        machines = load_machines(SAMPLES / "machines")
        self.assertEqual(len(machines), 6)
        for machine in machines:
            analysis = analyze(machine)
            expected_reach = (
                SAMPLES / "expected" / f"{machine.name}.reachability.txt"
            ).read_bytes()
            expected_prob = (
                SAMPLES / "expected" / f"{machine.name}.problems.txt"
            ).read_bytes()
            with self.subTest(machine=machine.name, kind="reachability"):
                self.assertEqual(reachability_text(analysis).encode("utf-8"), expected_reach)
            with self.subTest(machine=machine.name, kind="problems"):
                self.assertEqual(problems_text(analysis).encode("utf-8"), expected_prob)


class CliTest(unittest.TestCase):
    def run_cli(self, machines_dir, out_dir):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--machines", str(machines_dir), "--out", str(out_dir)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_end_to_end_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, stderr = self.run_cli(SAMPLES / "machines", tmp)
            self.assertEqual(code, 0, stderr)
            lines = [l for l in stdout.splitlines() if l]
            self.assertEqual(len(lines), 6)
            for line in lines:
                name, *rest = line.split("\t")
                self.assertTrue(all(part.startswith(k) for part, k in
                                    zip(rest, ["状态=", "可达=", "问题="])))
                for kind in ("reachability", "problems"):
                    expected = (SAMPLES / "expected" / f"{name}.{kind}.txt").read_bytes()
                    actual = (Path(tmp) / f"{name}.{kind}.txt").read_bytes()
                    self.assertEqual(actual, expected, f"{name}.{kind}.txt")

    def test_report_json_consistent_with_text_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = self.run_cli(SAMPLES / "machines", tmp)
            self.assertEqual(code, 0)
            report = json.loads((Path(tmp) / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(
                [m["name"] for m in report["machines"]],
                sorted(m["name"] for m in report["machines"]),
            )
            for entry in report["machines"]:
                reach_lines = (Path(tmp) / f"{entry['name']}.reachability.txt") \
                    .read_text(encoding="utf-8").splitlines()
                prob_lines = (Path(tmp) / f"{entry['name']}.problems.txt") \
                    .read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(entry["states"]), len(reach_lines))
                self.assertEqual(len(entry["states"]), len(entry["reachable"]))
                for state, flag, line in zip(
                    entry["states"], entry["reachable"], reach_lines
                ):
                    self.assertEqual(line, f"{state}\t{'可达' if flag else '不可达'}")
                self.assertEqual(entry["problems"], prob_lines)

    def test_report_html_self_contained(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _, _ = self.run_cli(SAMPLES / "machines", tmp)
            self.assertEqual(code, 0)
            html = (Path(tmp) / "report.html").read_text(encoding="utf-8")
            self.assertIn('<script type="module">', html)
            self.assertNotIn("http://", html)
            self.assertNotIn("https://", html)
            self.assertNotIn("<link", html)
            self.assertNotIn("<img", html)
            for name in ("conflict", "order_flow", "retry_cycle",
                         "selfloops", "stuck_zone", "unreachable"):
                self.assertIn(name, html)

    def test_determinism_two_runs_identical(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            self.assertEqual(self.run_cli(SAMPLES / "machines", d1)[0], 0)
            self.assertEqual(self.run_cli(SAMPLES / "machines", d2)[0], 0)
            files1 = sorted(p.name for p in Path(d1).iterdir())
            self.assertEqual(files1, sorted(p.name for p in Path(d2).iterdir()))
            for name in files1:
                self.assertEqual(
                    (Path(d1) / name).read_bytes(),
                    (Path(d2) / name).read_bytes(),
                    name,
                )

    def test_invalid_input_exit_2_and_no_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            machines_dir = Path(tmp) / "machines"
            machines_dir.mkdir()
            write_machine(machines_dir, "bad", "不是表头\n", "甲\n")
            out_dir = Path(tmp) / "out"
            code, stdout, stderr = self.run_cli(machines_dir, out_dir)
            self.assertEqual(code, 2)
            self.assertIn("bad", stderr)
            self.assertFalse(out_dir.exists(), "校验失败不得产出任何文件")


class ParserTest(unittest.TestCase):
    def load_one(self, tsv_text, init_text="甲\n", tsv_bytes=None, init_bytes=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        directory = Path(tmp.name)
        if tsv_bytes is not None:
            (directory / "m.tsv").write_bytes(tsv_bytes)
        else:
            (directory / "m.tsv").write_text(tsv_text, encoding="utf-8")
        if init_bytes is not None:
            (directory / "m.init").write_bytes(init_bytes)
        else:
            (directory / "m.init").write_text(init_text, encoding="utf-8")
        return load_machines(directory)

    def test_bom_crlf_comments_and_blank_lines(self):
        tsv = ("\ufeff# 注释\n"
               "   # 前导空格注释\n"
               "\r\n"
               "当前状态\t条件\t目标状态\r\n"
               "甲\t走\t乙\r\n").encode("utf-8")
        init = "\ufeff甲\r\n".encode("utf-8")
        machines = self.load_one(None, tsv_bytes=tsv, init_bytes=init)
        self.assertEqual(machines[0].states, ["甲", "乙"])
        self.assertEqual(len(machines[0].transitions), 1)

    def test_canonical_state_order(self):
        tsv = HEADER + "乙\tc\t丙\n甲\tc\t丁\n"
        init = "戊\n甲\n甲\n"
        machines = self.load_one(tsv, init)
        self.assertEqual(machines[0].states, ["戊", "甲", "乙", "丙", "丁"])
        self.assertEqual(machines[0].initials, ["戊", "甲"])

    def test_init_only_state_allowed(self):
        machines = self.load_one(HEADER + "甲\tc\t乙\n", "甲\n孤岛\n")
        self.assertIn("孤岛", machines[0].states)

    def test_header_must_be_first_effective_line(self):
        with self.assertRaises(SpecError) as ctx:
            self.load_one("甲\tc\t乙\n" + HEADER)
        self.assertEqual(ctx.exception.machine, "m")
        self.assertEqual(ctx.exception.line, 1)

    def test_wrong_column_count(self):
        with self.assertRaises(SpecError) as ctx:
            self.load_one(HEADER + "甲\tc\n")
        self.assertEqual(ctx.exception.line, 2)

    def test_empty_cell_rejected(self):
        with self.assertRaises(SpecError):
            self.load_one(HEADER + "甲\t \t乙\n")

    def test_name_with_whitespace_or_comma_rejected(self):
        with self.assertRaises(SpecError):
            self.load_one(HEADER + "甲 乙\tc\t丙\n")
        with self.assertRaises(SpecError):
            self.load_one(HEADER + "甲\tc,d\t乙\n")

    def test_arrow_name_rejected(self):
        with self.assertRaises(SpecError):
            self.load_one(HEADER + "甲\tc\t->\n")

    def test_init_requires_at_least_one_state(self):
        with self.assertRaises(SpecError):
            self.load_one(HEADER + "甲\tc\t乙\n", "\n\n")

    def test_pairing_and_empty_dir_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            with self.assertRaises(SpecError):
                load_machines(directory)
            (directory / "a.tsv").write_text(HEADER, encoding="utf-8")
            with self.assertRaises(SpecError) as ctx:
                load_machines(directory)
            self.assertEqual(ctx.exception.machine, "a")
            (directory / "a.init").write_text("甲\n", encoding="utf-8")
            (directory / "b.init").write_text("甲\n", encoding="utf-8")
            with self.assertRaises(SpecError) as ctx:
                load_machines(directory)
            self.assertEqual(ctx.exception.machine, "b")

    def test_missing_directory(self):
        with self.assertRaises(SpecError):
            load_machines("/nonexistent/path/xyz")


class AnalysisTest(unittest.TestCase):
    def problems_of(self, machine):
        return analyze(machine).problems

    def test_self_loop_only_state_is_trap_not_terminal(self):
        machine = make_machine("m", ["甲"], [("甲", "c", "乙"), ("乙", "x", "乙")])
        self.assertEqual(self.problems_of(machine), ["TRAP 乙"])

    def test_self_loop_with_exit_is_not_trap(self):
        machine = make_machine(
            "m", ["甲"], [("甲", "c", "乙"), ("乙", "x", "乙"), ("乙", "d", "丙")]
        )
        self.assertEqual(self.problems_of(machine), ["TERMINAL 丙"])

    def test_unreachable_cycle_not_reported_as_trap(self):
        machine = make_machine(
            "m", ["甲"], [("甲", "c", "乙"), ("丙", "x", "丁"), ("丁", "y", "丙")]
        )
        self.assertEqual(
            self.problems_of(machine),
            ["UNREACHABLE 丙", "UNREACHABLE 丁", "TERMINAL 乙"],
        )

    def test_unreachable_zero_outdeg_state_not_terminal(self):
        machine = make_machine("m", ["甲"], [("甲", "c", "乙"), ("丙", "x", "丁")])
        analysis = analyze(machine)
        self.assertEqual(analysis.terminals, [1])
        self.assertEqual(analysis.unreachable, ["丙", "丁"])

    def test_identical_duplicate_rows_not_conflict(self):
        machine = make_machine(
            "m", ["甲"],
            [("甲", "c", "乙"), ("甲", "c", "乙"), ("甲", "c", "乙")],
        )
        self.assertEqual(self.problems_of(machine), ["TERMINAL 乙"])

    def test_conflict_target_dedup_and_first_seen_order(self):
        machine = make_machine(
            "m", ["甲"],
            [("甲", "c", "丙"), ("甲", "c", "乙"), ("甲", "c", "丙"), ("甲", "c", "丁")],
        )
        self.assertEqual(
            self.problems_of(machine),
            ["CONFLICT 甲 c -> 丙,乙,丁", "TERMINAL 丙", "TERMINAL 乙", "TERMINAL 丁"],
        )

    def test_problem_type_order_and_trap_block_order(self):
        machine = make_machine(
            "m", ["甲"],
            [
                ("甲", "c", "乙"), ("乙", "x", "乙"),
                ("甲", "d", "丙"), ("丙", "x", "丁"), ("丁", "x", "丙"),
                ("甲", "e", "戊"),
                ("甲", "f", "庚"), ("甲", "f", "辛"),
                ("壬", "x", "癸"),
            ],
        )
        self.assertEqual(
            self.problems_of(machine),
            [
                "UNREACHABLE 壬",
                "UNREACHABLE 癸",
                "TRAP 乙",
                "TRAP 丙,丁",
                "CONFLICT 甲 f -> 庚,辛",
                "TERMINAL 戊",
                "TERMINAL 庚",
                "TERMINAL 辛",
            ],
        )

    def test_multiple_initials(self):
        machine = make_machine(
            "m", ["甲", "丙"],
            [("甲", "c", "乙"), ("丙", "c", "丁")],
        )
        analysis = analyze(machine)
        self.assertEqual(analysis.reachable, [True, True, True, True])

    def test_long_chain_no_recursion_error(self):
        n = 20000
        rows = [(f"s{i}", "c", f"s{i+1}") for i in range(n - 1)]
        machine = make_machine("m", ["s0"], rows)
        analysis = analyze(machine)
        self.assertTrue(all(analysis.reachable))
        self.assertEqual(analysis.problems, [f"TERMINAL s{n-1}"])


class PerformanceTest(unittest.TestCase):
    def test_large_machine_within_budget(self):
        n_states, n_rows = 20000, 100000
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            lines = [HEADER]
            for i in range(n_states - 1):
                lines.append(f"s{i}\tnext\ts{i+1}\n")
            remaining = n_rows - (n_states - 1)
            for i in range(remaining):
                lines.append(f"s{i % n_states}\tpoll{i % 7}\ts{i % n_states}\n")
            (directory / "big.tsv").write_text("".join(lines), encoding="utf-8")
            (directory / "big.init").write_text("s0\n", encoding="utf-8")
            out_dir = directory / "out"
            start = time.monotonic()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = main(["--machines", str(directory), "--out", str(out_dir)])
            elapsed = time.monotonic() - start
            self.assertEqual(code, 0)
            self.assertLess(elapsed, 5.0, f"全流程耗时 {elapsed:.2f}s 超过 5s 预算")
            self.assertIn("状态=20000", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
