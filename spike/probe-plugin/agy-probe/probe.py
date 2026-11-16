#!/usr/bin/env python3
"""agy-probe: records every hook payload plus transcript state, for M0.

Never blocks or changes agent behaviour, except injecting a uniquely marked
systemMessage at SessionStart and at the Nth PreInvocation, so we can later
check whether injected messages survive compaction.

Output: $AGY_PROBE_OUT (default ~/.agy-probe/out)/<conversationId>.jsonl
"""
import json
import os
import sys
import time
import uuid

OUT = os.path.expanduser(os.environ.get("AGY_PROBE_OUT", "~/.agy-probe/out"))
INJECT_AT = int(os.environ.get("AGY_PROBE_INJECT_AT", "3"))
MAX_STR = 2000


def clip(v):
    if isinstance(v, str):
        return v if len(v) <= MAX_STR else v[:MAX_STR] + f"...<{len(v)} chars>"
    if isinstance(v, dict):
        return {k: clip(x) for k, x in v.items()}
    if isinstance(v, list):
        return [clip(x) for x in v[:50]]
    return v


def transcript_state(path):
    st = {"path": path, "readable": False}
    if not path:
        return st
    try:
        st["size"] = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, st["size"] - 64 * 1024))
            tail = f.read().decode("utf-8", "replace").splitlines()[-3:]
        st["readable"] = True
        st["tail"] = [clip(t) for t in tail]
        full = path.replace("transcript.jsonl", "transcript_full.jsonl")
        if full != path and os.path.exists(full):
            st["full_size"] = os.path.getsize(full)
    except Exception as e:  # noqa: BLE001
        st["error"] = repr(e)
    return st


def main():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        payload = {"_unparsed": raw[:MAX_STR]}
    event = payload.get("hookEventName") or (sys.argv[1] if len(sys.argv) > 1 else "?")
    conv = payload.get("conversationId", "unknown")

    os.makedirs(OUT, exist_ok=True)
    state_path = os.path.join(OUT, f"{conv}.state.json")
    try:
        state = json.load(open(state_path))
    except Exception:  # noqa: BLE001
        state = {"pre_count": 0}

    out = {}
    injected = None
    if event == "SessionStart":
        injected = f"PROBE-MARKER-START-{uuid.uuid4().hex[:8]}"
    elif event == "PreInvocation":
        state["pre_count"] += 1
        if state["pre_count"] == INJECT_AT:
            injected = f"PROBE-MARKER-PRE-{uuid.uuid4().hex[:8]}"
    if injected:
        msg = (f"[{injected}] agy-probe test marker. Ignore this message; "
               "it is only used to check whether injected messages survive context compaction.")
        out = {"injectSteps": [{"systemMessage": {"systemMessage": msg}}]}

    rec = {
        "ts": time.time(),
        "event": event,
        "argv_event": sys.argv[1] if len(sys.argv) > 1 else None,
        "payload": clip(payload),
        "transcript": transcript_state(payload.get("transcriptPath")),
        "injected": injected,
        "env": {k: os.environ.get(k) for k in ("PLUGIN_ROOT", "PLUGIN_DATA", "HOME")},
        "proc_cwd": os.getcwd(),
    }
    with open(os.path.join(OUT, f"{conv}.jsonl"), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with open(state_path, "w") as f:
        json.dump(state, f)
    print(json.dumps(out))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001  never break the agent
        sys.stderr.write(f"agy-probe error: {e!r}\n")
        print("{}")
