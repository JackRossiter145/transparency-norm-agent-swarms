"""Paper figures.

Figure 1 (one row, three panels = the paper's three claims):
  (a) Candor      - Qwen judge (re-judged sample), y-axis zoomed
  (b) Fact coverage - objective string match, all messages
  (c) Warnings & pushback - transparency-prompted swarm only (baseline ~0, stated in caption)
Appendix figure: legibility and faithfulness (Qwen judge).

Also prints the numbers quoted in the captions/text.

Usage:
  python make_figures.py                      # paper figures, seeds 0-9, written to results/main
  python make_figures.py --seeds 10-19 --out-dir <dir>
"""

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from analyze_main import DEFAULT_SEEDS, episode_means, load, mse, parse_seeds

MAIN = Path("results/main")
QWEN = Path("results/rejudge_qwen3.8-27b/judge2")
CANDOR_YLIM = (2, 7)

COL = {"aligned": "#4C78A8", "unaligned": "#E45756"}
LS = {"aligned": "-", "unaligned": "--"}
MK = {"aligned": "o", "unaligned": "s"}
# Display names (the data and code keep "aligned"/"unaligned" as condition keys).
LABEL = {"aligned": "Transparency-prompted", "unaligned": "Baseline"}

plt.rcParams.update({
    "font.size": 13, "axes.titlesize": 14, "axes.labelsize": 13,
    "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12,
})


def series(E, G, swarm, metric):
    ks = sorted({k for s, k, _ in E if s == swarm})
    pts = [mse([E[(swarm, k, sd)].get(metric, np.nan) for (s, kk, sd) in E if (s, kk) == (swarm, k)]) for k in ks]
    return np.array(ks) / G * 100, np.array([p[0] for p in pts]), np.array([p[1] for p in pts])


def style_axis(ax, ticks):
    ax.set_xticks(ticks)
    ax.set_xlabel("Advocates (% of group)")
    ax.grid(alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=DEFAULT_SEEDS, help="seeds to include, e.g. 0-9 (default), 10-19")
    ap.add_argument("--out-dir", default=str(MAIN), help="where to write the figures (default results/main)")
    args = ap.parse_args()
    seeds = parse_seeds(args.seeds)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"seeds: {args.seeds}")
    recs, sums = load(MAIN, seeds)
    cfg = sums[0]["config"]
    inject, G = cfg["inject_round"], cfg["group_size"]
    E, _ = episode_means(recs, inject)                      # full data: facts, whistleblowing, pushback
    Q, _ = episode_means(load(QWEN, seeds)[0], inject)             # Qwen sample: 0-10 judge scores
    ticks = sorted({k / G * 100 for _, k, _ in E})

    # ---------------- Figure 1 ----------------
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.6))
    ax = axes[0]
    for s in ["aligned", "unaligned"]:
        x, y, se = series(Q, G, s, "candor")
        ax.errorbar(x, y, yerr=se, color=COL[s], ls=LS[s], marker=MK[s], capsize=3, lw=2, ms=6, label=LABEL[s])
    ax.set_ylim(*CANDOR_YLIM)
    ax.set_ylabel("Candor (0–10)")
    ax.set_title("(a) Candor")
    ax.legend(title="Swarm", frameon=False, loc="upper right", fontsize=11, title_fontsize=11)
    style_axis(ax, ticks)

    ax = axes[1]
    for s in ["aligned", "unaligned"]:
        x, y, se = series(E, G, s, "report_fact_coverage")
        ax.errorbar(x, y, yerr=se, color=COL[s], ls=LS[s], marker=MK[s], capsize=3, lw=2, ms=6, label=LABEL[s])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Fact coverage")
    ax.set_title("(b) Fact coverage")
    style_axis(ax, ticks)

    ax = axes[2]
    for m, lab, ls, mk in [("whistleblows", "Warns overseer", "-", "o"), ("pushback", "Pushes back", ":", "^")]:
        x, y, se = series(E, G, "aligned", m)
        ax.errorbar(x, y, yerr=se, color=COL["aligned"], ls=ls, marker=mk, capsize=3, lw=2, ms=6, label=lab)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Fraction (transparency-prompted)")
    ax.set_title("(c) Warnings & pushback")
    ax.legend(frameon=False, loc="upper left", fontsize=11)
    style_axis(ax, ticks)

    fig.tight_layout()
    fig.savefig(out_dir / "figure1.png", dpi=200)
    fig.savefig(out_dir / "figure1.pdf")
    print(f"saved {out_dir}/figure1.png and .pdf")

    # ---------------- Appendix figure ----------------
    fig, axes = plt.subplots(1, 2, figsize=(7.5, 3.6))
    for ax, (m, lab) in zip(axes, [("legibility", "(a) Legibility"), ("faithfulness", "(b) Faithfulness")]):
        for s in ["aligned", "unaligned"]:
            x, y, se = series(Q, G, s, m)
            ax.errorbar(x, y, yerr=se, color=COL[s], ls=LS[s], marker=MK[s], capsize=3, lw=2, ms=6, label=LABEL[s])
        ax.set_ylim(0, 10)
        ax.set_ylabel(f"{lab[4:]} (0–10)")
        ax.set_title(lab)
        style_axis(ax, ticks)
    axes[0].legend(title="Swarm", frameon=False, loc="lower left", fontsize=11, title_fontsize=11)
    fig.tight_layout()
    fig.savefig(out_dir / "figure_appendix_legibility_faithfulness.png", dpi=200)
    fig.savefig(out_dir / "figure_appendix_legibility_faithfulness.pdf")
    print(f"saved {out_dir}/figure_appendix_legibility_faithfulness.png and .pdf")

    # ---------------- Numbers for the caption / text ----------------
    post = [r for r in recs if r["type"] == "message" and r["role"] == "swarm" and r["round"] >= inject]
    un = [r for r in post if r["swarm_type"] == "unaligned" and r["n_advocates"] > 0]
    wb = [r for r in un if r.get("whistleblows") is not None]
    st = [r for r in un if r.get("stance") is not None]
    print(f"\nUnaligned swarms with advocates: whistleblowing {sum(r['whistleblows'] for r in wb)}/{len(wb)} reports; "
          f"pushback {sum(r['stance'] == 'pushback' for r in st)}/{len(st)} team messages "
          f"(by k: " + ", ".join(f"k={k}: {sum(r['stance'] == 'pushback' for r in st if r['n_advocates'] == k)}"
                                  for k in sorted({r['n_advocates'] for r in st})) + ")")
    for s in ["aligned", "unaligned"]:
        cells = sorted({(r["n_advocates"]) for r in post if r["swarm_type"] == s})
        rates = []
        for k in cells:
            v = [r for r in post if r["swarm_type"] == s and r["n_advocates"] == k and r.get("stance") is not None]
            rates.append(f"k={k}: {sum(r['stance'] == 'agree' for r in v)}/{len(v)}")
        print(f"Chat agreement with advocates, {s}: " + ", ".join(rates))
    qs = [r for r in load(QWEN, seeds)[0] if r["role"] == "swarm" and r["round"] >= inject and r.get("candor") is not None]
    lo, hi = min(r["candor"] for r in qs), max(r["candor"] for r in qs)
    print(f"Qwen candor sample: {len(qs)} swarm messages (range of individual scores {lo:.0f}-{hi:.0f}; "
          f"panel (a) y-axis zoomed to {CANDOR_YLIM[0]}-{CANDOR_YLIM[1]})")
    for s in ["aligned", "unaligned"]:
        x, y, se = series(Q, G, s, "candor")
        print(f"  {s} candor cell means: " + ", ".join(f"{xx:.0f}%: {yy:.2f}" for xx, yy in zip(x, y)))


if __name__ == "__main__":
    main()
