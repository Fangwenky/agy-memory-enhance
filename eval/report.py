#!/usr/bin/env python3
"""Aggregate grade.json files into a markdown results table.

Usage: python3 eval/report.py ~/agy-eval/run1 > eval/RESULTS.md
"""
import glob
import json
import os
import sys


def main():
    out = os.path.expanduser(sys.argv[1])
    rows = {}
    for g in sorted(glob.glob(os.path.join(out, "*", "grade.json"))):
        name = os.path.basename(os.path.dirname(g))
        task, arm = name.rsplit("-", 1)
        rows.setdefault(task, {})[arm] = json.load(open(g))

    def fmt(g, key):
        if not g:
            return "-"
        if key == "quiz":
            return f"{g['quiz_correct']}/{g['quiz_total']}" + (" (void)" if g.get("quiz_void") else "")
        if key == "constraints":
            return "-" if g.get("constraints_total") is None else \
                f"{g['constraints_recalled']}/{g['constraints_total']}"
        if key == "violations":
            return str(len(g["violations"]))
        if key == "tokens":
            t = g["tokens"]
            return f"{(t['input_tokens'] + t['cache_read_tokens'] + t['output_tokens']) / 1e6:.1f}M"
        if key == "completion":
            return "-" if g.get("completion") is None else f"{g['completion']:.0%}"
        return str(g.get(key, "-"))

    cols = [("quiz", "事实正确"), ("hallucinated", "编造"), ("constraints", "约束复述"),
            ("violations", "约束违反"), ("completion", "完成度"), ("compactions", "压缩次数"),
            ("tokens", "处理 tokens")]
    print("| 任务 | 组别 | " + " | ".join(c[1] for c in cols) + " |")
    print("| :-- | :-- | " + " | ".join(":--" for _ in cols) + " |")
    tot = {"plugin": {"q": 0, "qt": 0, "h": 0, "v": 0, "tok": 0},
           "baseline": {"q": 0, "qt": 0, "h": 0, "v": 0, "tok": 0}}
    for task, arms in rows.items():
        for arm in ("plugin", "baseline"):
            g = arms.get(arm)
            print(f"| {task} | {arm} | " + " | ".join(fmt(g, c[0]) for c in cols) + " |")
            if g:
                t = tot[arm]
                t["q"] += g["quiz_correct"]
                t["qt"] += g["quiz_total"]
                t["h"] += g["hallucinated"]
                t["v"] += len(g["violations"])
                tk = g["tokens"]
                t["tok"] += tk["input_tokens"] + tk["cache_read_tokens"] + tk["output_tokens"]
    print()
    print("| 汇总 | 事实正确 | 编造 | 约束违反 | 处理 tokens |")
    print("| :-- | :-- | :-- | :-- | :-- |")
    for arm, t in tot.items():
        print(f"| {arm} | {t['q']}/{t['qt']} | {t['h']} | {t['v']} | {t['tok'] / 1e6:.1f}M |")
    print("\n## 违反明细\n")
    for task, arms in rows.items():
        for arm, g in arms.items():
            for v in g["violations"]:
                print(f"- {task}/{arm}: {v}")
    print("\n## 题目明细\n")
    for task, arms in rows.items():
        for arm, g in arms.items():
            bad = [d for d in g.get("detail", []) if d["result"] != "correct"]
            if bad:
                print(f"- {task}/{arm}: " + "; ".join(f"{d['item']}={d['result']}" for d in bad))


if __name__ == "__main__":
    main()
