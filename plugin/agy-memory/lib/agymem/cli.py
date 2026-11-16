"""`mem`: the agent-facing CLI over the memory store (design doc §9)."""
import argparse
import datetime
import glob
import gzip
import json
import os
import re
import sys
import time

from . import brief as B
from . import config as C
from . import ledger as L
from . import transcript as T
from .store import Store

PTR = re.compile(r"^(?P<conv>[0-9a-zA-Z_\-]+)#(?P<step>\d+)$")
ID = re.compile(r"^[0-9a-f]{8}$")


# ------------------------------------------------------------------ helpers
def _ts(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts or 0))


def _since(value):
    if not value:
        return 0
    m = re.fullmatch(r"(\d+)([hdw])", value)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return time.time() - n * {"h": 3600, "d": 86400, "w": 604800}[unit]
    return datetime.datetime.fromisoformat(value).timestamp()


def _clip(text, n):
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return text if len(text) <= n else text[:n] + f" …[+{len(text) - n} chars]"


def _one_line(text, n=160):
    return _clip(" ".join(str(text).split()), n)


class Ctx:
    def __init__(self, args):
        self.store = Store(args.root, C.load(args.root)["redactPatterns"]).ensure()
        self.cfg = C.load(args.root)
        cur = self.store.load_json("state", "current.json")
        self.conv = getattr(args, "conv", None) or cur.get("convId") or "manual"

    def ledger(self):
        return self.store.read("ledger.jsonl")

    def transcript_for(self, conv):
        st = self.store.conv_state(conv)
        cands = [st.get("transcriptPath"),
                 os.path.expanduser(f"~/.gemini/antigravity/brain/{conv}/.system_generated/logs/"
                                    "transcript_full.jsonl")]
        return next((p for p in cands if p and os.path.exists(p)), None)


def _find(entries, item_id):
    view = L.current_view(entries)
    for e in view:
        if e["id"] == item_id or item_id in {h["id"] for h in L.history(entries, e["id"])}:
            return e
    return None


# ------------------------------------------------------------------ commands
def cmd_add(c, a):
    if a.type == "fact" and not a.source:
        print("warning: facts should carry --source (e.g. <conv>#<step> or file:path)",
              file=sys.stderr)
    text = " ".join(a.text)
    e = L.new_entry(a.type, text, c.conv, a.source or [])
    c.store.append("ledger.jsonl", e)
    print(f"added [{e['id']}] {a.type}: {text}")


def cmd_status(c, a, status):
    entries = c.ledger()
    for item in a.ids:
        e = _find(entries, item)
        if not e:
            print(f"no such entry: {item}", file=sys.stderr)
            continue
        new = L.status_update(e, status, c.conv)
        c.store.append("ledger.jsonl", new)
        entries.append(new)
        print(f"[{e['id']}] -> {status} (new id {new['id']})")


def cmd_supersede(c, a):
    entries = c.ledger()
    e = _find(entries, a.id)
    if not e:
        sys.exit(f"no such entry: {a.id}")
    new = L.new_entry(e["type"], " ".join(a.text), c.conv,
                      a.source or e.get("source") or [], supersedes=e["id"])
    c.store.append("ledger.jsonl", new)
    print(f"[{e['id']}] superseded by [{new['id']}] {e['type']}: {new['text']}")


def cmd_brief(c, a):
    out = B.render(c.ledger(), c.conv, a.max_tokens or c.cfg["briefMaxTokens"])
    print(out or "(memory ledger is empty)")


def cmd_show(c, a):
    target = a.target
    entries = c.ledger()
    if target in L.TYPES or target == "all":
        view = [e for e in L.current_view(entries)
                if (target == "all" or e["type"] == target)
                and (a.all_status or e.get("status") == "active")]
        for e in view:
            src = f"  src: {', '.join(e['source'])}" if e.get("source") else ""
            print(f"[{e['id']}] ({e['type']}, {e.get('status')}, {_ts(e['ts'])}, conv {e.get('convId')}) "
                  f"{e['text']}{src}")
        if not view:
            print("(none)")
        return
    if ID.match(target):
        hist = L.history(entries, target)
        if not hist:
            sys.exit(f"no such entry: {target}")
        for e in hist:
            print(f"[{e['id']}] {_ts(e['ts'])} {e['type']} {e.get('status')} conv={e.get('convId')}"
                  f" src={e.get('source')}\n    {e['text']}")
        return
    m = PTR.match(target)
    if m:
        conv, step = m.group("conv"), int(m.group("step"))
        s = _step_from_any(c, conv, step)
        if not s:
            sys.exit(f"step {target} not found (transcript and archive)")
        body = {k: s[k] for k in ("source", "type", "content", "tool_calls", "thinking") if k in s}
        print(f"{target} {s.get('created_at', '')}")
        for k, v in body.items():
            print(f"--- {k}\n{_clip(v, a.max_chars)}")
        return
    sys.exit("target must be an entry id, a type (constraint|decision|progress|fact|open|all), "
             "or a pointer <conv>#<step>")


def _step_from_any(c, conv, step):
    tp = c.transcript_for(conv)
    s = T.find_step(tp, step) if tp else None
    if s:
        return s
    arc = c.store.path("archive", f"{conv}.jsonl.gz")
    if os.path.exists(arc):
        with gzip.open(arc, "rt", encoding="utf-8", errors="replace") as f:
            for line in f:
                if f'"step_index":{step},' in line or f'"step_index": {step},' in line:
                    try:
                        s = json.loads(line)
                    except ValueError:
                        continue
                    if s.get("step_index") == step:
                        return s
    return None


def _event_text(e):
    d = e.get("data") or {}
    k = e["kind"]
    if k == "user_input":
        return d.get("text", "")
    if k == "file_edit":
        return f"{d.get('tool')} {d.get('path')}" + (f" ERROR {d['error']}" if d.get("error") else "")
    if k == "command":
        return f"$ {d.get('cmd')}" + (f"  ERROR {d['error']}" if d.get("error") else "")
    if k == "compaction":
        return f"signal={d.get('signal')} peak={d.get('peak')} " + (d.get("summary") or "")
    if k == "turn_end":
        return f"reason={d.get('reason')} changed={d.get('gitChanged')}"
    return json.dumps(d, ensure_ascii=False)


def cmd_search(c, a):
    terms = [t.lower() for t in a.query]
    since = _since(a.since)
    hits = []

    def match(text):
        low = text.lower()
        return all(t in low for t in terms)

    if a.where in ("all", "ledger"):
        for e in c.ledger():
            if e["ts"] >= since and (not a.type or e["type"] == a.type) and match(e["text"]):
                hits.append((e["ts"], f"ledger [{e['id']}] {e['type']}/{e.get('status')}", e["text"]))
    if a.where in ("all", "events"):
        for e in c.store.read("events.jsonl"):
            if e["ts"] < since or (a.type and e["kind"] != a.type):
                continue
            text = _event_text(e)
            if match(text):
                ptr = f"{e['convId']}#{e['step']}" if e.get("step") is not None else e["convId"]
                hits.append((e["ts"], f"event {e['kind']} @ {ptr}", text))
    if a.where in ("all", "archive"):
        for arc in glob.glob(c.store.path("archive", "*.jsonl.gz")):
            if os.path.getmtime(arc) < since:
                continue
            conv = os.path.basename(arc)[: -len(".jsonl.gz")]
            with gzip.open(arc, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not match(line):
                        continue
                    try:
                        s = json.loads(line)
                    except ValueError:
                        continue
                    text = s.get("content") or json.dumps(s.get("tool_calls"), ensure_ascii=False)
                    hits.append((0, f"transcript {conv}#{s.get('step_index')} {s.get('type')}",
                                 str(text)))
    hits.sort(key=lambda h: h[0], reverse=True)
    for ts, where, text in hits[: a.limit]:
        print(f"{_ts(ts) if ts else '                '}  {where}\n    {_snippet(text, terms)}")
    print(f"({len(hits)} hits{', showing ' + str(a.limit) if len(hits) > a.limit else ''})")


def _snippet(text, terms, width=200):
    flat = " ".join(str(text).split())
    i = flat.lower().find(terms[0]) if terms else 0
    start = max(0, i - width // 3)
    return ("…" if start else "") + flat[start:start + width] + ("…" if len(flat) > start + width else "")


def cmd_timeline(c, a):
    since = _since(a.since)
    rows = []
    for e in c.store.read("events.jsonl"):
        if e["ts"] < since or (a.conv_only and e.get("convId") != c.conv):
            continue
        if e["kind"] in ("intro", "checkpoint_nudge", "align_nudge", "stop_nudge") and not a.verbose:
            continue
        text = _event_text(e)
        if a.file and a.file not in text:
            continue
        rows.append((e["ts"], f"{e['kind']:<11}", text))
    for e in c.ledger():
        if e["ts"] >= since and (not a.file or a.file in e["text"]) \
                and (not a.conv_only or e.get("convId") == c.conv):
            rows.append((e["ts"], f"ledger:{e['type'][:4]}", f"[{e['id']}] {e.get('status')} {e['text']}"))
    rows.sort(key=lambda r: r[0])
    for ts, kind, text in rows[-a.limit:]:
        print(f"{_ts(ts)}  {kind}  {_one_line(text)}")
    if not rows:
        print("(no events)")


def cmd_session(c, a):
    if a.id:
        path = c.store.path("sessions", f"{a.id}.md")
        if not os.path.exists(path):
            sys.exit(f"no session index for {a.id}")
        with open(path, encoding="utf-8") as f:
            print(f.read())
        return
    rows = []
    for p in glob.glob(c.store.path("state", "*.json")):
        conv = os.path.basename(p)[:-5]
        if conv in ("current", "models"):
            continue
        st = c.store.load_json("state", f"{conv}.json")
        rows.append((st.get("lastSeen") or 0, conv, st))
    for last, conv, st in sorted(rows, reverse=True):
        mark = " *" if conv == c.conv else ""
        print(f"{conv}{mark}  last {_ts(last)}  compactions {st.get('compactions', 0)}  "
              f"files {len(st.get('files') or [])}  — {_one_line(st.get('firstUserInput') or '', 80)}")
    if not rows:
        print("(no sessions recorded yet)")


def cmd_doctor(c, a):
    ok = True

    def check(cond, msg, hint=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'ok' if cond else 'FAIL'}] {msg}" + (f"\n       -> {hint}" if not cond and hint else ""))

    check(sys.version_info >= (3, 9), f"python {sys.version.split()[0]}", "need Python 3.9+")
    check(os.access(c.store.root, os.W_OK), f"store writable: {c.store.root}")
    cur = c.store.load_json("state", "current.json")
    age = time.time() - cur.get("ts", 0)
    check(cur, "hooks have run in this project",
          "no state/current.json: is the agy-memory plugin enabled?")
    if cur:
        print(f"       last hook {int(age)}s ago, conversation {cur.get('convId')}, model {cur.get('model')}")
    ev = c.store.read("events.jsonl")
    kinds = {}
    for e in ev:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    print(f"[info] events: {kinds or 'none'}")
    print(f"[info] ledger entries: {len(c.ledger())}; learned compaction peaks: "
          f"{c.store.load_json('state', 'models.json') or 'none yet'}")
    tp = c.transcript_for(c.conv)
    check(tp, f"transcript readable for current conversation: {tp}",
          "compaction detection needs read access to the transcript")
    log = os.path.expanduser("~/.agy-memory/hook-errors.log")
    if os.path.exists(log):
        with open(log, encoding="utf-8", errors="replace") as f:
            tail = f.read()[-600:]
        print(f"[warn] hook errors logged in {log}:\n{tail}")
    sys.exit(0 if ok else 1)


# ------------------------------------------------------------------ parser
def build_parser():
    p = argparse.ArgumentParser(prog="mem", description="agy-memory CLI")
    p.add_argument("--root", required=True, help="memory store (.agy-memory); set by the shim")
    p.add_argument("--conv", help="conversation id (default: the one hooks saw last)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add", help="append a ledger entry")
    s.add_argument("type", choices=L.TYPES)
    s.add_argument("text", nargs="+")
    s.add_argument("--source", action="append", help="pointer: <conv>#<step> or file:<path>")

    for name in ("done", "drop"):
        s = sub.add_parser(name, help="mark entries done" if name == "done" else "retire entries")
        s.add_argument("ids", nargs="+")

    s = sub.add_parser("supersede", help="replace an entry with a corrected version")
    s.add_argument("id")
    s.add_argument("text", nargs="+")
    s.add_argument("--source", action="append")

    s = sub.add_parser("brief", help="print the memory brief for this session")
    s.add_argument("--max-tokens", type=int)

    s = sub.add_parser("show", help="entry id | type | all | <conv>#<step>")
    s.add_argument("target")
    s.add_argument("--all-status", action="store_true", help="include done/superseded")
    s.add_argument("--max-chars", type=int, default=4000)

    s = sub.add_parser("search", help="keyword search across ledger, events, archived transcripts")
    s.add_argument("query", nargs="+")
    s.add_argument("--where", choices=("all", "ledger", "events", "archive"), default="all")
    s.add_argument("--type", help="ledger type or event kind")
    s.add_argument("--since", help="e.g. 3d, 12h, 2026-11-01")
    s.add_argument("--limit", type=int, default=20)

    s = sub.add_parser("timeline", help="chronological events and ledger changes")
    s.add_argument("--since")
    s.add_argument("--file", help="only lines mentioning this path fragment")
    s.add_argument("--conv-only", action="store_true")
    s.add_argument("--verbose", action="store_true")
    s.add_argument("--limit", type=int, default=60)

    s = sub.add_parser("session", help="list sessions or show one session index")
    s.add_argument("id", nargs="?")

    sub.add_parser("doctor", help="self-check")
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    c = Ctx(a)
    {
        "add": cmd_add,
        "done": lambda c, a: cmd_status(c, a, "done"),
        "drop": lambda c, a: cmd_status(c, a, "superseded"),
        "supersede": cmd_supersede,
        "brief": cmd_brief,
        "show": cmd_show,
        "search": cmd_search,
        "timeline": cmd_timeline,
        "session": cmd_session,
        "doctor": cmd_doctor,
    }[a.cmd](c, a)
