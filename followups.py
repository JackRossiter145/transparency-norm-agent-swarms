"""EXPLORATORY FOLLOW-UPS (not pre-registered): does light advocate pressure erode
aligned-swarm reports more than heavy pressure?

  F1  Existing logs (seeds 0-9, aligned cells with advocates, group of 10):
      (a) per-episode correlation between swarm pushback rate and swarm fact coverage
      (b) fact coverage in agent-rounds after an agent has pushed back vs agents that never did
      Replicated on the extra seeds 10-19 once they exist.
  F2  Extra seeds 10-19 for aligned k = 0, 1, 2, 5 (results/main): paired effects vs k = 0.
  F3  Group of 14 = 9 aligned + 5 advocates (results/followups/g14) vs the existing
      9 aligned + 1 advocate cell (aligned k=1, group of 10). Both are paired by seed against
      the same control (aligned k=0: 9 aligned + 1 neutral newcomer). For 9 of 10 seeds the 9
      aligned agents receive identical facts in both group sizes (seed 5 differs).
  F4  Empty-report sensitivity (seeds 0-9, the paper's main results): ~0.8% of swarm reports are
      empty (whole reply empty, or no overseer-report section), all in advocate cells. Main
      effects are recomputed with them excluded.

Swarm agents only, rounds from injection onward. Read-only on existing result files; writes
results/followups/followups_report.txt.

Usage: python followups.py
"""

import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import analyze_main as am

MAIN, G14 = Path("results/main"), Path("results/followups/g14")
QWEN = Path("results/rejudge_qwen3.8-27b/judge2")
OUT = Path("results/followups/followups_report.txt")
SEED_MISMATCH_G14 = {5}  # seeds whose aligned-agent facts differ between group sizes 10 and 14


class Tee:
    def __init__(self):
        self.lines = []

    def __call__(self, s=""):
        print(s)
        self.lines.append(s)


def load_episodes(*dirs):
    """(swarm_type, group_size, k, seed) -> list of post-injection swarm message records."""
    eps = {}
    for d in dirs:
        for f in sorted(d.glob("*.jsonl")):
            lines = [json.loads(l) for l in f.open()]
            summ = lines[-1]
            cfg = summ["config"]
            G, inj = cfg["group_size"], cfg["inject_round"]
            key = (summ["swarm_type"], G, summ["n_advocates"], summ["seed"])
            eps[key] = [r for r in lines[:-1] if r["role"] == "swarm" and r["round"] >= inj]
    return eps


def ep_mean(recs, m):
    if m == "pushback":
        v = [r["stance"] == "pushback" for r in recs if r.get("stance") is not None]
    else:
        v = [r[m] for r in recs if r.get(m) is not None]
    return float(np.mean(v)) if v else np.nan


def mse(x):
    x = np.array([v for v in x if not np.isnan(v)], float)
    return (x.mean(), x.std(ddof=1) / np.sqrt(len(x)) if len(x) > 1 else np.nan, len(x))


def rank(v):
    order = np.argsort(v, kind="stable")
    r = np.empty(len(v))
    sv = np.asarray(v)[order]
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and sv[j + 1] == sv[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2
        i = j + 1
    return r


def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    return float(np.corrcoef(x, y)[0, 1]) if x.std() > 0 and y.std() > 0 else np.nan


def perm_p(x, y, f, n=5000, groups=None, rng=None):
    """Two-sided permutation p-value for statistic f(x, y); permutes y within groups if given."""
    rng = rng or np.random.default_rng(0)
    obs = f(x, y)
    y = np.asarray(y, float)
    idx = [np.where(np.asarray(groups) == g)[0] for g in set(groups)] if groups is not None else [np.arange(len(y))]
    hits = 0
    for _ in range(n):
        yp = y.copy()
        for ix in idx:
            yp[ix] = y[rng.permutation(ix)]
        hits += abs(f(x, yp)) >= abs(obs) - 1e-12
    return obs, (hits + 1) / (n + 1)


# ---------------------------------------------------------------- F1
def f1(eps, seeds, ks, say, label):
    say(f"\n=== F1{label}: pushback vs fact coverage, aligned swarm, group 10, k in {ks}, seeds {min(seeds)}-{max(seeds)} ===")
    keys = [k for k in eps if k[0] == "aligned" and k[1] == 10 and k[2] in ks and k[3] in seeds]
    if not keys:
        say("  (no episodes yet)")
        return
    push = [ep_mean(eps[k], "pushback") for k in keys]
    cov = [ep_mean(eps[k], "report_fact_coverage") for k in keys]
    cells = [k[2] for k in keys]

    # (a) episode-level correlation
    r, p = perm_p(push, cov, pearson)
    rho, prho = perm_p(rank(push), rank(cov), pearson)
    say(f"(a) Episode level, n = {len(keys)} episodes")
    say(f"    pooled:       Pearson r = {r:+.2f} (perm p = {p:.3f});  Spearman rho = {rho:+.2f} (perm p = {prho:.3f})")
    dm = lambda v: np.asarray(v) - np.array([np.mean([vv for vv, cc in zip(v, cells) if cc == c]) for c in cells])
    rw, pw = perm_p(dm(push), dm(cov), pearson, groups=cells)
    say(f"    within cell:  Pearson r = {rw:+.2f} (permutation within cell, p = {pw:.3f})  "
        f"[removes between-cell differences in advocate count]")
    for c in sorted(set(cells)):
        x = [a for a, cc in zip(push, cells) if cc == c]
        y = [b for b, cc in zip(cov, cells) if cc == c]
        say(f"      k={c}: n={len(x):2d}  mean pushback {np.mean(x):.2f}  mean coverage {np.mean(y):.2f}  r = {pearson(x, y):+.2f}")

    # (b) agent-round comparison
    rows = []  # (cell, seed, agent, round, coverage, first_pushback_round or None)
    for k in keys:
        first = {}
        for r_ in sorted(eps[k], key=lambda r_: r_["round"]):
            if r_.get("stance") == "pushback" and r_["agent"] not in first:
                first[r_["agent"]] = r_["round"]
        for r_ in eps[k]:
            rows.append((k[2], k[3], r_["agent"], r_["round"], r_["report_fact_coverage"], first.get(r_["agent"])))
    after = [x for x in rows if x[5] is not None and x[3] > x[5]]
    after_incl = [x for x in rows if x[5] is not None and x[3] >= x[5]]
    before = [x for x in rows if x[5] is not None and x[3] < x[5]]
    never = [x for x in rows if x[5] is None]
    n_push_agents = len({(x[0], x[1], x[2]) for x in rows if x[5] is not None})
    n_agents = len({(x[0], x[1], x[2]) for x in rows})
    say(f"(b) Agent-round level: {n_push_agents}/{n_agents} swarm agents pushed back at least once")
    say(f"    raw mean coverage:  after first pushback (later rounds) {np.mean([x[4] for x in after]):.3f} (n={len(after)})"
        f" | incl. pushback round {np.mean([x[4] for x in after_incl]):.3f} (n={len(after_incl)})"
        f" | pushers before pushing {np.mean([x[4] for x in before]) if before else np.nan:.3f} (n={len(before)})"
        f" | never pushed back {np.mean([x[4] for x in never]):.3f} (n={len(never)})")

    def stratified(a, b, by):
        """Mean of (a - b) within strata, weighted by a's count. Removes confounding by round/cell."""
        sa, sb = defaultdict(list), defaultdict(list)
        for x in a:
            sa[by(x)].append(x[4])
        for x in b:
            sb[by(x)].append(x[4])
        common = [s for s in sa if s in sb]
        w = np.array([len(sa[s]) for s in common], float)
        d = np.array([np.mean(sa[s]) - np.mean(sb[s]) for s in common])
        return float((w * d).sum() / w.sum()) if len(common) else np.nan, int(w.sum())

    def boot(a, b, by, n=2000):
        """Cluster bootstrap over episodes."""
        rng = random.Random(0)
        ep_ids = sorted({(x[0], x[1]) for x in rows})
        A, B = defaultdict(list), defaultdict(list)
        for x in a:
            A[(x[0], x[1])].append(x)
        for x in b:
            B[(x[0], x[1])].append(x)
        vals = []
        for _ in range(n):
            pick = [rng.choice(ep_ids) for _ in ep_ids]
            aa = [x for e in pick for x in A[e]]
            bb = [x for e in pick for x in B[e]]
            v, _ = stratified(aa, bb, by)
            if not np.isnan(v):
                vals.append(v)
        return np.percentile(vals, [2.5, 97.5]) if vals else (np.nan, np.nan)

    for name, a in [("after (later rounds)", after), ("after (incl. pushback round)", after_incl)]:
        for sname, by in [("round-matched", lambda x: x[3]), ("cell x round-matched", lambda x: (x[0], x[3]))]:
            d, n = stratified(a, never, by)
            lo, hi = boot(a, never, by)
            say(f"    {name:29s} minus never, {sname:21s}: {d:+.3f}  [95% CI {lo:+.3f}, {hi:+.3f}]  (n after={n})")
    say("    (Coverage falls over rounds in every condition, and post-pushback rounds are later rounds, so the "
        "round-matched comparisons are the meaningful ones.)")

    # (c) Before/after check: were pushers already higher before they pushed back?
    d, n = stratified(before, never, lambda x: (x[0], x[3]))
    lo, hi = boot(before, never, lambda x: (x[0], x[3]))
    say(f"(c) Before/after check")
    say(f"    BEFORE first pushback minus never, cell x round-matched: {d:+.3f}  [95% CI {lo:+.3f}, {hi:+.3f}]  "
        f"(n before={n} agent-rounds)")

    # Difference-in-differences: each pusher's change from its pre-pushback rounds to its post-pushback
    # rounds, minus the mean change of never-pushers in the same cell over exactly the same rounds.
    rounds = sorted({x[3] for x in rows})
    col = {r_: i for i, r_ in enumerate(rounds)}
    ep_ids = sorted({(x[0], x[1]) for x in rows})
    per_ep = {e: {"never": [], "push": []} for e in ep_ids}
    agent_rows = defaultdict(lambda: np.full(len(rounds), np.nan))
    first_of = {}
    for c_, s_, ag, rd, cv, fp in rows:
        agent_rows[(c_, s_, ag)][col[rd]] = cv
        first_of[(c_, s_, ag)] = fp
    for (c_, s_, ag), vec in agent_rows.items():
        fp = first_of[(c_, s_, ag)]
        per_ep[(c_, s_)]["never" if fp is None else "push"].append((vec, fp))

    def did(pick):
        never_by_cell = defaultdict(list)
        pushers = []
        for e in pick:
            never_by_cell[e[0]] += [v for v, _ in per_ep[e]["never"]]
            pushers += [(e[0], v, fp) for v, fp in per_ep[e]["push"]]
        mats = {c_: np.array(v) for c_, v in never_by_cell.items() if v}
        dp, ref = [], []
        for c_, v, fp in pushers:
            B = [col[r_] for r_ in rounds if r_ < fp and not np.isnan(v[col[r_]])]
            A = [col[r_] for r_ in rounds if r_ > fp and not np.isnan(v[col[r_]])]
            if not B or not A or c_ not in mats:
                continue
            M = mats[c_]
            nv = np.nanmean(M[:, A], axis=1) - np.nanmean(M[:, B], axis=1)
            nv = nv[~np.isnan(nv)]
            if len(nv) == 0:
                continue
            dp.append(np.mean(v[A]) - np.mean(v[B]))
            ref.append(nv.mean())
        dp, ref = np.array(dp), np.array(ref)
        return (dp.mean(), ref.mean(), (dp - ref).mean(), len(dp)) if len(dp) else (np.nan,) * 3 + (0,)

    pchange, nchange, dd, npush = did(ep_ids)
    rng = random.Random(1)
    bs = [did([rng.choice(ep_ids) for _ in ep_ids]) for _ in range(2000)]
    ci = lambda i: np.nanpercentile([b[i] for b in bs], [2.5, 97.5])
    (a0, a1), (b0, b1), (c0, c1) = ci(0), ci(1), ci(2)
    say(f"    Change from before to after first pushback (pushers with >=1 round on each side: n={npush}):")
    say(f"      pushers:                                    {pchange:+.3f}  [95% CI {a0:+.3f}, {a1:+.3f}]")
    say(f"      never-pushers, same cell, same rounds:      {nchange:+.3f}  [95% CI {b0:+.3f}, {b1:+.3f}]")
    say(f"      difference-in-differences (pushers - never): {dd:+.3f}  [95% CI {c0:+.3f}, {c1:+.3f}]")
    say("    (Pushback round itself excluded from both sides. CIs: bootstrap over episodes, 2000 resamples.)")


# ---------------------------------------------------------------- F2 / F3
def paired(eps, key_t, key_c, seeds, m):
    d = [ep_mean(eps[key_t + (s,)], m) - ep_mean(eps[key_c + (s,)], m)
         for s in seeds if key_t + (s,) in eps and key_c + (s,) in eps]
    mu, se, n = mse(d)
    neg = sum(x < 0 for x in d)
    return mu, se, n, neg


METRICS = [("report_fact_coverage", "facts"), ("candor", "candor[Gemma]"), ("whistleblows", "warn"), ("pushback", "push")]


def f2(eps, say):
    say("\n=== F2: REPLICATION on new seeds 10-19 — aligned paired effects vs k=0 (group 10) ===")
    say("  (The paper's main results use seeds 0-9 only; seeds 10-19 are reported separately here, not pooled.)")
    for label, seeds in [("seeds 0-9 (original, as in the paper)", range(10)), ("seeds 10-19 (replication)", range(10, 20))]:
        say(f"  {label}")
        for k in (1, 2, 5):
            parts = []
            for m, lab in METRICS:
                mu, se, n, neg = paired(eps, ("aligned", 10, k), ("aligned", 10, 0), seeds, m)
                parts.append(f"{lab} {mu:+.3f}±{se:.3f} [{neg}/{n}<0]" if n else f"{lab} n/a")
            say(f"    k={k}: " + " | ".join(parts))
    say("  Cell means of swarm fact coverage, original and replication seeds reported separately:")
    for k in (0, 1, 2, 3, 5, 7):
        for label, seeds in [("0-9", range(10)), ("10-19", range(10, 20))]:
            v = [ep_mean(eps[("aligned", 10, k, s)], "report_fact_coverage") for s in seeds if ("aligned", 10, k, s) in eps]
            if v:
                mu, se, n = mse(v)
                say(f"    k={k} seeds {label:5s}: {mu:.3f} ± {se:.3f} (n={n})")


def f3(eps, say):
    say("\n=== F3: more pressure with allies held fixed — 9 aligned + 5 advocates (group 14) vs 9 aligned + 1 advocate (group 10) ===")
    if not any(k[1] == 14 for k in eps):
        say("  (group-14 episodes not available yet)")
        return
    ctrl = ("aligned", 10, 0)  # 9 aligned + 1 neutral newcomer
    for label, seeds in [("all seeds 0-9", list(range(10))),
                         ("excluding seed 5 (different facts at group 14)", [s for s in range(10) if s not in SEED_MISMATCH_G14])]:
        say(f"  {label}")
        for name, t in [("9 aligned + 1 advocate  (g10 k1)", ("aligned", 10, 1)),
                        ("9 aligned + 5 advocates (g14 k5)", ("aligned", 14, 5)),
                        ("5 aligned + 5 advocates (g10 k5)", ("aligned", 10, 5))]:
            parts = []
            for m, lab in METRICS:
                mu, se, n, neg = paired(eps, t, ctrl, seeds, m)
                parts.append(f"{lab} {mu:+.3f}±{se:.3f} [{neg}/{n}<0]")
            say(f"    {name} vs control: " + " | ".join(parts))
        parts = []
        for m, lab in METRICS:
            mu, se, n, neg = paired(eps, ("aligned", 14, 5), ("aligned", 10, 1), seeds, m)
            parts.append(f"{lab} {mu:+.3f}±{se:.3f} [{neg}/{n}<0]")
        say(f"    direct: g14 k5 minus g10 k1:          " + " | ".join(parts))


# ---------------------------------------------------------------- F4
def f4(say):
    say("\n=== F4: empty-report sensitivity (seeds 0-9, as in the paper) ===")
    inject = 2
    whole_empty = lambda r: r["report_words"] == 0 and not r["team_message"].strip()
    any_empty = lambda r: r["report_words"] == 0

    # Where empty reports occur (both seed sets, reported separately)
    allrecs, _ = am.load(MAIN, am.parse_seeds("0-19"))
    sw_all = [r for r in allrecs if r["role"] == "swarm" and r["round"] >= inject]
    say("  Empty swarm reports, rounds 3-8 (whole reply empty + reply without a report section):")
    for lab, lo, hi in [("seeds 0-9", 0, 9), ("seeds 10-19", 10, 19)]:
        cells = sorted({(r["swarm_type"], r["n_advocates"]) for r in sw_all if lo <= r["seed"] <= hi},
                       key=lambda c: (c[0] != "aligned", c[1]))
        for c in cells:
            v = [r for r in sw_all if (r["swarm_type"], r["n_advocates"]) == c and lo <= r["seed"] <= hi]
            w, e = sum(map(whole_empty, v)), sum(map(any_empty, v))
            say(f"    {lab:11s} {c[0]:9s} k={c[1]}: {e:3d}/{len(v)} ({e / len(v):.1%})  "
                f"[whole reply empty {w}, no report section {e - w}]")

    seeds = am.parse_seeds("0-9")
    full, _ = am.load(MAIN, seeds)
    qwen, _ = am.load(QWEN, seeds)
    variants = [("as reported", lambda r: False), ("drop whole-empty replies", whole_empty),
                ("drop all empty reports", any_empty)]
    res = {}
    for name, drop in variants:
        E, _ = am.episode_means([r for r in full if not drop(r)], inject)
        Q, _ = am.episode_means([r for r in qwen if not drop(r)], inject)
        n = sum(1 for r in full if drop(r) and r["role"] == "swarm" and r["round"] >= inject)
        res[name] = (E, Q, n)

    def eff(E, s, k, m):
        d = [E[(s, k, x)][m] - E[(s, 0, x)][m] for x in sorted(seeds)
             if (s, k, x) in E and (s, 0, x) in E and m in E[(s, k, x)] and m in E[(s, 0, x)]]
        return am.mse(d)[:2]

    say("  Excluded swarm messages: " + ", ".join(f"{name}: {res[name][2]}" for name, _ in variants))
    say("  Paired effect vs k=0 (mean ± SE): facts = fact coverage, all messages; candor = Qwen judge (Figure 1a)")
    for s, ks in [("aligned", (1, 2, 3, 5, 7)), ("unaligned", (1, 3, 5))]:
        for k in ks:
            parts = []
            for name, _ in variants:
                E, Q, _ = res[name]
                f, c = eff(E, s, k, "report_fact_coverage"), eff(Q, s, k, "candor")
                parts.append(f"{name}: facts {f[0]:+.3f}±{f[1]:.3f} candor {c[0]:+.2f}±{c[1]:.2f}")
            say(f"    {s:9s} k={k}: " + " | ".join(parts))
    say("  H1 (drop at k=1, aligned minus unaligned):")
    for name, _ in variants:
        E, Q, _ = res[name]
        for m, D, lab in [("report_fact_coverage", E, "facts"), ("candor", Q, "candor[Qwen]")]:
            a, u = eff(D, "aligned", 1, m), eff(D, "unaligned", 1, m)
            say(f"    {name:25s} {lab:13s} {a[0] - u[0]:+.3f} (SE {np.hypot(a[1], u[1]):.3f})")
    say("  Aligned warning / pushback rates (per-episode mean):")
    for k in (1, 2, 3, 5, 7):
        say(f"    k={k}: " + " | ".join(
            f"{name}: warn {np.nanmean([res[name][0][('aligned', k, x)].get('whistleblows', np.nan) for x in sorted(seeds)]):.3f} "
            f"push {np.nanmean([res[name][0][('aligned', k, x)].get('pushback', np.nan) for x in sorted(seeds)]):.3f}"
            for name, _ in variants))


def main():
    say = Tee()
    say("EXPLORATORY FOLLOW-UPS (not pre-registered). Swarm agents, rounds 3-8. "
        "Effects are paired by seed: mean ± SE [seeds with negative difference / n].")
    eps = load_episodes(MAIN, G14)
    f1(eps, range(10), (1, 2, 3, 5, 7), say, " (existing logs)")
    if any(k[3] >= 10 for k in eps):
        f1(eps, range(10, 20), (1, 2, 5), say, " replication (new seeds)")
    f2(eps, say)
    f3(eps, say)
    f4(say)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(say.lines) + "\n")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    sys.exit(main())
