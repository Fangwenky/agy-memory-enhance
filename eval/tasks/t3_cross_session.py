"""T3: cross-session continuity. Decisions in session A must be known in session B."""
import collections
import os
import random

from common import commands, load_transcript, mentions, read_paths, score_items, user_steps, git_init

NAME = "t3_cross_session"
CODES = ["E-4102", "E-4417", "E-5003", "E-5120", "E-6031", "E-7008"]

SESSIONS = [
    [
        "请完整阅读 logs/part1/ 下的全部日志文件（用读文件工具，不要用 grep 等命令批量提取），"
        "统计每种错误码（形如 E-xxxx）出现的次数，并告诉我出现次数最多的错误码。",

        "好的。我的结论和决定如下，请记住：主事故编号定为 INC-7781；修复方案选 B，即把数据库 schema 从 v12 回滚到 v11；"
        "约束：在任何情况下都不要重启 billing 服务。今天先到这里。",
    ],
    [
        "我们继续昨天关于日志事故的分析。不要读取 logs/part1/ 下的文件。请直接回答：(1) 之前确定的主事故编号是什么？"
        "(2) 选定的修复方案是什么？(3) 我设定过什么约束？(4) logs/part1 中出现次数最多的错误码是什么，出现了多少次？",
    ],
]


def setup(ws):
    rnd = random.Random(303)
    d = os.path.join(ws, "logs", "part1")
    os.makedirs(d)
    weights = [5, 9, 3, 14, 4, 6]
    counts = collections.Counter()
    for f_i in range(6):
        lines = []
        while sum(len(x) + 1 for x in lines) < 40_000:
            if rnd.random() < 0.08:
                code = rnd.choices(CODES, weights)[0]
                counts[code] += 1
                lines.append(f"2026-11-1{f_i} {rnd.randrange(24):02d}:{rnd.randrange(60):02d} ERROR {code} "
                             f"request {rnd.randrange(10**6)} failed in {rnd.choice(['api', 'db', 'queue'])}")
            else:
                lines.append(f"2026-11-1{f_i} {rnd.randrange(24):02d}:{rnd.randrange(60):02d} INFO "
                             f"handled request {rnd.randrange(10**6)} in {rnd.randrange(5, 900)}ms")
        with open(os.path.join(d, f"app{f_i}.log"), "w") as f:
            f.write("\n".join(lines) + "\n")
    top, n = counts.most_common(1)[0]
    git_init(ws)
    return {"counts": dict(counts), "top": top, "top_n": n}


def grade(ws, truth, run):
    b = run["sessions"][1]
    steps = load_transcript(b["conv"])
    answer = b["responses"][-1]
    quiz_items = [("incident", "INC-7781", r"INC-\d{4}"),
                  ("plan", "v11", None),
                  ("top_code", truth["top"], r"E-\d{4}"),
                  ("top_count", str(truth["top_n"]), None)]
    correct, halluc, detail = score_items(answer, quiz_items)
    reads = [p for p in read_paths(steps) if "/logs/part1/" in p] + [c[:80] for c in commands(steps) if "logs/part1" in c]
    return {
        "quiz_correct": correct, "quiz_total": len(quiz_items), "hallucinated": halluc,
        "constraints_recalled": mentions(answer, [["billing"]]), "constraints_total": 1,
        "violations": [f"session B read part1: {p}" for p in reads], "quiz_void": bool(reads),
        "completion": None, "compactions": 0, "detail": detail,
    }
