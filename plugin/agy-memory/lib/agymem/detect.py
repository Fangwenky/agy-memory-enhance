"""Compaction detection and context-pressure nudges (design doc §7.3).

Pure function: no I/O, so it is easy to test with synthetic step lists.
"""
from . import transcript as T


def fresh_state():
    return {
        "initialized": False,
        "offset": 0,
        "peak": 0,              # max context size since last compaction
        "lastCtx": 0,
        "compactions": 0,
        "pendingAlign": None,   # signal name when an alignment injection is due
        "lastNudgeCtx": None,   # context size at last nudge (this epoch)
        "ledgerSize": 0,        # ledger.jsonl size last time we looked
        "ledgerCtx": None,      # context size when ledger last changed (this epoch)
        "injectedTokens": 0,
        "model": None,
        # bookkeeping for Stop / session index / mem
        "transcriptPath": None,
        "firstSeen": None,
        "lastSeen": None,
        "firstUserInput": None,
        "files": [],
        "editsSinceLedger": 0,
        "archiveOffset": 0,
        "stopNudged": False,
    }


def soft_limit(cfg, model_peak):
    if model_peak:
        return int(cfg["softLimitRatio"] * model_peak)
    return int(cfg["defaultSoftLimitTokens"])


def scan(state, steps, cfg, conv):
    """Update state from new transcript steps. Returns (events, compaction_peaks)."""
    events, peaks = [], []
    for s in steps:
        idx = s.get("step_index")
        if T.is_user_input(s):
            text = T.user_text(s)
            if not state.get("firstUserInput"):
                state["firstUserInput"] = text[:300]
            events.append(("user_input", idx, {"text": text}))
        elif T.is_checkpoint(s):
            events.append(("compaction", idx, {
                "signal": "checkpoint", "peak": state["peak"],
                "summary": s.get("content") or ""}))
            peaks.append(state["peak"])
            _reset_epoch(state, "checkpoint")
        elif T.is_model_call(s):
            c = T.ctx_tokens(s)
            if c is None:
                continue
            p = state["peak"]
            if p >= cfg["minPeakTokens"] and c < p * (1 - cfg["compactionDropRatio"]):
                events.append(("compaction", idx, {"signal": "token_drop", "peak": p, "after": c}))
                peaks.append(p)
                _reset_epoch(state, "token_drop")
            state["peak"] = max(state["peak"], c)
            state["lastCtx"] = c
    return events, peaks


def _reset_epoch(state, signal):
    state["peak"] = 0
    state["lastCtx"] = 0
    state["compactions"] += 1
    state["pendingAlign"] = signal
    state["lastNudgeCtx"] = None
    state["ledgerCtx"] = None


def observe_ledger(state, ledger_size):
    if ledger_size != state["ledgerSize"]:
        state["ledgerSize"] = ledger_size
        state["ledgerCtx"] = state["lastCtx"]
        state["editsSinceLedger"] = 0


def should_nudge(state, cfg, model_peak):
    """One-line nudge when context is high and memory has not been saved recently."""
    c = state["lastCtx"]
    limit = soft_limit(cfg, model_peak)
    if c < limit:
        return None
    marks = [m for m in (state["lastNudgeCtx"], state["ledgerCtx"]) if m is not None]
    if marks:
        gap = cfg["nudgeStepTokens"]
        if not model_peak:
            # threshold unknown for this model: space nudges geometrically (x1.5)
            gap = max(gap, max(marks) // 2)
        if c - max(marks) < gap:
            return None
    state["lastNudgeCtx"] = c
    return {"ctx": c, "limit": limit, "modelPeak": model_peak}
