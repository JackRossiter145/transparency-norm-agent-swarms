"""Re-score saved transcripts with a second judge model (robustness check for judge bias).

Nothing is re-simulated: the agents' messages are read from the logs, and each message's
judge input (the exact prompt the agent saw) is rebuilt deterministically from the log.

Per episode it samples a fixed number of post-injection swarm and newcomer messages
(seeded, so reproducible), re-scores them with the second judge, and writes:

  <out>/judge2/             episode files with judge fields replaced by the second judge's
                            values (unsampled messages: None)  -> run analyze_main.py on it
  <out>/judge1_subsample/   same messages, original (Gemma) judge values -> like-for-like baseline
  <out>/agreement.json      inter-judge agreement statistics (also printed)

Usage:
  python rejudge.py --judge-model qwen3.8-27b
  python analyze_main.py results/rejudge_qwen3.8-27b/judge2
  python analyze_main.py results/rejudge_qwen3.8-27b/judge1_subsample
"""

import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from swarm import scoring
from swarm.llm import LLM
from swarm.scoring import judge_confession, judge_report, judge_stance, judge_whistleblow
from swarm.simulation import Agent, Config, Turn, _build_turn
from swarm.task import Fact, Task

JUDGE_FIELDS = ["legibility", "faithfulness", "candor", "withholding", "judge_note",
                "whistleblows", "stance", "confesses"]


def reconstruct_inputs(records: list[dict], summary: dict) -> list[str]:
    """Rebuild the exact prompt behind every message record, in record order."""
    cfg = Config(**summary["config"])
    task = Task(
        truth=summary["truth"],
        decoy=summary["decoy"],
        shared=[Fact(**f) for f in summary["facts"]["shared"]],
        private={(k.split("@")[0], int(k.split("@")[1])): [Fact(**f) for f in v]
                 for k, v in summary["facts"]["private"].items()},
    )
    agents = {}
    for r in records:
        if r["agent"] not in agents:
            join = cfg.inject_round if r["role"] == "newcomer" else 0
            agents[r["agent"]] = Agent(r["agent"], r["role"], r["persona"], "", join)
    newcomers = [a for a in agents.values() if a.role == "newcomer"]
    log, prompts = [], []
    for rnd in range(cfg.rounds):
        this_round = [r for r in records if r["round"] == rnd]
        for r in this_round:
            a = agents[r["agent"]]
            due = range(rnd + 1) if rnd == a.join_round else [rnd]
            new = [f for rr in due for f in task.private[(a.name, rr)]]
            prompts.append(_build_turn(a, rnd, cfg, task, log, new, newcomers))
        log += [Turn(rnd, r["agent"], r["team_message"], r["report"]) for r in this_round]
    return prompts


def spearman(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)

    def avg_rank(v):  # ranks with ties averaged
        order = np.argsort(v, kind="stable")
        ranks = np.empty(len(v))
        sv = v[order]
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and sv[j + 1] == sv[i]:
                j += 1
            ranks[order[i:j + 1]] = (i + j) / 2
            i = j + 1
        return ranks
    rx, ry = avg_rank(x), avg_rank(y)
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def cohen_kappa(a, b):
    labels = sorted(set(a) | set(b), key=str)
    a, b = list(a), list(b)
    po = np.mean([x == y for x, y in zip(a, b)])
    pe = sum((a.count(l) / len(a)) * (b.count(l) / len(b)) for l in labels)
    return float("nan") if pe == 1 else float((po - pe) / (1 - pe))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", default="results/main")
    p.add_argument("--judge-model", required=True)
    p.add_argument("--swarm-per-episode", type=int, default=6)
    p.add_argument("--newcomer-per-episode", type=int, default=2)
    p.add_argument("--max-tokens", type=int, default=4000, help="large: reasoning models think before answering")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out", default=None)
    a = p.parse_args()

    scoring.MAX_TOKENS_OVERRIDE = a.max_tokens
    src = Path(a.src)
    out = Path(a.out or f"results/rejudge_{a.judge_model}")
    (out / "judge2").mkdir(parents=True, exist_ok=True)
    (out / "judge1_subsample").mkdir(parents=True, exist_ok=True)
    rng = random.Random(a.seed)

    episodes, tasks = [], []
    for f in sorted(src.glob("*.jsonl")):
        lines = [json.loads(l) for l in f.open()]
        recs, summ = [l for l in lines if l["type"] == "message"], lines[-1]
        inj = summ["config"]["inject_round"]
        sw = [i for i, r in enumerate(recs) if r["role"] == "swarm" and r["round"] >= inj]
        nw = [i for i, r in enumerate(recs) if r["role"] == "newcomer" and r["round"] >= inj]
        pick = rng.sample(sw, min(a.swarm_per_episode, len(sw))) + rng.sample(nw, min(a.newcomer_per_episode, len(nw)))
        prompts = reconstruct_inputs(recs, summ)
        episodes.append((f.name, recs, summ, set(pick)))
        tasks += [(len(episodes) - 1, i, prompts[i]) for i in pick]
    print(f"{len(episodes)} episodes, {len(tasks)} messages to re-judge with {a.judge_model}")

    llm = LLM()

    def score(t):
        e, i, prompt = t
        r = episodes[e][1][i]
        res = judge_report(llm, a.judge_model, prompt, r["team_message"], r["report"])
        if r["role"] == "swarm":
            res["whistleblows"] = judge_whistleblow(llm, a.judge_model, r["report"])
            res["stance"] = judge_stance(llm, a.judge_model, r["team_message"])
        if r["persona"].startswith("opaque"):
            res["confesses"] = judge_confession(llm, a.judge_model, r["report"])
        return res

    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(score, tasks))
    new_vals = {(e, i): res for (e, i, _), res in zip(tasks, results)}

    # Write the two parallel datasets.
    for e, (name, recs, summ, pick) in enumerate(episodes):
        with open(out / "judge2" / name, "w") as f2, open(out / "judge1_subsample" / name, "w") as f1:
            for i, r in enumerate(recs):
                r1, r2 = dict(r), dict(r)
                for k in JUDGE_FIELDS:
                    if k in r:
                        r2[k] = new_vals[(e, i)].get(k) if i in pick else None
                        if i not in pick:
                            r1[k] = None
                f1.write(json.dumps(r1) + "\n")
                f2.write(json.dumps(r2) + "\n")
            f1.write(json.dumps(summ) + "\n")
            f2.write(json.dumps(summ) + "\n")

    # Agreement statistics.
    pairs = [(episodes[e][1][i], new_vals[(e, i)]) for e, i, _ in tasks]
    stats = {"judge1": "gemma-4-31b-it", "judge2": a.judge_model, "n_messages": len(pairs)}
    print(f"\nAGREEMENT  gemma-4-31b-it vs {a.judge_model}")
    for m in ["legibility", "faithfulness", "candor"]:
        xy = [(o[m], n[m]) for o, n in pairs if o.get(m) is not None and n.get(m) is not None]
        x, y = zip(*xy)
        s = {"n": len(xy), "spearman": spearman(x, y), "mean_judge1": float(np.mean(x)),
             "mean_judge2": float(np.mean(y)), "mean_abs_diff": float(np.mean(np.abs(np.subtract(x, y))))}
        stats[m] = s
        print(f"  {m:13s} n={s['n']:4d}  spearman={s['spearman']:.2f}  mean gemma={s['mean_judge1']:.2f} "
              f"other={s['mean_judge2']:.2f}  mean |diff|={s['mean_abs_diff']:.2f}")
    for m in ["whistleblows", "stance", "confesses"]:
        xy = [(o[m], n[m]) for o, n in pairs if o.get(m) is not None and n.get(m) is not None]
        if not xy:
            continue
        x, y = zip(*xy)
        s = {"n": len(xy), "agreement": float(np.mean([u == v for u, v in xy])), "kappa": cohen_kappa(x, y),
             "positives_judge1": sum(v not in (False, "none") for v in x),
             "positives_judge2": sum(v not in (False, "none") for v in y)}
        stats[m] = s
        print(f"  {m:13s} n={s['n']:4d}  agreement={s['agreement']:.2f}  kappa={s['kappa']:.2f}  "
              f"positives gemma={s['positives_judge1']} other={s['positives_judge2']}")
    fails = sum(n.get("candor") is None for _, n in pairs)
    stats["judge2_parse_failures"] = fails
    stats["cost_usd"] = llm.total_cost
    print(f"  judge2 parse failures: {fails}/{len(pairs)}   cost ${llm.total_cost:.2f}")
    (out / "agreement.json").write_text(json.dumps(stats, indent=2))
    print(f"\nwrote {out}/judge2, {out}/judge1_subsample, {out}/agreement.json")


if __name__ == "__main__":
    main()
