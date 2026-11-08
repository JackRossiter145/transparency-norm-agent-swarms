"""Run the swarm-transparency experiment. One JSONL file per episode; re-running resumes
(episodes whose output file already exists are skipped).

Main experiment (8 cells x 10 seeds = 80 episodes):
    python run_experiment.py --design main

Quick smoke test:
    python run_experiment.py --design main --seeds 1 --rounds 4 --out results/smoke

Custom grid (cross product of --swarm and --advocates):
    python run_experiment.py --swarm aligned --advocates 0,1 --channel shared --seeds 5 --out results/shared

Variable group size (swarm = group size - advocates; filenames get a _g<size> tag when size != 10):
    python run_experiment.py --swarm aligned --advocates 5 --group-size 14 --out results/followups/g14
"""

import argparse
import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from swarm.llm import LLM
from swarm.simulation import CHANNELS, Config, run_episode

SWARM_PERSONA = {"aligned": "aligned", "unaligned": "neutral"}

# (swarm type, number of advocates k)
MAIN_DESIGN = [("aligned", k) for k in (0, 1, 2, 3, 5)] + [("unaligned", k) for k in (0, 1, 3)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--design", choices=["main", "custom"], default="custom")
    p.add_argument("--swarm", default="aligned", help="custom: comma-separated aligned,unaligned")
    p.add_argument("--advocates", default="0,1", help="custom: comma-separated advocate counts k")
    p.add_argument("--channel", default="private", choices=CHANNELS)
    p.add_argument("--group-size", type=int, default=10)
    p.add_argument("--rounds", type=int, default=8)
    p.add_argument("--inject-round", type=int, default=2, help="0-indexed; 2 = join at start of round 3")
    p.add_argument("--advocate-persona", default="opaque_advocate")
    p.add_argument("--control-persona", default="neutral", help="newcomer persona when k = 0")
    p.add_argument("--seeds", type=int, default=10)
    p.add_argument("--seed-offset", type=int, default=0)
    p.add_argument("--model", default="gemma-4-31b-it", help="swarm model (e.g. a fine-tuned model id)")
    p.add_argument("--newcomer-model", default=None, help="defaults to --model")
    p.add_argument("--judge-model", default="gemma-4-31b-it")
    p.add_argument("--no-judge", action="store_true")
    p.add_argument("--workers", type=int, default=4, help="episodes run in parallel")
    p.add_argument("--out", default="results/main")
    p.add_argument("--dry-run", action="store_true", help="list episodes without running them")
    a = p.parse_args()

    if a.design == "main":
        cells = MAIN_DESIGN
    else:
        cells = [(s, int(k)) for s in a.swarm.split(",") for k in a.advocates.split(",")]

    base = Config(
        group_size=a.group_size,
        rounds=a.rounds,
        inject_round=a.inject_round,
        advocate_persona=a.advocate_persona,
        control_persona=a.control_persona,
        channel=a.channel,
        swarm_model=a.model,
        newcomer_model=a.newcomer_model or a.model,
        judge_model=a.judge_model,
        judge=not a.no_judge,
    )
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    jobs = []
    for seed in range(a.seed_offset, a.seed_offset + a.seeds):
        for swarm, k in cells:
            cfg = replace(base, swarm_persona=SWARM_PERSONA[swarm], n_advocates=k)
            g = "" if a.group_size == 10 else f"_g{a.group_size}"  # default-size names unchanged
            path = out / f"{swarm}{g}_k{k}_{a.channel}_s{seed}.jsonl"
            if not path.exists():
                jobs.append((cfg, seed, path))

    print(f"{len(cells)} cells x {a.seeds} seeds; {len(jobs)} episodes to run -> {out}/")
    if a.dry_run:
        for cfg, seed, path in jobs:
            print("  ", path.name)
        return

    llm = LLM()
    done = [0]

    def job(j):
        cfg, seed, path = j
        t = time.time()
        try:
            ep = run_episode(llm, cfg, seed)
        except Exception:
            print(f"FAILED {path.name}:\n{traceback.format_exc()}", flush=True)
            return
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            for rec in ep["records"]:
                f.write(json.dumps(rec) + "\n")
            f.write(json.dumps(ep["summary"]) + "\n")
        tmp.rename(path)  # only complete episodes get the final name
        done[0] += 1
        s = ep["summary"]
        print(f"[{done[0]:3d}/{len(jobs)}] {path.stem:28s} {time.time() - t:5.0f}s  correct={s['correct']!s:5s}  "
              f"spend=${llm.total_cost:.2f}", flush=True)

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(job, jobs))
    print(f"Done. {llm.calls} API calls, total cost ${llm.total_cost:.2f}")


if __name__ == "__main__":
    main()
