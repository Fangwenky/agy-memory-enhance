"""Shared helpers for agy-memory evaluation tasks."""
import json
import os
import random
import re
import subprocess

CLI_BRAIN = os.path.expanduser("~/.gemini/antigravity-cli/brain")
WORDS = ("alpha beta gamma delta ledger cursor shard replica quorum lease "
         "fence epoch vector bloom cache index segment wal snapshot").split()
OWNERS = ("mira", "tomas", "anaya", "kofi", "lena", "ravi", "sora", "ines", "yuki", "omar")
CJK = re.compile(r"[\u4e00-\u9fff]")


# ------------------------------------------------------------------ workload
def make_modules(src, n, seed, size=30_000, start=0):
    """Python modules with a REGISTRY_KEY, an OWNER and a last function name."""
    rnd = random.Random(seed)
    os.makedirs(src, exist_ok=True)
    truth = {}
    for i in range(start, start + n):
        key = f"REG_{i:02d}_{rnd.randrange(16**6):06x}"
        owner = f"{rnd.choice(OWNERS)}-{rnd.randrange(100, 999)}"
        lines = [f'"""Module m{i:02d}."""', "", f'REGISTRY_KEY = "{key}"', f'OWNER = "{owner}"', ""]
        k, last = 0, None
        while sum(len(x) + 1 for x in lines) < size:
            a, b, c = rnd.sample(WORDS, 3)
            last = f"{a}_{b}_{k}"
            lines += [f"def {last}(x, y):", f'    """Combine {a} with {b} using {c}."""',
                      f"    t = (x * {rnd.randint(2, 97)} + y) % {rnd.randint(101, 997)}",
                      f"    return {{'{c}': t, 'src': 'm{i:02d}'}}", ""]
            k += 1
        with open(os.path.join(src, f"m{i:02d}.py"), "w") as f:
            f.write("\n".join(lines))
        truth[f"m{i:02d}"] = {"key": key, "owner": owner, "last": last}
    return truth


def filler_lines(rnd, n_bytes, prefix="#"):
    out, size = [], 0
    while size < n_bytes:
        a, b, c = rnd.sample(WORDS, 3)
        ln = f"{prefix} {a} {b} {c} {rnd.randrange(10**8):08d} tuning note for {a}-{b}"
        out.append(ln)
        size += len(ln) + 1
    return out


def git_init(ws):
    subprocess.run(["git", "init", "-q", ws], check=True)
    subprocess.run(["git", "-C", ws, "add", "-A"], check=True)
    subprocess.run(["git", "-C", ws, "-c", "user.email=eval@local", "-c", "user.name=eval",
                    "commit", "-qm", "initial"], check=True)


def git_changes(ws, ignore=(".agy-memory", ".agents")):
    p = subprocess.run(["git", "-C", ws, "status", "--porcelain", "-uall"],
                       capture_output=True, text=True)
    paths = [ln[3:] for ln in p.stdout.splitlines() if len(ln) > 3]
    return [x for x in paths if not x.startswith(ignore)]


# ------------------------------------------------------------------ transcripts
def load_transcript(conv):
    if not conv:
        return []
    path = os.path.join(CLI_BRAIN, conv, ".system_generated", "logs", "transcript_full.jsonl")
    steps = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    steps.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return steps


def tool_calls(steps, after_step=-1):
    for s in steps:
        if s.get("type") == "PLANNER_RESPONSE" and s.get("step_index", 0) > after_step:
            for tc in s.get("tool_calls") or []:
                yield s["step_index"], tc.get("name"), tc.get("args") or {}


def user_steps(steps):
    return [s["step_index"] for s in steps if s.get("type") == "USER_INPUT"]


def compactions(steps):
    return sum(1 for s in steps if s.get("type") == "CHECKPOINT")


def read_paths(steps, after_step=-1):
    return [a.get("Path") or a.get("AbsolutePath") or "" for _, n, a in tool_calls(steps, after_step)
            if n in ("read_file", "view_file")]


def commands(steps, after_step=-1):
    """Shell commands run by the agent, excluding agy-memory CLI calls (their text quotes rules)."""
    return [a.get("CommandLine", "") for _, n, a in tool_calls(steps, after_step)
            if n == "run_command" and ".agy-memory/bin/mem" not in a.get("CommandLine", "")
            and not a.get("CommandLine", "").lstrip().startswith("mem ")]


def cjk_ratio(text):
    letters = [ch for ch in text if ch.isalpha()]
    return len(CJK.findall(text)) / max(1, len(letters))


# ------------------------------------------------------------------ scoring
def score_items(answer, items):
    """items: list of (label, expected, wrong_pattern|None).

    correct      expected string appears in the answer
    hallucinated a value matching wrong_pattern appears but it is not the expected one
    """
    correct, halluc, detail = 0, 0, []
    for label, expected, wrong in items:
        ok = expected in answer
        bad = False
        if not ok and wrong:
            bad = bool(re.search(wrong, answer))
        correct += ok
        halluc += bad
        detail.append({"item": label, "expected": expected,
                       "result": "correct" if ok else ("hallucinated" if bad else "missing")})
    return correct, halluc, detail


def mentions(answer, keyword_groups):
    """Count groups where any keyword appears (case-insensitive)."""
    low = answer.lower()
    return sum(1 for group in keyword_groups if any(k.lower() in low for k in group))
