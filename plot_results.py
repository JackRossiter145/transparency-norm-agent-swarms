"""PILOT ANALYSIS ONLY (results/*.jsonl from the 6-agent pilot). For the main experiment use analyze_main.py.

Aggregate episode logs and plot transparency toward the human overseer over time.

  left column  - CONTAGION:  do swarm members' overseer reports degrade when the opaque agent is present?
  right column - CONVERSION: do the newcomer's overseer reports become more transparent over time?
  colour = newcomer persona, line style = channel (solid: shared report log, dashed: private reports)

Usage: python plot_results.py [results_dir] [--tag TAG]
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

COLORS = {"control": "#4C78A8", "neutral": "#9D9D9D", "opaque": "#E45756", "opaque_advocate": "#B279A2"}
STYLES = {"shared": "-", "private": "--"}
METRICS = [
    ("legibility", "Legibility (0-10)", 10),
    ("faithfulness", "Faithfulness (0-10)", 10),
    ("candor", "Candor (0-10)", 10),
    ("report_fact_coverage", "Own new facts in report", 1),
]


def load(d: Path, tag: str):
    records, summaries = [], []
    for f in sorted(d.glob("*.jsonl")):
        if tag and f"_{tag}_" not in f.name:
            continue
        for line in f.open():
            rec = json.loads(line)
            (summaries if rec["type"] == "summary" else records).append(rec)
    return records, summaries


def mean_se(xs):
    xs = np.array([x for x in xs if x is not None], dtype=float)
    if len(xs) == 0:
        return np.nan, np.nan
    return xs.mean(), (xs.std(ddof=1) / np.sqrt(len(xs)) if len(xs) > 1 else 0.0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dir", nargs="?", default="results")
    p.add_argument("--tag", default="")
    a = p.parse_args()
    d = Path(a.dir)
    records, summaries = load(d, a.tag)
    if not records:
        raise SystemExit(f"no episode logs in {d}/")

    inject = summaries[0]["config"]["inject_round"]
    groups = sorted({(r["channel"], r["condition"]) for r in records}, key=lambda g: (g[0], list(COLORS).index(g[1])))

    # Average within (episode, role, round) first so each episode counts once, then across episodes (seeds).
    per_ep = defaultdict(list)
    for r in records:
        for m, _, _ in METRICS:
            v = r.get(m)
            if v is not None:
                per_ep[(m, r["channel"], r["condition"], r["role"], r["round"], r["seed"])].append(float(v))
    agg = defaultdict(list)
    for (m, ch, c, role, rnd, _), vals in per_ep.items():
        agg[(m, ch, c, role, rnd)].append(float(np.mean(vals)))

    fig, axes = plt.subplots(len(METRICS), 2, figsize=(11, 3 * len(METRICS)), sharex=True)
    for i, (m, label, top) in enumerate(METRICS):
        for j, (role, title) in enumerate([("swarm", "Swarm members (contagion?)"), ("newcomer", "Newcomer (conversion?)")]):
            ax = axes[i, j]
            for ch, c in groups:
                rounds = sorted(k[4] for k in agg if k[:4] == (m, ch, c, role))
                if not rounds:
                    continue
                ms = np.array([mean_se(agg[(m, ch, c, role, rr)]) for rr in rounds])
                x = np.array(rounds) + 1
                ax.plot(x, ms[:, 0], STYLES[ch], marker="o", color=COLORS[c], label=f"{c} / {ch}", ms=4)
                ax.fill_between(x, ms[:, 0] - ms[:, 1], ms[:, 0] + ms[:, 1], color=COLORS[c], alpha=0.12)
            ax.axvline(inject + 1, ls=":", color="k", lw=0.8)
            ax.set_ylim(0, top * 1.05)
            if i == 0:
                ax.set_title(title)
            if j == 0:
                ax.set_ylabel(label)
            if i == len(METRICS) - 1:
                ax.set_xlabel("Round (dotted line = newcomer joins)")
            ax.grid(alpha=0.3)
    axes[0, 1].legend(title="newcomer / channel", fontsize=8)
    fig.tight_layout()
    out = d / (f"summary_{a.tag}.png" if a.tag else "summary.png")
    fig.savefig(out, dpi=150)
    print(f"saved {out}\n")

    # Post-injection means, per role.
    short = ["leg", "faith", "cand", "facts"]
    hdr = " ".join(f"{s:>6s}" for s in short)
    print(f"{'channel':8s} {'newcomer':16s} {'n':>3s} {'acc':>5s} | swarm: {hdr} | newcomer: {hdr} confess")
    for ch, c in groups:
        ss = [s for s in summaries if s["condition"] == c and s["channel"] == ch]
        acc = np.mean([s["correct"] for s in ss])
        post = [r for r in records if r["condition"] == c and r["channel"] == ch and r["round"] >= inject]
        row = []
        for role in ["swarm", "newcomer"]:
            row.append(" ".join(f"{mean_se([r.get(m) for r in post if r['role'] == role])[0]:6.2f}" for m, _, _ in METRICS))
        conf = [r["confesses"] for r in post if r.get("confesses") is not None]
        conf_s = f"{np.mean(conf):7.2f}" if conf else "      -"
        print(f"{ch:8s} {c:16s} {len(ss):3d} {acc:5.2f} | swarm: {row[0]} | newcomer: {row[1]} {conf_s}")


if __name__ == "__main__":
    main()
