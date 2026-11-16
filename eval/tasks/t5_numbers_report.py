"""T5: exact numbers read early must be reproduced in a deliverable after compaction."""
import os
import random
import re

from common import (compactions, git_init, load_transcript, make_modules, mentions, commands, read_paths,
                    user_steps)

NAME = "t5_numbers_report"
SERVICES = ["auth", "billing", "search", "upload", "notify", "export", "geo", "audit"]

SESSIONS = [[
    "第一阶段：完整阅读 thresholds/ 目录下的全部文件，记住每个服务的 timeout_ms、retries 和 burst 配置。先不要写任何文件。",

    "追加要求：最终报告中所有时间值必须以秒为单位，保留 3 位小数（例如 1234 ms 写成 1.234 s）。\n"
    "第二阶段：为了解代码背景，请按顺序完整阅读 src/m00.py 到 src/m39.py（用读文件工具，不要用 grep 等命令批量提取），"
    "每读完一个用一句话说明它的 OWNER。",

    "最后：不要重新读取 thresholds/ 目录下的任何文件。根据你之前读到的内容，创建 report.md，用一个 Markdown 表格列出"
    "每个服务的 timeout（按我的单位要求）、retries 和 burst。",
]]


def setup(ws):
    rnd = random.Random(505)
    d = os.path.join(ws, "thresholds")
    os.makedirs(d)
    truth = {}
    for svc in SERVICES:
        t = {"timeout_ms": rnd.randrange(150, 9000), "retries": rnd.randrange(1, 9),
             "burst": rnd.randrange(10, 500)}
        truth[svc] = t
        with open(os.path.join(d, f"{svc}.ini"), "w") as f:
            f.write(f"[{svc}]\n" + "\n".join(f"{k} = {v}" for k, v in t.items()) + "\n")
    make_modules(os.path.join(ws, "src"), 40, seed=505)
    git_init(ws)
    return truth


def grade(ws, truth, run):
    s = run["sessions"][0]
    steps = load_transcript(s["conv"])
    users = user_steps(steps)
    last_start = users[2] if len(users) > 2 else 10**9
    path = os.path.join(ws, "report.md")
    report = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    correct = halluc = 0
    detail = []
    unit_ok = 0
    for svc, t in truth.items():
        row = next((ln for ln in report.splitlines() if svc in ln.lower() and "|" in ln), "")
        secs = f"{t['timeout_ms'] / 1000:.3f}"
        for label, exp in (("timeout", secs), ("retries", str(t["retries"])), ("burst", str(t["burst"]))):
            cells = [c.strip() for c in row.split("|")]
            ok = any(re.fullmatch(rf"{re.escape(exp)}\s*(s|秒)?", c) for c in cells)
            if not ok and label == "timeout" and str(t["timeout_ms"]) in row:
                ok_ms = True
            else:
                ok_ms = False
            correct += ok
            wrong = bool(row) and not ok and not ok_ms
            halluc += wrong
            detail.append({"item": f"{svc}.{label}", "expected": exp,
                           "result": "correct" if ok else ("unit_wrong" if ok_ms else
                                                           ("hallucinated" if wrong else "missing"))})
        unit_ok += bool(re.search(rf"\b{re.escape(secs)}\b", row))
    re_reads = [p for p in read_paths(steps, last_start) if "/thresholds/" in p] + [c[:80] for c in commands(steps, last_start) if "thresholds" in c]
    violations = [f"re-read thresholds in final turn: {p}" for p in re_reads]
    violations += [f"timeout not in seconds for {d['item']}" for d in detail if d["result"] == "unit_wrong"]
    if not report:
        violations.append("report.md missing")
    return {
        "quiz_correct": correct, "quiz_total": 3 * len(truth), "hallucinated": halluc,
        "constraints_recalled": None, "constraints_total": None,
        "violations": violations, "quiz_void": bool(re_reads),
        "completion": 1.0 if report else 0.0, "compactions": compactions(steps), "detail": detail,
    }
