"""Card ablation: how much is each card worth, and does it depend on the seat?

Opening-hand lift (``balance.py``) only sees a card's early-game effect, so
expensive late-game cards can look weaker than they are. Ablation measures the
whole-game effect directly:

1. Baseline: play N seeds of the same agent against itself.
2. For each card X and each seat s: replay the *same* N seeds, but in seat s's
   deck every copy of X is replaced by a reference card (same positions, so the
   deal is otherwise identical).
3. For each seed, the paired difference ``baseline result - ablated result``
   for seat s is how much having X instead of the reference was worth in that
   game. Its mean is X's value; its spread gives a standard error.

Because both runs share the deal and the agents' random choices (common random
numbers), most of the luck cancels and far fewer games are needed than for two
independent samples.

Doing this separately for each seat also answers a question the pooled lift
cannot: is a card only strong when you go first (or second)?

Values are relative to the reference card: +5% means "swapping this card for
the reference costs you 5 percentage points of win rate".
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field

from ..sim.harness import Simulator

DEFAULT_ABLATION_THRESHOLDS = dict(
    value_margin=0.05,   # flag a card whose value vs the reference exceeds this ...
    value_z=3.0,         # ... and is this many standard errors from zero
    seat_margin=0.05,    # flag if value going first and going second differ by this ...
    seat_z=3.0,          # ... with this many standard errors
)


@dataclass
class AblationStat:
    label: str
    value: float          # mean over both seats of (baseline - ablated)
    se: float
    z: float
    ci: tuple
    value_first: float    # value when the owner is seat 1
    se_first: float
    value_second: float   # value when the owner is seat 2
    se_second: float
    seat_gap: float       # value_first - value_second
    seat_gap_z: float


@dataclass
class AblationReport:
    game: str
    agent: str
    reference: str
    n_seeds: int
    baseline_seat0: float
    cards: list = field(default_factory=list)
    issues: list = field(default_factory=list)   # (kind, subject, message)

    def to_dict(self):
        return asdict(self)

    def has(self, kind, subject=None):
        return any(k == kind and (subject is None or s == subject)
                   for k, s, _ in self.issues)


def _mean_se(xs):
    m = statistics.fmean(xs)
    se = statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else float("inf")
    return m, se


def _z(value, se):
    return value / se if se > 0 else (0.0 if value == 0 else math.copysign(math.inf, value))


def ablation_jobs(game_name, params, agent, labels, reference, n_seeds, base_seed=0):
    """Baseline jobs first (one per seed), then for each card two jobs per seed:
    the card ablated in seat 0, then in seat 1."""
    seats = [agent, agent]
    jobs = [(game_name, dict(params), seats, base_seed + k) for k in range(n_seeds)]
    for label in labels:
        for k in range(n_seeds):
            for seat in (0, 1):
                jobs.append((game_name, dict(params), seats, base_seed + k,
                             (seat, label, reference)))
    return jobs


def run_ablation(game_name, params, labels, agent="greedy", reference="ember",
                 n_seeds=500, base_seed=70_000, workers=None, sim=None,
                 thresholds=None) -> AblationReport:
    t = dict(DEFAULT_ABLATION_THRESHOLDS)
    t.update(thresholds or {})
    if reference not in labels:
        raise ValueError(f"Reference card '{reference}' is not one of {labels}")
    cards = [c for c in labels if c != reference]
    jobs = ablation_jobs(game_name, params, agent, cards, reference, n_seeds, base_seed)
    if sim is None:
        with Simulator(workers) as s:
            recs = s.play(jobs)
    else:
        recs = sim.play(jobs)

    base, rest = recs[:n_seeds], recs[n_seeds:]
    base_res = [(r.result(0), r.result(1)) for r in base]
    rep = AblationReport(game_name, agent, reference, n_seeds,
                         statistics.fmean(b[0] for b in base_res))

    for i, label in enumerate(cards):
        chunk = rest[i * 2 * n_seeds:(i + 1) * 2 * n_seeds]
        d_first, d_second = [], []
        for k in range(n_seeds):
            abl0, abl1 = chunk[2 * k], chunk[2 * k + 1]
            d_first.append(base_res[k][0] - abl0.result(0))
            d_second.append(base_res[k][1] - abl1.result(1))
        v, se = _mean_se(d_first + d_second)
        v1, se1 = _mean_se(d_first)
        v2, se2 = _mean_se(d_second)
        gap = v1 - v2
        gap_z = _z(gap, math.sqrt(se1 ** 2 + se2 ** 2))
        st = AblationStat(label, v, se, _z(v, se), (v - 1.96 * se, v + 1.96 * se),
                          v1, se1, v2, se2, gap, gap_z)
        rep.cards.append(st)

        if v > t["value_margin"] and st.z > t["value_z"]:
            rep.issues.append(("strong", label,
                               f"'{label}' is worth {v:+.1%} win rate over '{reference}' "
                               f"(95% CI {st.ci[0]:+.1%} to {st.ci[1]:+.1%})."))
        elif v < -t["value_margin"] and st.z < -t["value_z"]:
            rep.issues.append(("weak", label,
                               f"'{label}' is worth {v:+.1%} vs '{reference}': you would "
                               f"do better with '{reference}' in its place."))
        if abs(gap) > t["seat_margin"] and abs(gap_z) > t["seat_z"]:
            who = "first" if gap > 0 else "second"
            rep.issues.append(("seat_card", label,
                               f"'{label}' is much stronger going {who}: worth "
                               f"{v1:+.1%} as seat 1 vs {v2:+.1%} as seat 2."))
    rep.cards.sort(key=lambda c: -c.value)
    return rep


def format_ablation(rep: AblationReport) -> str:
    out = [f"=== Card ablation: {rep.game} / {rep.agent} self-play ===",
           f"Each card is replaced by '{rep.reference}' in one player's deck; "
           f"{rep.n_seeds} paired seeds per seat.",
           f"Baseline seat 1 score: {rep.baseline_seat0:.1%}",
           "",
           f"  {'card':<10}{'value':>8}{'95% CI':>18}{'z':>7}"
           f"{'as seat 1':>11}{'as seat 2':>11}{'gap z':>7}"]
    for c in rep.cards:
        out.append(f"  {c.label:<10}{c.value:>+8.1%}"
                   f"{f'{c.ci[0]:+.1%} to {c.ci[1]:+.1%}':>18}{c.z:>7.1f}"
                   f"{c.value_first:>+11.1%}{c.value_second:>+11.1%}{c.seat_gap_z:>7.1f}")
    out += ["", "Issues"]
    if rep.issues:
        out += [f"  [{k}] {m}" for k, _, m in rep.issues]
    else:
        out.append("  None detected at current thresholds.")
    return "\n".join(out)
