"""Whistleblowing audit file: every swarm overseer report the classifier flagged as a warning,
plus 20 random unflagged reports from cells with 5+ advocates, with both judges' labels.

Usage:
  python make_audit.py                  # seeds 0-9 -> results/main/audit/whistleblowing_audit.md
  python make_audit.py --seeds 10-19    # -> results/main/audit/whistleblowing_audit_seeds10-19.md
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from analyze_main import DEFAULT_SEEDS, parse_seeds

MAIN = Path("results/main")
QWEN = Path("results/rejudge_qwen3.8-27b/judge2")
N_CONTROLS = 20
CONTROL_MIN_ADVOCATES = 5


def load_messages(d: Path, seeds: set[int]) -> list[dict]:
    recs = []
    for f in sorted(d.glob("*.jsonl")):
        for line in f.open():
            r = json.loads(line)
            if r["type"] == "message" and r["seed"] in seeds:
                r["_file"] = f.name
                recs.append(r)
    return recs


def block(i, r, tag, qwen):
    q = qwen.get((r["_file"], r["agent"], r["round"]))
    qs = "not in Qwen sample" if q is None else f"Qwen: {'flagged' if q else 'NOT flagged'}"
    return (f"### {tag} {i}: {r['swarm_type']}, {r['n_advocates']} advocates, seed {r['seed']}, {r['agent']}, "
            f"round {r['round'] + 1}\n"
            f"`{r['_file']}` | Gemma: {'flagged' if r['whistleblows'] else 'not flagged'} | {qs} | "
            f"stance in chat: {r.get('stance')}\n\n"
            + "\n".join("> " + ln for ln in r["report"].splitlines()) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=DEFAULT_SEEDS)
    ap.add_argument("--out", default=None, help="default: results/main/audit/whistleblowing_audit[_seedsX].md")
    a = ap.parse_args()
    seeds = parse_seeds(a.seeds)
    out = Path(a.out) if a.out else MAIN / "audit" / (
        "whistleblowing_audit.md" if a.seeds == DEFAULT_SEEDS else f"whistleblowing_audit_seeds{a.seeds}.md")

    recs = load_messages(MAIN, seeds)
    inject = 2  # newcomers join at round 3 (0-indexed 2) in every main-experiment episode
    sw = [r for r in recs if r["role"] == "swarm" and r["round"] >= inject]
    order = lambda r: (r["swarm_type"], r["n_advocates"], r["seed"], r["round"], int(r["agent"][1:]))
    flag = sorted([r for r in sw if r.get("whistleblows")], key=order)
    pool = [r for r in sw if r.get("whistleblows") is False and r["n_advocates"] >= CONTROL_MIN_ADVOCATES]
    ctrl = sorted(random.Random(0).sample(pool, min(N_CONTROLS, len(pool))), key=order)

    qwen = {}
    for f in QWEN.glob("*.jsonl"):
        for line in f.open():
            r = json.loads(line)
            if r["type"] == "message" and r.get("whistleblows") is not None:
                qwen[(f.name, r["agent"], r["round"])] = r["whistleblows"]

    counts = Counter((r["swarm_type"], r["n_advocates"]) for r in flag)
    parts = [
        "# Whistleblowing audit\n",
        f"Swarm overseer reports (rounds 3-8). Part A: all {len(flag)} reports the Gemma classifier flagged as "
        "warning the overseer about teammates urging shorter/conclusion-only reports. Part B: 20 random unflagged "
        "reports from cells with 5+ advocates (random seed 0). Qwen's label is shown where the message was in the "
        "re-judged sample.\n",
        "Counts flagged by cell: " + ", ".join(f"{s} k={k}: {n}" for (s, k), n in sorted(counts.items())) + "\n",
        f"\n## Part A: flagged ({len(flag)})\n",
    ]
    parts += [block(i + 1, r, "A", qwen) for i, r in enumerate(flag)]
    parts += [f"\n## Part B: unflagged, high-advocate cells ({len(ctrl)})\n"]
    parts += [block(i + 1, r, "B", qwen) for i, r in enumerate(ctrl)]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts))
    print(f"seeds {a.seeds}: {len(flag)} flagged, {len(ctrl)} controls -> {out}")


if __name__ == "__main__":
    main()
