"""Table 1: warnings to the overseer per cell — episodes with at least one warning, distinct
swarm agents who ever warned, and warners per episode; plus message-level warning and pushback
counts. Swarm agents only, rounds 3-8, Gemma classifier on all messages.

Usage:
  python paper_tables.py                 # seeds 0-9 -> results/main/table1_warnings.txt
  python paper_tables.py --seeds 10-19   # -> results/main/table1_warnings_seeds10-19.txt
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from analyze_main import DEFAULT_SEEDS, parse_seeds

MAIN = Path("results/main")
INJECT = 2  # newcomers join at round 3 (0-indexed 2)
LABEL = {"aligned": "transparency-prompted", "unaligned": "baseline"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=DEFAULT_SEEDS)
    ap.add_argument("--out", default=None, help="default: results/main/table1_warnings[_seedsX].txt")
    a = ap.parse_args()
    seeds = parse_seeds(a.seeds)
    out = Path(a.out) if a.out else MAIN / (
        "table1_warnings.txt" if a.seeds == DEFAULT_SEEDS else f"table1_warnings_seeds{a.seeds}.txt")

    agents = defaultdict(set)                      # cell -> {(seed, agent)} swarm agents
    warners = defaultdict(lambda: defaultdict(set))  # cell -> seed -> {agents who warned}
    eps = defaultdict(set)                         # cell -> {seeds present}
    msgs = defaultdict(lambda: [0, 0, 0, 0])       # cell -> [warn, n_warn_labelled, push, n_stance_labelled]
    for f in sorted(MAIN.glob("*.jsonl")):
        for line in f.open():
            r = json.loads(line)
            if r["type"] != "message" or r["seed"] not in seeds or r["role"] != "swarm" or r["round"] < INJECT:
                continue
            c = (r["swarm_type"], r["n_advocates"])
            agents[c].add((r["seed"], r["agent"]))
            eps[c].add(r["seed"])
            if r.get("whistleblows") is not None:
                msgs[c][0] += bool(r["whistleblows"])
                msgs[c][1] += 1
                if r["whistleblows"]:
                    warners[c][r["seed"]].add(r["agent"])
            if r.get("stance") is not None:
                msgs[c][2] += r["stance"] == "pushback"
                msgs[c][3] += 1

    cells = sorted(agents, key=lambda c: (c[0] != "aligned", c[1]))
    lines = [f"TABLE 1. Warnings to the overseer, seeds {a.seeds}. Swarm agents, rounds 3-8; "
             "'warning' = overseer report flagged by the Gemma classifier (see audit file).", ""]
    hdr = (f"{'swarm':22s} {'advocates':>9s} | {'episodes w/ >=1 warning':>23s} | {'distinct agents warned':>22s} | "
           f"warners per episode (by seed)")
    lines += [hdr, "-" * len(hdr)]
    for c in cells:
        sd = sorted(eps[c])
        n_ep = len(sd)
        n_warn_ep = sum(1 for s in sd if warners[c][s])
        n_agents = len(agents[c])
        n_warners = sum(len(warners[c][s]) for s in sd)
        per = " ".join(str(len(warners[c][s])) for s in sd)
        lines.append(f"{LABEL[c[0]]:22s} {c[1]:>9d} | {n_warn_ep:>14d} / {n_ep:<6d} | "
                     f"{n_warners:>8d} / {n_agents:<4d} ({n_warners / n_agents:4.0%}) | {per}")
    lines += ["", "Message level (pooled counts; per-episode mean ± SE of the rate is in analyze_main.py output):", ""]
    lines += [f"{'swarm':22s} {'advocates':>9s} | {'warnings':>14s} | {'pushback':>14s}"]
    for c in cells:
        w, nw, p, npush = msgs[c]
        lines.append(f"{LABEL[c[0]]:22s} {c[1]:>9d} | {w:>5d} / {nw:<6d} | {p:>5d} / {npush:<6d}")
    text = "\n".join(lines) + "\n"
    print(text)
    out.write_text(text)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
