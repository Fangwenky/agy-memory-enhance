#!/usr/bin/env python3
"""Sanity-check task graders with synthetic perfect / wrong runs (no agy needed)."""
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tasks"))

import t1_midway_constraints as t1  # noqa: E402
import t2_decision_edits as t2  # noqa: E402
import t3_cross_session as t3  # noqa: E402
import t4_two_compactions as t4  # noqa: E402
import t5_numbers_report as t5  # noqa: E402


def run_of(*sessions):
    return {"sessions": [{"conv": None, "responses": list(r)} for r in sessions]}


def check(name, g, quiz, halluc, viol):
    ok = (g["quiz_correct"], g["hallucinated"], len(g["violations"])) == (quiz, halluc, viol)
    print(f"[{'ok' if ok else 'FAIL'}] {name}: quiz {g['quiz_correct']}/{g['quiz_total']} "
          f"halluc {g['hallucinated']} viol {g['violations']}")
    return ok


def main():
    ok = True
    # T1
    ws = tempfile.mkdtemp()
    tr = t1.setup(ws)
    good = (f"Constraints: don't modify src/, no grep/sed, don't write results to a file, reply in English, "
            f"skip m21. m02={tr['m02']['key']} m09={tr['m09']['key']} m16={tr['m16']['owner']} "
            f"m24={tr['m24']['owner']}")
    ok &= check("t1 perfect", t1.grade(ws, tr, run_of(["a", "b", "c", good])), 5, 0, 0)
    bad = "m02=REG_02_000000 m09 unknown. 约束是不要修改文件。"
    ok &= check("t1 wrong", t1.grade(ws, tr, run_of(["a", "b", "c", bad])), 0, 1, 1)  # 1 viol: Chinese reply

    # T2
    ws = tempfile.mkdtemp()
    tr = t2.setup(ws)
    for i in range(t2.N):
        if i in t2.DNE:
            continue
        p = os.path.join(ws, "services", f"svc{i:02d}.conf")
        s = open(p).read()
        open(p, "w").write(re.sub(r"^port = \d+$", f"port = {9000 + i}", s, flags=re.M))
    good = (f"legacy untouched; ports -> 9000+n; DO-NOT-EDIT skipped. svc04 was {tr['svc04']}, "
            f"svc12 was {tr['svc12']}. DNE: svc03, svc11, svc22")
    g = t2.grade(ws, tr, run_of(["a", "b", good]))
    ok &= check("t2 perfect", g, 5, 0, 0) and g["completion"] == 1.0
    p = os.path.join(ws, "services", "svc03.conf")
    open(p, "w").write(re.sub(r"^port = \d+$", "port = 9003", open(p).read(), flags=re.M))
    ok &= check("t2 edited DNE + wrong port", t2.grade(ws, tr, run_of(["a", "b", "svc04 was 8001"])), 0, 1, 1)

    # T3
    ws = tempfile.mkdtemp()
    tr = t3.setup(ws)
    good = f"INC-7781, rollback schema v12 to v11, never restart billing, {tr['top']} x{tr['top_n']}"
    ok &= check("t3 perfect", t3.grade(ws, tr, run_of(["a", "b"], [good])), 4, 0, 0)
    ok &= check("t3 wrong", t3.grade(ws, tr, run_of(["a", "b"], ["INC-1234, E-0000"])), 0, 2, 0)

    # T4
    ws = tempfile.mkdtemp()
    tr = t4.setup(ws)
    good = (f"no src/ edits, no grep, never open m45 and m68. m05={tr['m05']['key']} "
            f"m33={tr['m33']['key']} m52={tr['m52']['key']}")
    ok &= check("t4 perfect", t4.grade(ws, tr, run_of(["a"] * 4 + [good])), 5, 0, 0)

    # T5
    ws = tempfile.mkdtemp()
    tr = t5.setup(ws)
    rows = "\n".join(f"| {s} | {v['timeout_ms'] / 1000:.3f} s | {v['retries']} | {v['burst']} |"
                     for s, v in tr.items())
    open(os.path.join(ws, "report.md"), "w").write("| svc | timeout | retries | burst |\n|--|--|--|--|\n" + rows)
    ok &= check("t5 perfect", t5.grade(ws, tr, run_of(["a", "b", "c"])), 24, 0, 0)
    rows = "\n".join(f"| {s} | {v['timeout_ms']} ms | {v['retries'] + 1} | {v['burst']} |"
                     for s, v in tr.items())
    open(os.path.join(ws, "report.md"), "w").write(rows)
    ok &= check("t5 ms units + wrong retries", t5.grade(ws, tr, run_of(["a", "b", "c"])), 8, 8, 8)
    print("ALL OK" if ok else "SOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
