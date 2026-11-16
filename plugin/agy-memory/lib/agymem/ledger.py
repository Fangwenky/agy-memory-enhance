"""Ledger model (design doc §6 L2). Append-only; updates supersede older ids."""
import time
import uuid

TYPES = ("constraint", "decision", "progress", "fact", "open")
PROJECT_TYPES = ("constraint", "decision", "fact")
SESSION_TYPES = ("progress", "open")
STATUSES = ("active", "done", "superseded")


def new_entry(type_, text, conv, source=(), supersedes=None, status="active"):
    if type_ not in TYPES:
        raise ValueError(f"unknown type {type_!r}; expected one of {TYPES}")
    return {
        "id": uuid.uuid4().hex[:8],
        "ts": time.time(),
        "convId": conv,
        "type": type_,
        "text": text,
        "source": list(source),
        "status": status,
        "supersedes": supersedes,
    }


def status_update(target, status, conv):
    """A status change is itself an entry that supersedes the target."""
    e = dict(target)
    e.update(id=uuid.uuid4().hex[:8], ts=time.time(), status=status,
             supersedes=target["id"], updatedBy=conv)
    return e


def current_view(entries):
    """Latest version of every logical item, in original creation order."""
    superseded = {e.get("supersedes") for e in entries if e.get("supersedes")}
    latest = [e for e in entries if e.get("id") not in superseded]
    # creation order: follow chain back to root to get the original ts
    by_id = {e["id"]: e for e in entries if "id" in e}

    def root_ts(e):
        seen = set()
        while e.get("supersedes") in by_id and e["id"] not in seen:
            seen.add(e["id"])
            e = by_id[e["supersedes"]]
        return e.get("ts", 0)

    return sorted(latest, key=root_ts)


def history(entries, item_id):
    """All versions of the item that `item_id` belongs to, oldest first."""
    by_id = {e["id"]: e for e in entries if "id" in e}
    children = {}
    for e in entries:
        if e.get("supersedes"):
            children[e["supersedes"]] = e
    e = by_id.get(item_id)
    if not e:
        return []
    while e.get("supersedes") in by_id:
        e = by_id[e["supersedes"]]
    chain = [e]
    while chain[-1]["id"] in children:
        chain.append(children[chain[-1]["id"]])
    return chain
