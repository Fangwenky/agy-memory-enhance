"""Incremental reader for agy transcript_full.jsonl (see spike/FINDINGS.md)."""
import json
import os
import re

_USER_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.S)


def read_new(path, offset):
    """Return (steps, new_offset, was_reset). Only complete lines are consumed."""
    try:
        size = os.path.getsize(path)
    except (OSError, TypeError):
        return [], offset, False
    reset = size < offset
    if reset:
        offset = 0
    if size == offset:
        return [], offset, reset
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read(size - offset)
    end = chunk.rfind(b"\n")
    if end < 0:
        return [], offset, reset
    steps = []
    for line in chunk[: end + 1].splitlines():
        if not line.strip():
            continue
        try:
            steps.append(json.loads(line))
        except ValueError:
            continue
    return steps, offset + end + 1, reset


def ctx_tokens(step):
    """Context size of a model call = uncached input + cache reads."""
    if "input_tokens" not in step and "cache_read_tokens" not in step:
        return None
    return int(step.get("input_tokens") or 0) + int(step.get("cache_read_tokens") or 0)


def is_checkpoint(step):
    return step.get("type") == "CHECKPOINT"


def is_user_input(step):
    return step.get("type") == "USER_INPUT"


def is_model_call(step):
    return step.get("type") == "PLANNER_RESPONSE"


def user_text(step):
    content = step.get("content") or ""
    m = _USER_RE.search(content)
    return m.group(1) if m else content.strip()


def find_step(path, step_index):
    """Linear scan for one step (used by `mem show <conv>#<step>`)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                if f'"step_index":{step_index},' not in line and \
                        f'"step_index": {step_index},' not in line:
                    continue
                try:
                    s = json.loads(line)
                except ValueError:
                    continue
                if s.get("step_index") == step_index:
                    return s
    except OSError:
        pass
    return None
