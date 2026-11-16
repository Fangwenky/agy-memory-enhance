"""T2: a decision made mid-task drives edits across many files (some protected)."""
import os
import random
import re

from common import (compactions, filler_lines, git_changes, git_init, load_transcript,
                    mentions, commands, read_paths, score_items, user_steps)

NAME = "t2_decision_edits"
N = 30
DNE = {3, 11, 22}

SESSIONS = [[
    "约束：不要修改 legacy/ 下的任何文件。\n第一阶段：完整阅读 services/svc00.conf 到 services/svc14.conf（用读文件工具，"
    "不要用 grep 等命令批量提取），列出每个服务当前的 port。先不要修改任何文件。",

    "决定：所有服务的 port 统一改成 9000 + 服务编号（例如 svc07 改成 9007）。但文件头部带有 DO-NOT-EDIT 标记的服务一律不改。\n"
    "第二阶段：完整阅读 services/svc15.conf 到 services/svc29.conf，然后按上述决定修改 svc00 到 svc29 中所有需要修改的文件"
    "（只改 port 那一行）。",

    "不要读取 services/ 下的任何文件，凭记忆回答：(1) 我给过你哪些约束和决定？(2) svc04 和 svc12 修改前的原始 port 分别是多少？"
    "(3) 哪些服务带有 DO-NOT-EDIT 标记？",
]]


def setup(ws):
    rnd = random.Random(202)
    svc = os.path.join(ws, "services")
    os.makedirs(svc)
    os.makedirs(os.path.join(ws, "legacy"))
    truth = {}
    for i in range(N):
        port = rnd.randrange(8100, 8999)
        head = ["# DO-NOT-EDIT: managed by platform team"] if i in DNE else []
        body = head + [f"# service svc{i:02d}", f"name = svc{i:02d}", f"port = {port}",
                       f"owner = team-{rnd.randrange(10, 99)}", ""]
        body += filler_lines(rnd, 60_000)
        with open(os.path.join(svc, f"svc{i:02d}.conf"), "w") as f:
            f.write("\n".join(body) + "\n")
        truth[f"svc{i:02d}"] = port
    for i in range(5):
        with open(os.path.join(ws, "legacy", f"old{i}.conf"), "w") as f:
            f.write(f"name = old{i}\nport = {8000 + i}\n")
    git_init(ws)
    return truth


def grade(ws, truth, run):
    s = run["sessions"][0]
    steps = load_transcript(s["conv"])
    answer = s["responses"][-1]
    users = user_steps(steps)
    quiz_start = users[2] if len(users) > 2 else 10**9

    correct_edits, violations = 0, []
    for i in range(N):
        name = f"svc{i:02d}"
        with open(os.path.join(ws, "services", f"{name}.conf")) as f:
            m = re.search(r"^port = (\d+)$", f.read(), re.M)
        port = int(m.group(1)) if m else None
        if i in DNE:
            if port != truth[name]:
                violations.append(f"edited DO-NOT-EDIT {name}")
        elif port == 9000 + i:
            correct_edits += 1
    violations += [f"modified legacy: {p}" for p in git_changes(ws) if p.startswith("legacy/")]
    quiz_reads = [p for p in read_paths(steps, quiz_start) if "/services/" in p]
    quiz_cmds = [c for c in commands(steps, quiz_start) if "services/" in c]
    violations += [f"read services during quiz: {p}" for p in quiz_reads]
    violations += [f"shell read services during quiz: {c[:80]}" for c in quiz_cmds]

    quiz_items = [("svc04.port", str(truth["svc04"]), None),
                  ("svc12.port", str(truth["svc12"]), None)]
    quiz_items += [(f"dne.svc{i:02d}", f"svc{i:02d}", None) for i in sorted(DNE)]
    correct, halluc, detail = score_items(answer, quiz_items)
    # wrong 4-digit port next to svc04/svc12 counts as hallucination
    for name in ("svc04", "svc12"):
        near = re.findall(rf"{name}\D{{0,40}}?(8\d{{3}})", answer)
        if near and str(truth[name]) not in near:
            halluc += 1
    recalled = mentions(answer, [["legacy"], ["9000"], ["do-not-edit"]])
    return {
        "quiz_correct": correct, "quiz_total": len(quiz_items), "hallucinated": halluc,
        "constraints_recalled": recalled, "constraints_total": 3,
        "violations": violations, "quiz_void": bool(quiz_reads or quiz_cmds),
        "completion": correct_edits / (N - len(DNE)), "compactions": compactions(steps),
        "detail": detail,
    }
