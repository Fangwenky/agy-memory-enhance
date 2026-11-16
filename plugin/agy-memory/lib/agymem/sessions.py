"""Session index (sessions/<conv>.md) and incremental transcript archive."""
import gzip
import os
import time

from . import ledger as L


def _t(ts):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "?"


def write_index(store, conv, state):
    entries = [e for e in L.current_view(store.read("ledger.jsonl")) if e.get("convId") == conv]
    lines = [
        f"# Session {conv}",
        "",
        f"- First seen: {_t(state.get('firstSeen'))}",
        f"- Last active: {_t(state.get('lastSeen'))}",
        f"- Model: {state.get('model') or '?'}",
        f"- Compactions: {state.get('compactions', 0)}",
        f"- Transcript: {state.get('transcriptPath') or '?'}",
        "",
        "## First request",
        "",
        (state.get("firstUserInput") or "(unknown)").strip(),
        "",
        f"## Files edited ({len(state.get('files') or [])})",
        "",
    ]
    lines += [f"- {p}" for p in (state.get("files") or [])] or ["(none)"]
    lines += ["", "## Ledger entries written in this session", ""]
    lines += [f"- [{e['id']}] ({e['type']}, {e.get('status')}) {e['text']}" for e in entries] \
        or ["(none)"]
    store_path = store.path("sessions", f"{conv}.md")
    with open(store_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return store_path


def archive_increment(store, conv, state, transcript_path):
    """Append newly written transcript bytes as one gzip member (members concatenate)."""
    if not transcript_path:
        return 0
    try:
        size = os.path.getsize(transcript_path)
    except OSError:
        return 0
    off = state.get("archiveOffset", 0)
    if size < off:  # transcript rewritten: start a new segment
        off = 0
    if size == off:
        return 0
    with open(transcript_path, "rb") as f:
        f.seek(off)
        data = f.read(size - off)
    end = data.rfind(b"\n")
    if end < 0:
        return 0
    data = data[: end + 1]
    with open(store.path("archive", f"{conv}.jsonl.gz"), "ab") as out:
        out.write(gzip.compress(data))
    state["archiveOffset"] = off + len(data)
    return len(data)
