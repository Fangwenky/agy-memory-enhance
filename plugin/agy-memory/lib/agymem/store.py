"""On-disk memory store (design doc §6). Append-only JSONL with file locks."""
import fcntl
import hashlib
import json
import os
import re
import tempfile
import time

DIR_NAME = ".agy-memory"


def resolve_root(payload):
    """Workspace-local store, or a per-cwd fallback when there is no workspace."""
    ws = [p for p in (payload.get("workspacePaths") or []) if p]
    if ws:
        return os.path.join(ws[0], DIR_NAME)
    base = os.environ.get("PLUGIN_DATA") or os.path.expanduser("~/.agy-memory")
    key = hashlib.sha1((payload.get("cwd") or os.getcwd()).encode()).hexdigest()[:12]
    return os.path.join(base, "projects", key)


def redact(value, patterns):
    if isinstance(value, str):
        for p in patterns:
            value = re.sub(p, _mask, value)
        return value
    if isinstance(value, dict):
        return {k: redact(v, patterns) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, patterns) for v in value]
    return value


def _mask(m):
    # keep "key=" prefixes readable when the pattern captured them
    if m.lastindex and m.lastindex >= 2:
        return m.group(1) + m.group(2) + "[REDACTED]"
    return "[REDACTED]"


class Store:
    def __init__(self, root, redact_patterns=()):
        self.root = root
        self.patterns = list(redact_patterns)

    # ---------- layout ----------
    def ensure(self):
        for sub in ("", "state", "sessions", "archive", "bin"):
            os.makedirs(os.path.join(self.root, sub), exist_ok=True)
        gi = os.path.join(self.root, ".gitignore")
        if not os.path.exists(gi):
            with open(gi, "w") as f:
                f.write("# agy-memory: delete this file to commit your memory\n*\n")
        return self

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    # ---------- jsonl ----------
    def append(self, name, obj):
        self.append_many(name, [obj])

    def append_many(self, name, objs):
        if not objs:
            return
        data = "".join(
            json.dumps(redact(o, self.patterns), ensure_ascii=False) + "\n" for o in objs)
        with open(self.path(name), "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(data)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read(self, name):
        rows = []
        try:
            with open(self.path(name), encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except ValueError:
                            pass
        except OSError:
            pass
        return rows

    def size(self, name):
        try:
            return os.path.getsize(self.path(name))
        except OSError:
            return 0

    def event(self, conv, kind, data, step=None):
        return {"ts": time.time(), "convId": conv, "step": step, "kind": kind, "data": data}

    # ---------- json state ----------
    def load_json(self, *parts, default=None):
        try:
            with open(self.path(*parts), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {} if default is None else default

    def save_json(self, obj, *parts):
        target = self.path(*parts)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target), prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, target)

    def conv_state(self, conv):
        return self.load_json("state", f"{conv}.json")

    def save_conv_state(self, conv, state):
        self.save_json(state, "state", f"{conv}.json")
