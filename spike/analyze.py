#!/usr/bin/env python3
"""Analyze agy-probe output + transcripts and print a markdown report.

Usage: python3 spike/analyze.py [probe_out_dir] [--drop 0.3]
"""
import argparse
import collections
import glob
import json
import os
import re

KEYWORDS = re.compile(r"compact|compress|checkpoint|summar|truncat|压缩|摘要", re.I)


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_bad_line": line[:200]})
    return rows


def ctx_size(step):
    if "input_tokens" not in step:
        return None
    return (step.get("input_tokens") or 0) + (step.get("cache_read_tokens") or 0)


def analyze_conv(probe_file, drop):
    recs = load_jsonl(probe_file)
    conv = os.path.basename(probe_file)[: -len(".jsonl")]
    rep = [f"## 会话 `{conv}`", ""]

    ev = collections.Counter(r.get("event") for r in recs)
    rep.append(f"- hook 事件计数：{dict(ev)}")
    rep.append(f"- SessionStart 次数：{ev.get('SessionStart', 0)}（>1 说明恢复会话会再次触发）")
    tools = collections.Counter(
        (r["payload"].get("toolCall") or {}).get("name")
        for r in recs if r.get("event") == "PostToolUse")
    rep.append(f"- PostToolUse 工具名：{dict(tools)}")
    unread = [r for r in recs if not r.get("transcript", {}).get("readable")]
    rep.append(f"- hook 进程读不到 transcript 的次数：{len(unread)}"
               + (f"（示例错误：{unread[0]['transcript'].get('error')}）" if unread else ""))
    envs = {json.dumps(r.get("env"), sort_keys=True) for r in recs}
    rep.append(f"- hook 环境变量样例：{list(envs)[:1]}")
    rep.append(f"- payload 顶层字段：{sorted({k for r in recs for k in r.get('payload', {})})}")

    # transcript size series from probe records
    sizes = [(r["ts"], r["event"], r["transcript"].get("size")) for r in recs
             if r.get("transcript", {}).get("size") is not None]
    shrinks = [(a, b) for a, b in zip(sizes, sizes[1:]) if b[2] < a[2]]
    rep.append(f"- transcript 文件变小的次数：{len(shrinks)}"
               + (f"，例如 {shrinks[0][0][2]} → {shrinks[0][1][2]} 字节" if shrinks else "（只追加）"))

    tpath = next((r["transcript"]["path"] for r in reversed(recs)
                  if r.get("transcript", {}).get("readable")), None)
    if not tpath or not os.path.exists(tpath):
        rep.append("- 未找到可读的 transcript，跳过 step 分析")
        return "\n".join(rep)
    full = tpath.replace("transcript.jsonl", "transcript_full.jsonl")
    steps = load_jsonl(full if os.path.exists(full) else tpath)
    rep.append(f"- transcript：`{tpath}`，{len(steps)} 步")

    types = collections.Counter((s.get("source"), s.get("type")) for s in steps)
    rep.append(f"- step 类型：{dict((f'{a}/{b}', n) for (a, b), n in types.items())}")

    # context-size curve + drops
    series = [(s.get("step_index"), ctx_size(s)) for s in steps if ctx_size(s) is not None]
    peak = max((c for _, c in series), default=0)
    rep.append(f"- 模型调用 {len(series)} 次，上下文峰值 {peak}")
    drops, run_peak = [], 0
    for idx, c in series:
        if run_peak and c < run_peak * (1 - drop):
            drops.append((idx, run_peak, c))
            run_peak = c
        run_peak = max(run_peak, c)
    rep.append(f"- 上下文骤降（≥{int(drop*100)}%）{len(drops)} 次：")
    for idx, p, c in drops:
        rep.append(f"  - step {idx}：{p} → {c}")
        near = [s for s in steps if s.get("step_index") is not None
                and idx - 4 <= s["step_index"] <= idx]
        for s in near:
            blob = json.dumps(s, ensure_ascii=False)
            kw = sorted(set(m.group(0).lower() for m in KEYWORDS.finditer(blob)))
            rep.append(f"    - step {s.get('step_index')} {s.get('source')}/{s.get('type')}"
                       f" keys={sorted(s.keys())} kw={kw}")

    # step_index continuity
    idxs = [s.get("step_index") for s in steps if isinstance(s.get("step_index"), int)]
    gaps = [(a, b) for a, b in zip(idxs, idxs[1:]) if b != a + 1]
    rep.append(f"- step_index 不连续处：{gaps[:10]}")

    # markers
    markers = [r["injected"] for r in recs if r.get("injected")]
    rep.append("- 注入标记在 transcript 中的位置：")
    for m in markers:
        hits = [s.get("step_index") for s in steps if m in json.dumps(s, ensure_ascii=False)]
        rep.append(f"  - {m}：steps {hits}")

    # keyword scan across non-model steps
    kw_steps = [s for s in steps if s.get("source") == "SYSTEM"
                or s.get("type") not in ("PLANNER_RESPONSE", "GENERIC", "USER_INPUT")]
    rep.append(f"- SYSTEM / 非常规 step：{len(kw_steps)} 个")
    for s in kw_steps[:20]:
        content = str(s.get("content", ""))[:160].replace("\n", " ")
        rep.append(f"  - step {s.get('step_index')} {s.get('source')}/{s.get('type')}：{content}")
    return "\n".join(rep)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default=os.path.expanduser("~/.agy-probe/out"))
    ap.add_argument("--drop", type=float, default=0.3)
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.out, "*.jsonl")))
    print("# agy-probe 分析报告\n")
    if not files:
        print(f"`{a.out}` 下没有探针数据。")
    for f in files:
        print(analyze_conv(f, a.drop))
        print()


if __name__ == "__main__":
    main()
