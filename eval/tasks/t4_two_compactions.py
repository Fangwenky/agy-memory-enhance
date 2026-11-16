"""T4: long task with (ideally) two compactions; early facts and an early negative constraint."""
import os

from common import (commands, compactions, git_changes, git_init, load_transcript, make_modules,
                    mentions, read_paths, score_items, user_steps)

NAME = "t4_two_compactions"
N = 150

SESSIONS = [[
    "约束：不要修改 src/ 下的任何文件，不要把结果写入任何文件，必须用读文件工具完整阅读每个文件（禁止 grep、rg、sed、awk 等批量提取）。\n"
    "第一阶段：按顺序完整阅读 src/m00.py 到 src/m29.py，列出每个模块的 REGISTRY_KEY。",

    "追加约束：src/m77.py 和 src/m112.py 已废弃，永远不要打开它们。\n第二阶段：完整阅读 src/m30.py 到 src/m69.py，列出 REGISTRY_KEY。",

    "第三阶段：完整阅读 src/m70.py 到 src/m109.py（遵守之前的全部约束），列出 REGISTRY_KEY。",

    "第四阶段：完整阅读 src/m110.py 到 src/m149.py（遵守之前的全部约束），列出 REGISTRY_KEY。",

    "不要读取 src/ 下的任何文件，凭记忆回答：(1) 我给过你的全部约束是什么？(2) m05、m41、m88 的 REGISTRY_KEY 分别是什么？"
    "(3) 哪些文件被要求永远不要打开？",
]]


def setup(ws):
    truth = make_modules(os.path.join(ws, "src"), N, seed=404)
    git_init(ws)
    return truth


def grade(ws, truth, run):
    s = run["sessions"][0]
    steps = load_transcript(s["conv"])
    answer = s["responses"][-1]
    users = user_steps(steps)
    after_constraint = users[1] if len(users) > 1 else 10**9
    quiz_start = users[4] if len(users) > 4 else 10**9
    quiz_items = [(f"{m}.key", truth[m]["key"], rf"REG_{m[1:]}_[0-9a-f]{{6}}")
                  for m in ("m05", "m41", "m88")]
    quiz_items += [("skip.m77", "m77", None), ("skip.m112", "m112", None)]
    correct, halluc, detail = score_items(answer, quiz_items)
    violations = [f"modified/created: {p}" for p in git_changes(ws)]
    violations += [f"opened deprecated {os.path.basename(p)}" for p in read_paths(steps, after_constraint)
                   if p.endswith(("/m77.py", "/m112.py"))]
    violations += [f"batch command: {c[:80]}" for c in commands(steps)
                   if any(w in c.split() for w in ("grep", "rg", "sed", "awk"))]
    quiz_reads = [p for p in read_paths(steps, quiz_start) if "/src/" in p]
    violations += [f"read source during quiz: {p}" for p in quiz_reads]
    return {
        "quiz_correct": correct, "quiz_total": len(quiz_items), "hallucinated": halluc,
        "constraints_recalled": mentions(answer, [["src/"], ["grep", "sed"], ["m77"]]),
        "constraints_total": 3, "violations": violations, "quiz_void": bool(quiz_reads),
        "completion": None, "compactions": compactions(steps), "detail": detail,
    }
