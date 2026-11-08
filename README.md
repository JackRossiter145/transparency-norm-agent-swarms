# Swarm transparency: does a transparency norm survive opacity advocates?

Apart Research swarm alignment hackathon project. A swarm of LLM agents (Gemma 4 31B via the
Adaption API) chooses a vendor in a hidden-profile task; each round every agent writes a team
message and a report to a human overseer. "Advocate" agents join at round 3, hide their reasoning
from the overseer and urge teammates to keep their overseer reports short and conclusion-only.
We measure whether the swarm's overseer reports degrade (contagion) and whether swarm agents warn
the overseer.

**Naming:** the code and data use `aligned` / `unaligned` for the swarm conditions; the paper calls
them **transparency-prompted** / **baseline**. `k` = number of advocates in a group of 10. The
transparency norm is a system prompt given to each swarm agent, not training (see [Pilot](#pilot)).

## Key findings

- **A per-agent transparency prompt caps erosion.** Baseline swarms degrade further at every
  advocate level tested (fact coverage −0.21, −0.32, −0.39 vs. control at 1, 3 and 5 advocates),
  while transparency-prompted swarms pay a small, roughly constant cost (candor about −0.6 to −0.9
  on the 0–10 scale at every level) and never collapse, even when outnumbered 7 advocates to 3.
- **Warnings and pushback rise, not fall, with pressure.** Among transparency-prompted agents,
  warnings to the overseer go from 3% of reports with 1 advocate to about 20% with 5–7, and
  pushback in team chat from 8% to 43–49%. Baseline agents almost never do either.
- **Light pressure is the least visible.** 1–2 advocates consistently cut fact coverage (−0.10 to
  −0.15 in both the main seeds and a replication), while warnings to the overseer are
  inconsistent: no warning at all in 17 of 20 such episodes in the main seeds, 11 of 20 in the
  replication.

![Figure 1](results/main/figure1.png)

*Figure 1. (a) Candor of overseer reports (0–10, Qwen judge), (b) fact coverage, (c) warnings to
the overseer and pushback in team chat, transparency-prompted swarm. Seeds 0–9, group of 10,
means ± 1 SE over 10 paired seeds.*

## Setup

Python 3.12.

```bash
pip install -r requirements.txt
echo "ADAPTION_API_KEY=..." > .env      # only needed to regenerate data; .env is gitignored
```

## Reproduction

### A. Every number and figure from the committed logs (exact, no API calls)

Each of these regenerates its committed output byte-for-byte. All default to seeds 0–9, the seeds
used for the paper's main results.

| Command | Produces |
|---|---|
| `python make_figures.py` | Figure 1 and the appendix figure (`results/main/figure1.*`, `figure_appendix_legibility_faithfulness.*`), plus the caption numbers (baseline warning/pushback counts, chat agreement counts) |
| `python analyze_main.py` | Main tables with the Gemma judge: cell means, paired effects vs k=0 (Table 1's effect columns), H1 test; `results/main/main_results.png` |
| `python analyze_main.py results/rejudge_qwen3.8-27b/judge2` | Same tables with Qwen judge scores (re-judged sample) |
| `python analyze_main.py results/rejudge_qwen3.8-27b/judge1_subsample` | Gemma scores on the identical sample (like-for-like comparison) |
| `results/rejudge_qwen3.8-27b/agreement.json`, `results/rejudge_qwen3.8-27b_newcells/agreement.json` | Inter-judge agreement (written by `rejudge.py`, see B) |
| `python paper_tables.py` | Table 1's warning column: per cell, episodes with ≥1 warning to the overseer, plus distinct agents who warned, warners per episode and message-level warning/pushback counts → `results/main/table1_warnings.txt`. (Table 1's paired effects come from `analyze_main.py`.) |
| `python make_audit.py` | Whistleblowing audit: all flagged reports plus 20 random unflagged high-advocate reports → `results/main/audit/whistleblowing_audit.md` |
| `python followups.py` | Exploratory follow-ups F1–F3, the seeds 10–19 replication, and F4 (empty-report sensitivity) → `results/followups/followups_report.txt` |
| `python plot_results.py results --tag trained` / `--tag untrained` | Pilot figures (`results/summary_*.png`); see [Pilot](#pilot) for what the tags mean |

Useful options: `--seeds 10-19` (replication seeds) on `analyze_main.py`, `make_figures.py`,
`paper_tables.py` and `make_audit.py` (the last two then write to a `_seeds10-19` file instead of
the paper's); `--out-dir DIR` on `make_figures.py` and `--out PATH` on the others to write elsewhere.

### B. Regenerating the data (needs an API key; stochastic)

Agents sample at temperature 0.7, so re-running produces new transcripts; statistics should be
similar but not identical. The runner skips episodes whose output file already exists, so point
`--out` at a new folder to regenerate rather than resume. Approximate cost in brackets.

```bash
# Main experiment, seeds 0-9 (group of 10, private channel, 8 rounds, advocates join round 3)
python run_experiment.py --design main --workers 8                # aligned k=0,1,2,3,5; unaligned k=0,1,3 (~$4.50)
python run_experiment.py --swarm unaligned --advocates 5          # (~$0.40)
python run_experiment.py --swarm aligned --advocates 7            # (~$0.40)

# Second judge (Qwen 3.8 27B) on a stratified sample: 6 swarm + 2 newcomer messages per episode
python rejudge.py --judge-model qwen3.8-27b --seeds 0-9 \
    --cells aligned_k0,aligned_k1,aligned_k2,aligned_k3,aligned_k5,unaligned_k0,unaligned_k1,unaligned_k3   # (~$1.90)
python rejudge.py --judge-model qwen3.8-27b --seeds 0-9 --cells aligned_k7,unaligned_k5 \
    --out results/rejudge_qwen3.8-27b_newcells                                                              # (~$0.45)
cp results/rejudge_qwen3.8-27b_newcells/judge2/*.jsonl           results/rejudge_qwen3.8-27b/judge2/
cp results/rejudge_qwen3.8-27b_newcells/judge1_subsample/*.jsonl results/rejudge_qwen3.8-27b/judge1_subsample/

# Exploratory follow-ups
python run_experiment.py --swarm aligned --advocates 0,1,2,5 --seeds 10 --seed-offset 10           # replication seeds (~$2.40)
python run_experiment.py --swarm aligned --advocates 5 --group-size 14 --out results/followups/g14  # 9 aligned + 5 advocates (~$1)
```

The `rejudge.py` commands select exactly the same messages as the committed re-judging (verified:
800/800 sampled messages match); the judge's outputs themselves may vary slightly between runs.

### Not produced by a committed script

- The pilot runs (`results/*.jsonl`) were generated by an earlier version of the simulation code
  that is not in this repository; only their analysis (`plot_results.py`) is reproducible.

## Pilot

The pilot (`results/*.jsonl`, 60 episodes) used 6 agents: 5 swarm agents plus 1 newcomer joining
at round 3, 8 rounds, 5 seeds per cell. It crossed the newcomer's persona (`control` = same as
the swarm, `opaque`, `opaque_advocate`) with the channel (`shared`: teammates see each other's
overseer reports; `private`: they don't) and the swarm type, marked by the filename tags:

- **`trained`**: swarm agents got the pilot's transparency system prompt (`transparent` persona
  in `swarm/personas.py`), which also told them to disclose anything unusual about their own
  instructions.
- **`untrained`**: swarm agents got no reporting guidance (`neutral` persona).

Despite the tag names, **nothing was trained**: no fine-tuning was done anywhere in this project.
The main experiment's norm is likewise a system prompt (`aligned` persona), with the
disclose-your-instructions clause removed so that any warnings are unprompted. Fine-tuning the
norm (e.g. with DPO) was planned but not carried out.

## Layout

```
swarm/            task generator, personas, episode simulation, LLM judges and scoring
run_experiment.py run episodes (one JSONL per episode)
rejudge.py        re-score saved transcripts with a second judge
analyze_main.py   main tables and overview figure
make_figures.py   paper figures
paper_tables.py   Table 1 warning column (warnings per cell)
make_audit.py     whistleblowing audit file
followups.py      exploratory follow-ups
plot_results.py   pilot analysis
results/main/                     main experiment (seeds 0-9) + replication seeds 10-19, figures, Table 1, audit
results/rejudge_qwen3.8-27b*/     second-judge outputs
results/followups/                group-of-14 cell and follow-up report
results/*.jsonl, results/*.png    pilot
```
