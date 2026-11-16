#!/usr/bin/env python3
"""Run the agy-memory evaluation: every task x {plugin, baseline} through the agy CLI.

Usage:
  python3 eval/run.py --out ~/agy-eval/run1 [--tasks t1,t3] [--arms plugin,baseline]
                      [--model gemini-4-hydrogen-medium] [--dry-run]
  python3 eval/run.py --out ~/agy-eval/run1 --grade-only

Each run gets a fresh workspace <out>/<task>-<arm>/ws. Results: <out>/<task>-<arm>/run.json, grade.json.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tasks"))

ALL_TASKS = ["t1_midway_constraints", "t2_decision_edits", "t3_cross_session",
             "t4_two_compactions", "t5_numbers_report"]
_LOG_LOCK = threading.Lock()


def log(out, msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    with _LOG_LOCK:
        print(line, flush=True)
        with open(os.path.join(out, "progress.log"), "a") as f:
            f.write(line + "\n")


def run_session(ws, turns, model, logpath, timeout_s):
    stdin = "".join(json.dumps({"event": "user", "message": {"content": t}}, ensure_ascii=False) + "\n"
                    for t in turns)
    cmd = ["agy", "--input-format", "stream-json", "--output-format", "stream-json",
           "--model", model, "--sandbox", "--dangerously-skip-permissions",
           "--print-timeout", f"{timeout_s}s", "-p="]
    t0 = time.time()
    with open(logpath, "w") as lf:
        p = subprocess.run(cmd, input=stdin, cwd=ws, stdout=subprocess.PIPE, stderr=lf, text=True)
        lf.write(p.stdout)
    conv, responses, usage, statuses = None, [], [], []
    for line in p.stdout.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("event") == "init":
            conv = ev.get("conversation_id")
        if ev.get("event") == "result":
            r = ev["result"]
            conv = conv or r.get("conversation_id")
            responses.append(r.get("response") or "")
            statuses.append(r.get("status"))
            usage.append(r.get("usage") or {})
    # result usage is cumulative per process; keep the last one as the session total
    return {"conv": conv, "responses": responses, "statuses": statuses,
            "usage": usage[-1] if usage else {}, "seconds": round(time.time() - t0),
            "exit": p.returncode}


def do_run(task, arm, out, model, timeout_s):
    d = os.path.join(out, f"{task.NAME}-{arm}")
    ws = os.path.join(d, "ws")
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(ws)
    truth = task.setup(ws)
    if arm == "plugin":
        subprocess.run(["sh", os.path.join(REPO, "scripts", "install-dev.sh"), ws],
                       check=True, capture_output=True)
        subprocess.run(["git", "-C", ws, "add", "-A"], check=True)
        subprocess.run(["git", "-C", ws, "-c", "user.email=e@l", "-c", "user.name=e",
                        "commit", "-qm", "plugin"], check=True)
    with open(os.path.join(d, "truth.json"), "w") as f:
        json.dump(truth, f, ensure_ascii=False, indent=1)
    run = {"task": task.NAME, "arm": arm, "model": model, "sessions": []}
    for si, turns in enumerate(task.SESSIONS):
        s = run_session(ws, turns, model, os.path.join(d, f"session{si}.log"), timeout_s)
        run["sessions"].append(s)
        log(out, f"  {task.NAME}/{arm} session {si}: conv={s['conv']} turns={len(s['responses'])}/"
                 f"{len(turns)} status={s['statuses']} {s['seconds']}s")
    with open(os.path.join(d, "run.json"), "w") as f:
        json.dump(run, f, ensure_ascii=False, indent=1)
    return d


def do_grade(task, d):
    ws = os.path.join(d, "ws")
    truth = json.load(open(os.path.join(d, "truth.json")))
    run = json.load(open(os.path.join(d, "run.json")))
    g = task.grade(ws, truth, run)
    g["tokens"] = {k: sum(int(s["usage"].get(k) or 0) for s in run["sessions"])
                   for k in ("input_tokens", "cache_read_tokens", "output_tokens")}
    g["seconds"] = sum(s["seconds"] for s in run["sessions"])
    g["complete_run"] = all(len(s["responses"]) == len(t) for s, t in zip(run["sessions"], task.SESSIONS))
    mem_dir = os.path.join(ws, ".agy-memory")
    if os.path.isdir(mem_dir):
        ev = [json.loads(x) for x in open(os.path.join(mem_dir, "events.jsonl"))] \
            if os.path.exists(os.path.join(mem_dir, "events.jsonl")) else []
        led = open(os.path.join(mem_dir, "ledger.jsonl")).read().splitlines() \
            if os.path.exists(os.path.join(mem_dir, "ledger.jsonl")) else []
        kinds = {}
        for e in ev:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        g["memory"] = {"events": kinds, "ledger_entries": len(led)}
    with open(os.path.join(d, "grade.json"), "w") as f:
        json.dump(g, f, ensure_ascii=False, indent=1)
    return g


def _one(task, arm, out, a):
    name = task.NAME
    d = os.path.join(out, f"{name}-{arm}")
    if a.dry_run:
        os.makedirs(os.path.join(d, "ws"), exist_ok=True)
        task.setup(os.path.join(d, "ws"))
        log(out, f"built {d}")
        return
    if a.skip_done and os.path.exists(os.path.join(d, "grade.json")):
        g = json.load(open(os.path.join(d, "grade.json")))
        if g.get("complete_run"):
            log(out, f"skip (already done) {name}/{arm}")
            return
    if not a.grade_only:
        log(out, f"run {name}/{arm}")
        try:
            do_run(task, arm, out, a.model, a.timeout)
        except Exception as e:  # noqa: BLE001
            log(out, f"  FAILED {name}/{arm}: {e!r}")
            return
    try:
        g = do_grade(task, d)
        log(out, f"  graded {name}/{arm}: quiz {g['quiz_correct']}/{g['quiz_total']} "
                 f"halluc {g['hallucinated']} violations {len(g['violations'])} "
                 f"compactions {g['compactions']}")
    except Exception as e:  # noqa: BLE001
        log(out, f"  GRADE FAILED {name}/{arm}: {e!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--tasks", default=",".join(ALL_TASKS))
    ap.add_argument("--arms", default="plugin,baseline")
    ap.add_argument("--model", default="gemini-4-hydrogen-medium")
    ap.add_argument("--timeout", type=int, default=5400, help="per session, seconds")
    ap.add_argument("--jobs", type=int, default=1, help="parallel runs")
    ap.add_argument("--skip-done", action="store_true")
    ap.add_argument("--grade-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="only build workspaces")
    a = ap.parse_args()
    out = os.path.expanduser(a.out)
    os.makedirs(out, exist_ok=True)
    names = []
    for prefix in a.tasks.split(","):
        for n in ALL_TASKS:
            if n.startswith(prefix) and n not in names:
                names.append(n)
    tasks = [importlib.import_module(n) for n in names]
    work = [(task, arm) for task in tasks for arm in a.arms.split(",")]
    with ThreadPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        futs = [ex.submit(_one, task, arm, out, a) for task, arm in work]
        for f in as_completed(futs):
            f.result()


if __name__ == "__main__":
    main()
