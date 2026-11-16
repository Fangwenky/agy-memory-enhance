#!/usr/bin/env python3
"""Generate a synthetic codebase large enough to force context compaction.

Each module is ~30KB (~8k tokens) and contains one unique "registry key"
plus filler code, so reading all of them pushes context well past 200k tokens.

Usage: python3 gen_workload.py <dir> [--modules 40]
"""
import argparse
import os
import random

WORDS = ("alpha beta gamma delta ledger cursor shard replica quorum lease "
         "fence epoch vector bloom cache index segment wal snapshot").split()


def module(i, rnd):
    key = f"REG_{i:02d}_{rnd.randrange(16**6):06x}"
    lines = [f'"""Module m{i:02d}. Registry key: {key}"""', "",
             f'REGISTRY_KEY = "{key}"', ""]
    n = 0
    while sum(len(x) + 1 for x in lines) < 30_000:
        a, b, c = rnd.sample(WORDS, 3)
        lines += [f"def {a}_{b}_{n}(x, y):",
                  f'    """Combine {a} with {b} using {c} semantics."""',
                  f"    t = (x * {rnd.randint(2, 97)} + y) % {rnd.randint(101, 997)}",
                  f"    return {{'{c}': t, 'src': 'm{i:02d}'}}", ""]
        n += 1
    return key, "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--modules", type=int, default=40)
    a = ap.parse_args()
    rnd = random.Random(42)
    src = os.path.join(a.dir, "src")
    os.makedirs(src, exist_ok=True)
    keys = []
    for i in range(a.modules):
        key, text = module(i, rnd)
        keys.append(key)
        with open(os.path.join(src, f"m{i:02d}.py"), "w") as f:
            f.write(text)
    with open(os.path.join(a.dir, ".answer_keys.txt"), "w") as f:
        f.write("\n".join(keys) + "\n")
    print(f"wrote {a.modules} modules to {src}")


if __name__ == "__main__":
    main()
