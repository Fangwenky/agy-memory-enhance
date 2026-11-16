"""Configuration defaults and loading. See design doc §10."""
import json
import os

DEFAULTS = {
    "softLimitRatio": 0.75,
    "defaultSoftLimitTokens": 150000,
    "nudgeStepTokens": 30000,
    "compactionDropRatio": 0.4,
    "minPeakTokens": 60000,
    "briefMaxTokens": 1500,
    "sessionInjectBudgetTokens": 6000,
    "stopNudge": True,
    "stopNudgeEdits": 5,
    "archiveTranscripts": True,
    "editToolNames": ["write_file", "edit_file"],
    "redactPatterns": [
        r"(?i)(api[_-]?key|secret|token|password)(\s*[:=]\s*)\S+",
        r"sk-[A-Za-z0-9_\-]{16,}",
        r"gh[pousr]_[A-Za-z0-9]{20,}",
    ],
}


def load(root):
    cfg = dict(DEFAULTS)
    path = os.path.join(root, "config.json")
    try:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    except (OSError, ValueError):
        pass
    return cfg
