import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(REPO, "plugin", "agy-memory")
sys.path.insert(0, os.path.join(PLUGIN, "lib"))


def user(i, text):
    return {"step_index": i, "source": "USER_EXPLICIT", "type": "USER_INPUT",
            "content": f"<USER_REQUEST>\n{text}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>"}


def model(i, inp, cache=0):
    return {"step_index": i, "source": "MODEL", "type": "PLANNER_RESPONSE",
            "input_tokens": inp, "cache_read_tokens": cache, "output_tokens": 100}


def tool(i):
    return {"step_index": i, "source": "MODEL", "type": "GENERIC", "content": "ok"}


def checkpoint(i, peak):
    return {"step_index": i, "source": "SYSTEM", "type": "CHECKPOINT",
            "input_tokens": 4000, "cache_read_tokens": peak, "output_tokens": 7000,
            "content": "# Resuming from a compaction\n\nsummary..."}


def write_transcript(path, steps, mode="a"):
    with open(path, mode, encoding="utf-8") as f:
        for s in steps:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")


def run_hook(name, payload, env=None):
    p = subprocess.run(
        [sys.executable, os.path.join(PLUGIN, "hooks", f"{name}.py")],
        input=json.dumps(payload), capture_output=True, text=True,
        env={**os.environ, **(env or {})}, timeout=30)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout or "{}")
