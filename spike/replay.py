#!/usr/bin/env python3
"""Replay a real transcript through pre_invocation, one model call at a time.

Usage: python3 spike/replay.py <transcript_full.jsonl> [model_name]
Prints every injection and a summary of detected compactions.
"""
import json
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOOK = os.path.join(REPO, "plugin", "agy-memory", "hooks", "pre_invocation.py")


def main():
    src = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "replay-model"
    ws = tempfile.mkdtemp(prefix="agymem-replay-")
    tp = os.path.join(ws, "transcript_full.jsonl")
    open(tp, "w").close()
    lines = open(src, encoding="utf-8").read().splitlines(keepends=True)
    payload = {"hookEventName": "PreInvocation", "conversationId": "replay",
               "workspacePaths": [ws], "transcriptPath": tp, "modelName": model}
    calls = 0
    with open(tp, "a", encoding="utf-8") as out:
        for line in lines:
            out.write(line)
            out.flush()
            step = json.loads(line)
            # agy calls the model right after user input / tool results
            if step.get("type") in ("USER_INPUT", "GENERIC", "CHECKPOINT"):
                calls += 1
                p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                                   capture_output=True, text=True)
                res = json.loads(p.stdout or "{}")
                for s in res.get("injectSteps", []):
                    msg = s["systemMessage"]["systemMessage"]
                    print(f"step {step.get('step_index'):>4}: {msg.splitlines()[0][:150]}")
    ev = [json.loads(x) for x in open(os.path.join(ws, ".agy-memory", "events.jsonl"))]
    kinds = {}
    for e in ev:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"\nhook calls: {calls}; events: {kinds}")
    for e in ev:
        if e["kind"] == "compaction":
            print(f"compaction @step {e['step']}: signal={e['data']['signal']} peak={e['data']['peak']}")
    print("models.json:", open(os.path.join(ws, ".agy-memory", "state", "models.json")).read()
          if os.path.exists(os.path.join(ws, ".agy-memory", "state", "models.json")) else "-")


if __name__ == "__main__":
    main()
