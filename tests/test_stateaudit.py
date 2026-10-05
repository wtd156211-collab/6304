"""stateaudit 的 unittest 测试套件。"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import time
import unittest
from pathlib import Path

from stateaudit.__main__ import main
from stateaudit.analysis import analyze
from stateaudit.model import Row, build_machine

ROOT = Path(__file__).resolve().parents[1]
MACHINES = ROOT / "samples" / "machines"
EXPECTED = ROOT / "samples" / "expected"


def run_cli(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(list(args))
    return rc, out.getvalue(), err.getvalue()


def make_machine(initials, rows):
    """rows: [(当前, 条件, 目标), ...]，行号从 2 起（模拟表头后）。"""
    row_objs = [Row(i + 2, u, c, v) for i, (u, c, v) in enumerate(rows)]
    return build_machine("t", list(initials), row_objs)


def problems_of(initials, rows):
    return analyze(make_machine(initials, rows)).problems


class SamplesAcceptanceTest(unittest.TestCase):
    """验收口径 1-3：样机逐字节比对、report.json 一致、stdout 六行。"""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        cls.rc, cls.stdout, cls.stderr = run_cli(
            "--machines", str(MACHINES), "--out", str(cls.out)
        )

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_exit_code_zero(self):
        self.assertEqual(self.rc, 0, self.stderr)

    def test_stdout_one_line_per_machine(self):
        lines = self.stdout.splitlines()
        self.assertEqual(len(lines), 6)
        names = [line.split("\t")[0] for line in lines]
        self.assertEqual(names, sorted(names))
        for line in lines:
            _, rest = line.split("\t", 1)
            self.assertRegex(rest, r"^状态=\d+\t可达=\d+\t问题=\d+$")

    def test_text_files_match_expected_byte_for_byte(self):
        for expected in sorted(EXPECTED.glob("*.txt")):
            actual = self.out / expected.name
            self.assertTrue(actual.exists(), expected.name)
            self.assertEqual(actual.read_bytes(), expected.read_bytes(), expected.name)

    def test_report_json_consistent_with_text_files(self):
        report = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [m["name"] for m in report["machines"]],
            sorted(m["name"] for m in report["machines"]),
        )
        for m in report["machines"]:
            reach_lines = (self.out / f"{m['name']}.reachability.txt").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(m["states"]), len(m["reachable"]))
            for line, state, ok in zip(reach_lines, m["states"], m["reachable"]):
                self.assertEqual(line, f"{state}\t{'可达' if ok else '不可达'}")
            prob_lines = (self.out / f"{m['name']}.problems.txt").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(m["problems"], prob_lines)

    def test_report_html_self_contained(self):
        html = (self.out / "report.html").read_text(encoding="utf-8")
        self.assertIn('<script type="module">', html)
        # 不引用任何外部资源（SVG 命名空间字符串除外，它不是网络请求）
        for external in ("<link", "src=", "@import", "fetch(", "import(",
                         'href="http', "url(http"):
            self.assertNotIn(external, html)
        self.assertNotIn("https://", html)
        self.assertEqual(html.count("http://"), html.count("http://www.w3.org/2000/svg"))
        report = json.loads((self.out / "report.json").read_text(encoding="utf-8"))
        for m in report["machines"]:
            self.assertIn(json.dumps(m["name"], ensure_ascii=False), html)
            for p in m["problems"]:
                self.assertIn(json.dumps(p, ensure_ascii=False), html)


class DeterminismTest(unittest.TestCase):
    """同一份迁移表跑两遍，输出逐字节一致。"""

    def test_two_runs_identical(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            self.assertEqual(run_cli("--machines", str(MACHINES), "--out", d1)[0], 0)
            self.assertEqual(run_cli("--machines", str(MACHINES), "--out", d2)[0], 0)
            for p in sorted(Path(d1).iterdir()):
                self.assertEqual(
                    p.read_bytes(), (Path(d2) / p.name).read_bytes(), p.name
                )


class SemanticsTest(unittest.TestCase):
    """口径级单元测试：TRAP / TERMINAL / CONFLICT / UNREACHABLE 的边界。"""

    def test_single_state_self_loop_is_trap(self):
        problems = problems_of(["a"], [("a", "tick", "a")])
        self.assertEqual(problems, ["TRAP a"])

    def test_self_loop_with_exit_is_not_trap(self):
        problems = problems_of(["a"], [("a", "tick", "a"), ("a", "done", "b")])
        self.assertEqual(problems, ["TERMINAL b"])

    def test_unreachable_cycle_is_not_trap(self):
        problems = problems_of(["a"], [("a", "go", "b"), ("x", "go", "y"), ("y", "go", "x")])
        self.assertEqual(problems, ["UNREACHABLE x", "UNREACHABLE y", "TERMINAL b"])

    def test_unreachable_dead_end_is_not_terminal(self):
        problems = problems_of(["a"], [("a", "go", "a"), ("x", "go", "y")])
        self.assertIn("UNREACHABLE y", problems)
        self.assertNotIn("TERMINAL y", problems)

    def test_duplicate_rows_are_not_conflict(self):
        problems = problems_of(["a"], [("a", "go", "b"), ("a", "go", "b")])
        self.assertEqual(problems, ["TERMINAL b"])

    def test_conflict_targets_deduped_first_occurrence(self):
        problems = problems_of(
            ["a"],
            [("a", "go", "b"), ("a", "go", "c"), ("a", "go", "b")],
        )
        self.assertEqual(problems, ["CONFLICT a go -> b,c", "TERMINAL b", "TERMINAL c"])

    def test_conflict_on_unreachable_state_still_reported(self):
        problems = problems_of(["a"], [("x", "go", "b"), ("x", "go", "c")])
        self.assertIn("CONFLICT x go -> b,c", problems)

    def test_init_only_state_is_reachable_terminal(self):
        a = analyze(make_machine(["solo"], []))
        self.assertEqual(a.machine.states, ["solo"])
        self.assertEqual(a.reachable, [True])
        self.assertEqual(a.problems, ["TERMINAL solo"])

    def test_canonical_order_init_first_then_rows(self):
        m = make_machine(["z"], [("b", "go", "c"), ("a", "go", "b")])
        self.assertEqual(m.states, ["z", "b", "c", "a"])

    def test_trap_block_order_by_earliest_state(self):
        rows = [
            ("s", "go", "a1"), ("a1", "go", "a2"), ("a2", "go", "a1"),
            ("s", "go2", "b1"), ("b1", "go", "b2"), ("b2", "go", "b1"),
        ]
        problems = problems_of(["s"], rows)
        self.assertEqual(problems, ["TRAP a1,a2", "TRAP b1,b2"])

    def test_problem_type_order(self):
        rows = [
            ("s", "go", "t"), ("t", "tick", "t"),
            ("s", "c", "u"), ("s", "c", "v"),
            ("w", "go", "w"),
        ]
        problems = problems_of(["s"], rows)
        self.assertEqual(
            problems,
            ["UNREACHABLE w", "TRAP t", "CONFLICT s c -> u,v", "TERMINAL u", "TERMINAL v"],
        )


class ValidationTest(unittest.TestCase):
    """校验失败：机名与行号进 stderr，退出码 2，不产出文件。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "machines"
        self.dir.mkdir()
        self.out = Path(self._tmp.name) / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, tsv=None, init=None):
        if tsv is not None:
            (self.dir / f"{name}.tsv").write_bytes(tsv)
        if init is not None:
            (self.dir / f"{name}.init").write_bytes(init)

    def assert_invalid(self, expect_name, expect_line=None):
        rc, _, err = run_cli("--machines", str(self.dir), "--out", str(self.out))
        self.assertEqual(rc, 2)
        self.assertIn(expect_name, err)
        if expect_line is not None:
            self.assertIn(f"{expect_name}:{expect_line}", err)
        self.assertFalse(self.out.exists(), "校验失败不得产出任何文件")

    HEADER = "当前状态\t条件\t目标状态\n"

    def test_wrong_column_count(self):
        self.write("m", (self.HEADER + "a\tgo\n").encode(), b"a\n")
        self.assert_invalid("m", 2)

    def test_empty_field(self):
        self.write("m", (self.HEADER + "a\t\tb\n").encode(), b"a\n")
        self.assert_invalid("m", 2)

    def test_whitespace_in_name(self):
        self.write("m", (self.HEADER + "a b\tgo\tc\n").encode(), b"a\n")
        self.assert_invalid("m", 2)

    def test_comma_in_name(self):
        self.write("m", (self.HEADER + "a,b\tgo\tc\n").encode(), b"a\n")
        self.assert_invalid("m", 2)

    def test_arrow_as_name(self):
        self.write("m", (self.HEADER + "->\tgo\tc\n").encode(), b"a\n")
        self.assert_invalid("m", 2)

    def test_missing_header(self):
        self.write("m", "x\ty\tz\na\tgo\tb\n".encode(), b"a\n")
        self.assert_invalid("m", 1)

    def test_missing_init_pair(self):
        self.write("m", (self.HEADER + "a\tgo\tb\n").encode(), None)
        self.assert_invalid("m")

    def test_missing_tsv_pair(self):
        self.write("m", None, b"a\n")
        self.assert_invalid("m")

    def test_empty_directory(self):
        rc, _, err = run_cli("--machines", str(self.dir), "--out", str(self.out))
        self.assertEqual(rc, 2)
        self.assertIn(".tsv", err)

    def test_empty_init(self):
        self.write("m", (self.HEADER + "a\tgo\tb\n").encode(), b"\n")
        self.assert_invalid("m")

    def test_init_state_with_whitespace(self):
        self.write("m", (self.HEADER + "a\tgo\tb\n").encode(), b"a b\n")
        self.assert_invalid("m", 1)

    def test_bom_crlf_comments_and_blank_lines_ok(self):
        tsv = (
            "\ufeff# 注释\n"
            "\r\n"
            "   # 前导空格注释\n"
            "当前状态\t条件\t目标状态\r\n"
            "a\tgo\tb\r\n"
        )
        self.write("m", tsv.encode("utf-8"), b"a\r\n")
        rc, stdout, _ = run_cli("--machines", str(self.dir), "--out", str(self.out))
        self.assertEqual(rc, 0)
        self.assertIn("m\t状态=2\t可达=2\t问题=1", stdout)

    def test_duplicate_init_states_deduped(self):
        self.write("m", (self.HEADER + "a\tgo\tb\n").encode(), b"a\na\nb\n")
        rc, stdout, _ = run_cli("--machines", str(self.dir), "--out", str(self.out))
        self.assertEqual(rc, 0)
        states = (self.out / "m.reachability.txt").read_text(encoding="utf-8")
        self.assertEqual(states.splitlines(), ["a\t可达", "b\t可达"])


class ScaleTest(unittest.TestCase):
    """性能口径：20,000 状态 / 100,000 行迁移，全流程 ≤ 5 秒，长链不崩。"""

    def test_long_chain_no_recursion_error(self):
        n = 20000
        rows = [(f"s{i}", "go", f"s{i+1}") for i in range(n - 1)]
        a = analyze(make_machine(["s0"], rows))
        self.assertTrue(all(a.reachable))
        self.assertEqual(a.terminals, [f"s{n-1}"])

    def test_large_machine_within_budget(self):
        n_states, n_rows = 20000, 100000
        with tempfile.TemporaryDirectory() as tmp:
            mdir = Path(tmp) / "machines"
            mdir.mkdir()
            lines = ["当前状态\t条件\t目标状态"]
            lines += [f"s{i}\tgo\ts{i+1}" for i in range(n_states - 1)]
            u, v = 0, 1  # 确定性伪随机填充，不引入 random
            while len(lines) - 1 < n_rows:
                u = (u * 1103515245 + 12345) % 2000
                v = (v * 1103515245 + 12345) % n_states
                lines.append(f"s{u}\te{u % 50}\ts{v}")
            (mdir / "big.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (mdir / "big.init").write_text("s0\n", encoding="utf-8")
            start = time.perf_counter()
            rc, stdout, _ = run_cli("--machines", str(mdir), "--out", str(Path(tmp) / "out"))
            elapsed = time.perf_counter() - start
            self.assertEqual(rc, 0)
            self.assertIn("big\t状态=20000\t可达=20000\t", stdout)
            self.assertLess(elapsed, 5.0, f"全流程 {elapsed:.2f}s 超出 5s 预算")


if __name__ == "__main__":
    unittest.main()
