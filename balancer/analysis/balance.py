"""Turns game records into a balance report with flagged issues."""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field

from ..sim.harness import Simulator, agent_score

DEFAULT_THRESHOLDS = dict(
    seat_tolerance=0.02,    # flag seat advantage if the CI lies outside 50% +/- this
    card_lift=0.10,         # flag a card whose win-rate lift exceeds this ...
    card_z=3.0,             # ... and is this many standard errors from zero
    dead_play_rate=0.10,    # flag a card played in fewer than 10% of player-games
    min_samples=30,
    timeout_rate=0.10,      # flag if more than 10% of games hit the turn cap
    short_game_turns=4,     # flag if the median game is this short
    luck_threshold=0.65,    # flag if a strong agent beats a weak one less often
)


def wilson(k: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion (works for fractional k from draws)."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    adj = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - adj) / denom, (centre + adj) / denom)


@dataclass
class Issue:
    kind: str          # seat | dominant | weak | dead | timeout | short | luck | strategy
    subject: str
    severity: float    # rough effect size, for sorting
    message: str


@dataclass
class CardStat:
    label: str
    play_rate: float      # fraction of player-games in which it was played at least once
    avg_copies: float     # mean times played per player-game
    wr_played: float      # descriptive only: confounded by who survives to play it
    oh_rate: float        # fraction of player-games starting with it in the opening hand
    n_oh: int
    wr_oh: float          # win rate when in the opening hand
    n_not: int
    wr_not: float         # win rate when not in the opening hand
    lift: float           # wr_oh - wr_not: randomized, so a causal strength estimate
    se: float
    z: float


@dataclass
class BalanceReport:
    n_games: int
    seats: list
    seat0_score: float
    seat0_ci: tuple
    seat_wins: list
    draws: int
    agent_scores: dict
    length_mean: float
    length_p10: float
    length_p50: float
    length_p90: float
    timeout_rate: float
    cards: list = field(default_factory=list)
    issues: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

    def has(self, kind, subject=None):
        return any(i.kind == kind and (subject is None or i.subject == subject)
                   for i in self.issues)


def _quantile(sorted_vals, q):
    if not sorted_vals:
        return 0.0
    idx = min(len(sorted_vals) - 1, max(0, int(round(q * (len(sorted_vals) - 1)))))
    return float(sorted_vals[idx])


def analyze(records, labels, thresholds=None) -> BalanceReport:
    t = dict(DEFAULT_THRESHOLDS)
    t.update(thresholds or {})
    n = len(records)
    if n == 0:
        raise ValueError("No records to analyze")
    issues: list[Issue] = []

    # ---------------------------------------------------------- seat advantage
    wins = [0, 0]
    draws = 0
    for r in records:
        if r.winner is None:
            draws += 1
        else:
            wins[r.winner] += 1
    k0 = wins[0] + 0.5 * draws
    seat0 = k0 / n
    ci = wilson(k0, n)
    tol = t["seat_tolerance"]
    if ci[0] > 0.5 + tol or ci[1] < 0.5 - tol:
        who = "first" if seat0 > 0.5 else "second"
        issues.append(Issue(
            "seat", who, abs(seat0 - 0.5),
            f"The {who} player has an advantage: seat 1 scores {seat0:.1%} "
            f"(95% CI {ci[0]:.1%}-{ci[1]:.1%}) over {n} games."))

    # ------------------------------------------------------------ per agent
    specs = sorted({s for r in records for s in r.seats})
    agent_scores = {}
    for spec in specs:
        tot, cnt = agent_score(records, spec)
        agent_scores[spec] = {"score": tot / cnt if cnt else 0.0,
                              "ci": wilson(tot, cnt), "games": cnt}

    # ------------------------------------------------------------ cards
    # Strength uses the opening hand: which cards you start with is decided by
    # the shuffle, so "had it vs didn't" is a randomized comparison. Win rate
    # when *played* is shown for reference but is confounded (cards that need
    # many turns are only played by players who survive that long).
    cards = []
    player_games = n * len(records[0].seats)
    for label in labels:
        n_play = copies = 0
        w_play = 0.0
        n_oh = n_not = 0
        w_oh = w_not = 0.0
        for r in records:
            for seat in range(len(r.seats)):
                res = r.result(seat)
                c = r.plays[seat].get(label, 0)
                copies += c
                if c > 0:
                    n_play += 1
                    w_play += res
                if r.opening and label in r.opening[seat]:
                    n_oh += 1
                    w_oh += res
                else:
                    n_not += 1
                    w_not += res
        wr_oh = w_oh / n_oh if n_oh else float("nan")
        wr_not = w_not / n_not if n_not else float("nan")
        if n_oh and n_not:
            lift = wr_oh - wr_not
            pooled = (w_oh + w_not) / (n_oh + n_not)
            se = math.sqrt(max(pooled * (1 - pooled), 1e-9) * (1 / n_oh + 1 / n_not))
            z = lift / se
        else:
            lift, se, z = 0.0, float("inf"), 0.0
        cs = CardStat(label, n_play / player_games, copies / player_games,
                      w_play / n_play if n_play else float("nan"),
                      n_oh / player_games, n_oh, wr_oh, n_not, wr_not, lift, se, z)
        cards.append(cs)

        enough = n_oh >= t["min_samples"] and n_not >= t["min_samples"]
        if cs.play_rate < t["dead_play_rate"]:
            issues.append(Issue(
                "dead", label, t["dead_play_rate"] - cs.play_rate,
                f"'{label}' is almost never used: played in only {cs.play_rate:.1%} "
                f"of player-games. It may be too expensive or too weak."))
        elif enough and lift > t["card_lift"] and z > t["card_z"]:
            issues.append(Issue(
                "dominant", label, lift,
                f"'{label}' looks overpowered: starting with it raises win rate "
                f"from {wr_not:.1%} to {wr_oh:.1%} (lift {lift:+.1%}, z={z:.1f})."))
        elif enough and lift < -t["card_lift"] and z < -t["card_z"]:
            issues.append(Issue(
                "weak", label, -lift,
                f"'{label}' looks underpowered: starting with it lowers win rate "
                f"from {wr_not:.1%} to {wr_oh:.1%} (lift {lift:+.1%}, z={z:.1f})."))

    # ------------------------------------------------------------ length
    lengths = sorted(r.turns for r in records)
    timeout_rate = sum(r.timed_out for r in records) / n
    p50 = _quantile(lengths, 0.5)
    if timeout_rate > t["timeout_rate"]:
        issues.append(Issue(
            "timeout", "length", timeout_rate,
            f"{timeout_rate:.1%} of games hit the turn limit instead of ending "
            f"naturally. The game may run too long."))
    if p50 <= t["short_game_turns"]:
        issues.append(Issue(
            "short", "length", 1.0 / max(p50, 1),
            f"The median game lasts only {p50:.0f} turns; it may be decided too fast."))

    issues.sort(key=lambda i: -i.severity)
    return BalanceReport(
        n_games=n, seats=specs, seat0_score=seat0, seat0_ci=ci, seat_wins=wins,
        draws=draws, agent_scores=agent_scores,
        length_mean=statistics.fmean(lengths), length_p10=_quantile(lengths, 0.1),
        length_p50=p50, length_p90=_quantile(lengths, 0.9),
        timeout_rate=timeout_rate, cards=cards, issues=issues)


def skill_gap(game_name, params, strong="mcts:200", weak="random", n_games=200,
              base_seed=50_000, workers=None, sim=None, thresholds=None):
    """How often a strong agent beats a weak one. If skill barely matters, the
    game is mostly decided by luck."""
    t = dict(DEFAULT_THRESHOLDS)
    t.update(thresholds or {})
    if sim is None:
        with Simulator(workers) as s:
            recs = s.match(game_name, params, [strong, weak], n_games, base_seed)
    else:
        recs = sim.match(game_name, params, [strong, weak], n_games, base_seed)
    tot, cnt = agent_score(recs, strong)
    score, ci = tot / cnt, wilson(tot, cnt)
    issue = None
    if ci[1] < t["luck_threshold"]:
        issue = Issue("luck", "skill", t["luck_threshold"] - score,
                      f"Skill matters little: {strong} beats {weak} only {score:.1%} "
                      f"of the time (95% CI {ci[0]:.1%}-{ci[1]:.1%}). The outcome "
                      f"may be dominated by luck.")
    return {"strong": strong, "weak": weak, "score": score, "ci": ci,
            "games": cnt, "issue": issue}


def format_report(rep: BalanceReport, title="Balance report") -> str:
    out = [f"=== {title} ===",
           f"Games: {rep.n_games}   Agents: {', '.join(rep.seats)}",
           "",
           "Seat advantage",
           f"  Seat 1 wins {rep.seat_wins[0]}, seat 2 wins {rep.seat_wins[1]}, "
           f"draws {rep.draws}",
           f"  Seat 1 score {rep.seat0_score:.1%} "
           f"(95% CI {rep.seat0_ci[0]:.1%}-{rep.seat0_ci[1]:.1%})"]
    if len(rep.agent_scores) > 1:
        out += ["", "Agents"]
        for spec, a in rep.agent_scores.items():
            out.append(f"  {spec:<28} {a['score']:.1%} "
                       f"(CI {a['ci'][0]:.1%}-{a['ci'][1]:.1%}, {a['games']} games)")
    out += ["", "Game length (turns)",
            f"  mean {rep.length_mean:.1f}   p10 {rep.length_p10:.0f}   "
            f"median {rep.length_p50:.0f}   p90 {rep.length_p90:.0f}   "
            f"hit turn limit {rep.timeout_rate:.1%}"]
    if rep.cards:
        out += ["", "Cards (strength = opening-hand lift, a randomized comparison)",
                f"  {'name':<10}{'played':>8}{'copies':>8}{'win|play':>10}"
                f"{'in OH':>8}{'win|OH':>9}{'win|¬OH':>9}{'lift':>8}{'z':>7}"]
        for c in sorted(rep.cards, key=lambda c: -c.lift):
            fmt = lambda x: "    -" if math.isnan(x) else f"{x:.1%}"
            out.append(f"  {c.label:<10}{c.play_rate:>8.1%}{c.avg_copies:>8.2f}"
                       f"{fmt(c.wr_played):>10}{c.oh_rate:>8.1%}{fmt(c.wr_oh):>9}"
                       f"{fmt(c.wr_not):>9}{c.lift:>+8.1%}{c.z:>7.1f}")
    out += ["", "Issues"]
    if rep.issues:
        for i in rep.issues:
            out.append(f"  [{i.kind}] {i.message}")
    else:
        out.append("  None detected at current thresholds.")
    return "\n".join(out)
