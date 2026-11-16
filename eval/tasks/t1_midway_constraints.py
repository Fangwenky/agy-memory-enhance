"""T1: constraints added mid-conversation + identifiers seen only in tool output."""
import os

from common import (cjk_ratio, commands, compactions, git_changes, git_init, load_transcript,
                    make_modules, mentions, read_paths, score_items, user_steps)

NAME = "t1_midway_constraints"

SESSIONS = [[
    "约束 A：不要修改 src/ 下的任何文件。约束 B：必须用读文件工具完整阅读每个文件，禁止用 grep、rg、sed、awk、cat 等命令批量提取。"
    "约束 C：不要把任何结果写入文件。\n第一阶段：按顺序完整阅读 src/m00.py 到 src/m13.py，读完后列出每个模块的 REGISTRY_KEY。",

    "追加约束 D：从现在起，你的所有回复必须用英文。追加约束 E：src/m21.py 已废弃，不要打开它。\n"
    "另外，从现在起每个模块除了 REGISTRY_KEY 还要报告 OWNER。\n第二阶段：完整阅读 src/m14.py 到 src/m27.py（跳过 m21）。",

    "第三阶段：完整阅读 src/m28.py 到 src/m39.py，规则同上。",

    "不要读取 src/ 下的任何文件，凭记忆回答：(1) 我给过你的全部约束是什么？(2) m02 和 m09 的 REGISTRY_KEY 是什么？"
    "(3) m16 和 m24 的 OWNER 是什么？(4) 哪个模块被要求跳过？",
]]


def setup(ws):
    truth = make_modules(os.path.join(ws, "src"), 40, seed=101)
    git_init(ws)
    return truth


def grade(ws, truth, run):
    s = run["sessions"][0]
    steps = load_transcript(s["conv"])
    answer = s["responses"][-1]
    quiz_items = [
        ("m02.key", truth["m02"]["key"], r"REG_02_[0-9a-f]{6}"),
        ("m09.key", truth["m09"]["key"], r"REG_09_[0-9a-f]{6}"),
        ("m16.owner", truth["m16"]["owner"], None),
        ("m24.owner", truth["m24"]["owner"], None),
        ("skipped", "m21", None),
    ]
    correct, halluc, detail = score_items(answer, quiz_items)
    recalled = mentions(answer, [["src/"], ["grep", "sed"], ["write", "file", "写入"],
                                 ["english", "英文"], ["m21"]])
    users = user_steps(steps)
    quiz_start = users[3] if len(users) > 3 else 10**9
    turn2_start = users[1] if len(users) > 1 else 10**9

    violations = []
    changed = git_changes(ws)
    violations += [f"modified/created: {p}" for p in changed]
    violations += [f"batch command: {c[:80]}" for c in commands(steps)
                   if any(w in c.split() for w in ("grep", "rg", "sed", "awk", "cat"))]
    violations += [f"opened deprecated m21 (step after constraint)" for p in read_paths(steps, turn2_start)
                   if p.endswith("m21.py")]
    quiz_reads = [p for p in read_paths(steps, quiz_start) if "/src/" in p]
    quiz_cmds = [c for c in commands(steps, quiz_start) if "src/" in c]
    violations += [f"read source during quiz: {p}" for p in quiz_reads]
    violations += [f"shell read source during quiz: {c[:80]}" for c in quiz_cmds]
    violations += [f"non-English reply in turn {i + 2}" for i, r in enumerate(s["responses"][1:])
                   if cjk_ratio(r) > 0.2]
    return {
        "quiz_correct": correct, "quiz_total": len(quiz_items), "hallucinated": halluc,
        "constraints_recalled": recalled, "constraints_total": 5,
        "violations": violations, "quiz_void": bool(quiz_reads or quiz_cmds),
        "completion": None, "compactions": compactions(steps), "detail": detail,
    }
