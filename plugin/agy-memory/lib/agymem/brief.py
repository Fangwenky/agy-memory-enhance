"""Per-conversation brief rendering (design doc §6 简报)."""
import re

from . import ledger as L

_CJK = re.compile(r"[\u3000-\u303f\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uff00-\uffef]")


def est_tokens(text):
    cjk = len(_CJK.findall(text))
    return cjk + (len(text) - cjk + 3) // 4


def _fmt(e, with_src=False):
    s = f"- [{e['id']}] {e['text']}"
    if with_src and e.get("source"):
        s += f" (src: {', '.join(e['source'])})"
    return s


def render(entries, conv, max_tokens=1500, recent_decisions=8):
    view = [e for e in L.current_view(entries) if e.get("status") == "active"]
    constraints = [e for e in view if e["type"] == "constraint"]
    decisions = [e for e in view if e["type"] == "decision"][-recent_decisions:]
    facts = [e for e in view if e["type"] == "fact"]
    mine = [e for e in view if e["type"] in L.SESSION_TYPES and e.get("convId") == conv]
    others = {}
    for e in view:
        if e["type"] in L.SESSION_TYPES and e.get("convId") != conv:
            others.setdefault(e.get("convId"), e)

    # sections in truncation priority order (highest first)
    sections = [
        ("Constraints (must follow)", [_fmt(e) for e in constraints]),
        ("This session: progress / open questions",
         [_fmt(e).replace("- [", f"- ({e['type']}) [", 1) for e in mine]),
        ("Decisions", [_fmt(e) for e in decisions]),
        ("Facts (verify against source before use)", [_fmt(e, True) for e in facts]),
    ]
    if others:
        sections.append(("Other sessions with unfinished work", [
            f"- {cid}: {e['text'][:60]} (`mem session {cid}`)" for cid, e in others.items()]))

    if not any(lines for _, lines in sections):
        return ""

    budget = max_tokens
    out, truncated = [], False
    for title, lines in sections:
        if not lines:
            continue
        head = f"### {title}"
        if est_tokens(head) + est_tokens(lines[0]) > budget:
            truncated = True
            break
        out.append(head)
        budget -= est_tokens(head)
        for ln in lines:
            t = est_tokens(ln)
            if t > budget:
                truncated = True
                break
            out.append(ln)
            budget -= t
        if truncated:
            break
    if truncated:
        out.append("…(truncated; run `mem show <type>` for the full list)")
    return "\n".join(out)
