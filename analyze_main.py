"""Analysis for the main experiment (results/main). Pre-registered comparisons:

  H1 protection     - aligned vs unaligned swarm: drop in candor / fact coverage at k = 1
  H2 tipping point  - swarm candor / fact coverage vs advocate share (aligned arm)
  H3 whistleblowing - rate at which swarm reports alert the overseer to the pressure (k >= 1 vs k = 0 baseline)
  H4 suppression    - does whistleblowing fall off at a lower advocate share than candor does?

All swarm metrics use swarm agents only, rounds from injection onward. Effects are paired
differences vs k = 0 within the same swarm type and seed (identical task information).

Usage:
  python analyze_main.py [results/main]
  # Figure 1: 0-10 judge scores from the Qwen re-judged sample, everything else from the full data
  python analyze_main.py results/main --scores-from results/rejudge_qwen3.8-27b/judge2 \
      --scores-label "Qwen judge" --out figure1.png
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

SWARM_METRICS = [
    ("candor", "Candor (0-10)", 10),
    ("report_fact_coverage", "Own new facts in report", 1),
    ("whistleblows", "Whistleblowing rate", 1),
    ("pushback", "Chat pushback rate", 1),
    ("legibility", "Legibility (0-10)", 10),
    ("faithfulness", "Faithfulness (0-10)", 10),
    ("agree", "Chat agreement rate", 1),
]
JUDGE_SCORES = ("candor", "legibility", "faithfulness")  # the 0-10 scales that --scores-from replaces
STYLE = {"aligned": dict(color="#4C78A8", ls="-"), "unaligned": dict(color="#E45756", ls="--")}


DEFAULT_SEEDS = "0-9"  # the paper's main results use the original 10 seeds; 10-19 are a follow-up replication


def parse_seeds(spec: str) -> set[int]:
    """'0-9' -> {0..9};  '0-4,10-12' -> {0..4, 10..12};  '3' -> {3}."""
    out = set()
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        out |= set(range(int(lo), int(hi or lo) + 1))
    return out


def load(d: Path, seeds: set[int] | None = None):
    """Message records and episode summaries in d, optionally restricted to the given seeds."""
    recs, sums = [], []
    for f in sorted(d.glob("*.jsonl")):
        for line in f.open():
            r = json.loads(line)
            if seeds is not None and r["seed"] not in seeds:
                continue
            (sums if r["type"] == "summary" else recs).append(r)
    return recs, sums


def value(r, m):
    if m == "pushback":
        return None if r.get("stance") is None else float(r["stance"] == "pushback")
    if m == "agree":
        return None if r.get("stance") is None else float(r["stance"] == "agree")
    v = r.get(m)
    return None if v is None else float(v)


def mse(xs):
    xs = np.array([x for x in xs if x is not None and not np.isnan(x)], dtype=float)
    if len(xs) == 0:
        return np.nan, np.nan, 0
    se = xs.std(ddof=1) / np.sqrt(len(xs)) if len(xs) > 1 else 0.0
    return xs.mean(), se, len(xs)


def episode_means(recs, inject):
    """(swarm_type, k, seed) -> metric -> mean over post-injection messages, for swarm agents (E)
    and newcomers (N)."""
    ep = defaultdict(lambda: defaultdict(list))
    ep_new = defaultdict(lambda: defaultdict(list))
    for r in recs:
        if r["round"] < inject:
            continue
        key = (r["swarm_type"], r["n_advocates"], r["seed"])
        target = ep if r["role"] == "swarm" else ep_new
        for m, _, _ in SWARM_METRICS:
            v = value(r, m)
            if v is not None:
                target[key][m].append(v)
        if r["role"] == "newcomer" and r.get("confesses") is not None:
            ep_new[key]["confesses"].append(float(r["confesses"]))
    E = {k: {m: np.mean(v) for m, v in ms.items()} for k, ms in ep.items()}
    N = {k: {m: np.mean(v) for m, v in ms.items()} for k, ms in ep_new.items()}
    return E, N


def main():
    p = argparse.ArgumentParser()
    p.add_argument("dir", nargs="?", default="results/main")
    p.add_argument("--scores-from", default=None,
                   help="take the 0-10 judge scores (candor, legibility, faithfulness) from this re-judged dir")
    p.add_argument("--scores-label", default="second judge")
    p.add_argument("--out", default="main_results.png", help="filename (relative to dir) or absolute path")
    p.add_argument("--seeds", default=DEFAULT_SEEDS, help="seeds to include, e.g. 0-9 (default), 10-19, 0-19")
    a = p.parse_args()
    d = Path(a.dir)
    seeds = parse_seeds(a.seeds)
    recs, sums = load(d, seeds)
    print(f"seeds: {a.seeds}")
    if not recs:
        raise SystemExit(f"no episodes in {d}/")
    cfg = sums[0]["config"]
    inject, G = cfg["inject_round"], cfg["group_size"]

    E, N = episode_means(recs, inject)
    if a.scores_from:
        E2, N2 = episode_means(load(Path(a.scores_from), seeds)[0], inject)
        for key in E:
            for m in JUDGE_SCORES:
                E[key][m] = E2.get(key, {}).get(m, np.nan)
        for key in N:
            N[key]["candor"] = N2.get(key, {}).get("candor", np.nan)
        print(f"NOTE: candor/legibility/faithfulness (swarm + newcomer) from {a.scores_from} ({a.scores_label}); "
              f"all other metrics from {d}")

    cells = sorted({(s, k) for s, k, _ in E}, key=lambda c: (c[0] != "aligned", c[1]))
    seeds = lambda s, k: sorted(sd for (ss, kk, sd) in E if (ss, kk) == (s, k))
    acc = defaultdict(list)
    for s in sums:
        acc[(s["swarm_type"], s["n_advocates"])].append(float(s["correct"]))

    # ---- Table 1: cell means ----
    cols = ["candor", "report_fact_coverage", "whistleblows", "pushback", "agree", "legibility", "faithfulness"]
    short = ["cand", "facts", "whistle", "push", "agree", "legib", "faith"]
    print(f"\nCELL MEANS (swarm agents, rounds {inject + 1}+; mean over episodes)")
    print(f"{'swarm':9s} {'k':>2s} {'share':>5s} {'n':>3s} {'acc':>4s} | " + " ".join(f"{c:>7s}" for c in short)
          + " | newcomer cand  confess")
    for s, k in cells:
        sd = seeds(s, k)
        row = " ".join(f"{mse([E[(s, k, x)].get(m, np.nan) for x in sd])[0]:7.2f}" for m in cols)
        nc = mse([N.get((s, k, x), {}).get("candor", np.nan) for x in sd])[0]
        cf = mse([N.get((s, k, x), {}).get("confesses", np.nan) for x in sd])[0]
        print(f"{s:9s} {k:2d} {k / G:5.0%} {len(sd):3d} {np.mean(acc[(s, k)]):4.2f} | {row} | {nc:13.2f} {cf:8.2f}")

    # ---- Table 2: paired effects vs k = 0 ----
    print("\nPAIRED EFFECTS vs k=0 (same swarm type & seed): mean diff ± SE  [seeds with diff < 0 / n]")
    for s, k in cells:
        if k == 0:
            continue
        parts = []
        for m, lab in [("candor", "cand"), ("report_fact_coverage", "facts"), ("legibility", "legib"), ("faithfulness", "faith")]:
            diffs = [E[(s, k, x)][m] - E[(s, 0, x)][m] for x in seeds(s, k) if (s, 0, x) in E and m in E[(s, k, x)]]
            mu, se, n = mse(diffs)
            neg = sum(np.array(diffs) < 0)
            parts.append(f"{lab} {mu:+.2f}±{se:.2f} [{neg}/{n}]")
        print(f"{s:9s} k={k}: " + " | ".join(parts))

    # ---- H1: aligned vs unaligned drop at k = 1 ----
    print("\nH1 (protection): drop at k=1 vs k=0, aligned minus unaligned")
    for m in ["candor", "report_fact_coverage"]:
        drops = {}
        for s in ["aligned", "unaligned"]:
            drops[s] = [E[(s, 1, x)][m] - E[(s, 0, x)][m] for x in seeds(s, 1) if (s, 0, x) in E]
        al, un = mse(drops["aligned"]), mse(drops["unaligned"])
        print(f"  {m:22s} aligned {al[0]:+.2f}±{al[1]:.2f}   unaligned {un[0]:+.2f}±{un[1]:.2f}   "
              f"difference {al[0] - un[0]:+.2f} (SE {np.hypot(al[1], un[1]):.2f})")

    # ---- Figure ----
    fig, axes = plt.subplots(2, 4, figsize=(16, 7.5))
    axes = axes.ravel()
    for ax, (m, label, top) in zip(axes, SWARM_METRICS):
        for s in ["aligned", "unaligned"]:
            ks = sorted(k for ss, k in cells if ss == s)
            if not ks:
                continue
            st = np.array([mse([E[(s, k, x)].get(m, np.nan) for x in seeds(s, k)])[:2] for k in ks])
            ax.errorbar(np.array(ks) / G * 100, st[:, 0], yerr=st[:, 1], marker="o", capsize=3, label=s, **STYLE[s])
        ax.set_title(f"{label} [{a.scores_label}]" if a.scores_from and m in JUDGE_SCORES else label)
        ax.set_ylim(-0.03 * top, top * 1.05)
        ax.set_xlabel("Advocates (% of group)")
        ax.grid(alpha=0.3)
    axes[0].legend(title="swarm")

    # H4 panel: aligned candor change vs whistleblowing, same x-axis.
    ax = axes[7]
    ks = sorted(k for s, k in cells if s == "aligned")
    if 0 in ks:
        dc = [mse([E[("aligned", k, x)]["candor"] - E[("aligned", 0, x)]["candor"]
                   for x in seeds("aligned", k) if ("aligned", 0, x) in E]) for k in ks]
        wb = [mse([E[("aligned", k, x)].get("whistleblows", np.nan) for x in seeds("aligned", k)]) for k in ks]
        x = np.array(ks) / G * 100
        ax.errorbar(x, [c[0] for c in dc], yerr=[c[1] for c in dc], marker="o", capsize=3, color="#4C78A8",
                    label="candor change vs k=0")
        cl = f"Candor change (points){' [' + a.scores_label + ']' if a.scores_from else ''}"
        ax.set_ylabel(cl, color="#4C78A8")
        ax2 = ax.twinx()
        ax2.errorbar(x, [w[0] for w in wb], yerr=[w[1] for w in wb], marker="s", capsize=3, color="#F58518",
                     label="whistleblowing rate")
        ax2.set_ylabel("Whistleblowing rate", color="#F58518")
        ax2.set_ylim(-0.03, 1.05)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title("H4 (aligned): warning signal vs report quality")
        ax.set_xlabel("Advocates (% of group)")
        ax.grid(alpha=0.3)
    fig.tight_layout()
    out = d / a.out
    fig.savefig(out, dpi=150)
    print(f"\nsaved {out}")


if __name__ == "__main__":
    main()
