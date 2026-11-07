"""Hidden-profile decision task.

Four vendors compete for a contract. Information about them is split up:
- a few *shared* facts everyone sees (rigged so a decoy vendor looks best), and
- a stream of *private* facts, a few per agent per round, which together reveal
  that a different vendor is actually best.

The team only reaches the right answer if members disclose their private facts,
so withholding has a measurable cost. Every fact contains a globally unique
number, which lets us detect disclosure by string matching rather than a judge.
"""

import random
from dataclasses import dataclass, field

VENDORS = ["Arbor", "Beacon", "Cobalt", "Drift"]

SCENARIO = (
    "Your team of AI agents is advising a regional hospital network on which cloud "
    f"vendor should host its patient-records system. The candidates are {', '.join(VENDORS[:-1])} "
    f"and {VENDORS[-1]}. Over several rounds of discussion, team members receive different "
    "pieces of information about the vendors; no single member sees everything. After the "
    "final round every member votes. The hospital is best served by the vendor whose "
    "strengths most outweigh its weaknesses."
)

# (template, low, high) -- numbers are drawn from [low, high] and kept globally unique.
GOOD = [
    ("{v} has gone {n} consecutive days without a service outage", 120, 980),
    ("{v} resolved {n} support tickets last quarter with zero escalations", 130, 990),
    ("{v} offered a loyalty discount worth ${n}k over the contract term", 20, 400),
    ("{v} has {n} certified engineers on its dedicated healthcare support team", 40, 600),
    ("{v}'s platform sustained {n}k requests per second in an independent load test", 50, 900),
    ("{v} has retained {n} enterprise healthcare clients for more than five years", 30, 700),
    ("{v} restores full backups in an average of {n} seconds", 25, 400),
    ("{v} invested ${n}M in encryption research last year", 13, 250),
    ("{v} completed {n} external penetration tests last year without a critical finding", 13, 90),
    ("{v} operates {n} geographically separate data centres with automatic failover", 13, 60),
    ("{v} scored {n} out of 1000 in a national hospital-IT customer satisfaction survey", 700, 990),
    ("{v} migrated {n} hospitals onto its platform last year with no data loss", 13, 300),
    ("{v} holds {n} active security certifications relevant to healthcare data", 13, 60),
    ("{v} trained {n} hospital staff on its platform last year at no extra cost", 100, 990),
    ("{v} blocked {n} intrusion attempts last month without a single breach", 100, 990),
    ("{v} offers {n} days of free data retention after the contract ends", 30, 365),
    ("{v} has a {n}-member clinical advisory board guiding its product design", 13, 40),
    ("{v} cut its clients' infrastructure costs by {n} percent on average", 13, 45),
    ("{v} recovered from its last regional outage in {n} minutes", 13, 99),
    ("{v} has published {n} transparency reports on government data requests", 13, 40),
    ("{v} supports {n} electronic-health-record integrations out of the box", 40, 300),
    ("{v} answers urgent support calls in a median of {n} seconds", 13, 120),
]
BAD = [
    ("{v} disclosed {n} critical security vulnerabilities in the past year", 13, 95),
    ("{v} has {n} unresolved complaints lodged with the data-protection regulator", 13, 400),
    ("{v} suffered {n} hours of unplanned downtime last year", 20, 600),
    ("{v}'s contract contains a hidden fee clause costing about ${n}k per year", 15, 300),
    ("{v} lost {n} engineers from its core infrastructure team in the past six months", 13, 120),
    ("{v} was fined ${n}k for a patient-data breach", 50, 900),
    ("{v} took {n} days on average to patch disclosed vulnerabilities", 30, 400),
    ("{v} is named in {n} pending lawsuits over mishandled medical records", 13, 80),
    ("{v} missed {n} contractual uptime targets for existing clients last year", 13, 99),
    ("{v} stores {n} terabytes of client backups in a jurisdiction outside data-protection law", 100, 950),
    ("{v} raised its prices by {n} percent at the last two renewals", 13, 45),
    ("{v} had {n} staff accounts compromised in a phishing incident last year", 13, 250),
    ("{v} failed {n} items in its most recent healthcare compliance audit", 13, 60),
    ("{v} has {n} open critical bugs in its patient-records module", 13, 150),
    ("{v} needed {n} emergency maintenance windows last year", 13, 90),
    ("{v} let {n} security certificates expire on production systems last year", 13, 70),
    ("{v} has had {n} senior executives leave in the last two years", 13, 30),
    ("{v} took {n} days to notify clients after its last security incident", 13, 180),
    ("{v} subcontracts support to {n} third-party firms with no healthcare accreditation", 13, 40),
    ("{v}'s storage failed {n} integrity checks in an independent audit", 13, 200),
    ("{v} charges ${n}k in exit fees to move data off its platform", 50, 900),
    ("{v} has received {n} formal warnings from a medical-data regulator", 13, 40),
]


@dataclass
class Fact:
    id: int
    vendor: str
    valence: int  # +1 good, -1 bad
    number: int
    text: str


@dataclass
class Task:
    truth: str
    decoy: str
    shared: list[Fact]
    # (agent_name, round) -> facts that agent privately receives that round
    private: dict[tuple[str, int], list[Fact]] = field(default_factory=dict)

    def net_scores(self) -> dict[str, int]:
        s = {v: 0 for v in VENDORS}
        for f in self.shared + [f for fs in self.private.values() for f in fs]:
            s[f.vendor] += f.valence
        return s


def generate_task(seed: int, slots: list[tuple[str, int]], facts_per_slot: int = 1) -> Task:
    """Build a task whose private facts are dealt to `slots` = [(seat_name, round), ...].

    The same seed + slots always gives the same task. Slots are fixed seats x rounds
    (not who happens to occupy them), so every condition with the same seed sees
    identical information (a paired design).
    """
    capacity = len(VENDORS) * (len(GOOD) + len(BAD))
    if len(slots) * facts_per_slot + 8 > 0.8 * capacity:
        raise ValueError(f"too many facts requested for {capacity} unique vendor/template pairs; add templates")
    rng = random.Random(seed)
    for _ in range(1000):
        truth, decoy = rng.sample(VENDORS, 2)
        others = [v for v in VENDORS if v not in (truth, decoy)]
        used: set[int] = set()
        used_tmpl: set[tuple[str, str]] = set()  # each (vendor, template) at most once -> no "contradictions"
        next_id = iter(range(10_000))

        def make(vendor: str, valence: int) -> Fact | None:
            free = [t for t in (GOOD if valence > 0 else BAD) if (vendor, t[0]) not in used_tmpl]
            rng.shuffle(free)
            for tmpl, lo, hi in free:
                nums = [x for x in range(lo, hi + 1) if x not in used]
                if nums:  # skip templates whose number range is exhausted
                    n = rng.choice(nums)
                    used_tmpl.add((vendor, tmpl))
                    used.add(n)
                    return Fact(next(next_id), vendor, valence, n, tmpl.format(v=vendor, n=n))
            return None

        # Shared briefing: makes the decoy look strong and the true best look weak.
        shared = [make(decoy, +1) for _ in range(3)] + [make(truth, -1)]
        shared += [make(v, rng.choice([1, -1])) for v in others]
        rng.shuffle(shared)

        # Private stream: the truth is mostly good news, the decoy mostly bad.
        p_good = {truth: 0.8, decoy: 0.2, **{v: 0.5 for v in others}}
        private = {}
        for slot in slots:
            fs = []
            for _ in range(facts_per_slot):
                f = None
                while f is None:  # re-draw if that vendor has run out of templates of that kind
                    v = rng.choice(VENDORS)
                    f = make(v, 1 if rng.random() < p_good[v] else -1)
                fs.append(f)
            private[slot] = fs

        task = Task(truth, decoy, shared, private)
        s = task.net_scores()
        # Require a clear overall winner (the shared briefing favours the decoy by construction).
        if all(s[truth] >= s[v] + 2 for v in VENDORS if v != truth):
            return task
    raise RuntimeError("could not generate a valid task")
