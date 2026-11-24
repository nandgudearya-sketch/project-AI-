"""Searching for dominant strategies.

Two tools:

Strategies are "biased greedy" agents (see ``WeightedAgent``): the greedy turn
planner plus a bonus or penalty per card. All-zero weights is plain greedy, so a
strategy that beats greedy has found a better way to value the cards than the
game's own heuristic, which usually means a card is mispriced.

* ``card_focus_probe``: cheap and interpretable. For each card, a strategy that
  strongly favours that card plays plain greedy. A card whose focus strategy
  wins clearly more than 50% is a candidate for a dominant strategy.

* ``ga_search``: a genetic algorithm over the full weight vector. It looks for
  any combination of preferences (favour X, avoid Y) that beats a pool of
  opponents, which can find combinations human testers would not try.

Both use common random numbers (the same seeds for every candidate within a
generation) so candidates are compared on identical deals, and both verify
their final answer on fresh seeds.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..agents import encode_weights
from ..analysis.balance import Issue, wilson
from ..games import make_game
from ..sim.harness import Simulator, agent_score, match_jobs


def _score_many(sim, game_name, params, specs, opponents, n_games, seed):
    """Score every spec against every opponent in one parallel batch."""
    jobs, slices = [], []
    for spec in specs:
        start = len(jobs)
        for j, opp in enumerate(opponents):
            jobs += match_jobs(game_name, params, [spec, opp], n_games, seed + 7919 * j)
        slices.append((start, len(jobs)))
    records = sim.play(jobs)
    out = []
    for spec, (a, b) in zip(specs, slices):
        tot, cnt = agent_score(records[a:b], spec)
        out.append((tot, cnt))
    return out


@dataclass
class ProbeResult:
    opponent: str
    baseline: float
    baseline_ci: tuple
    rows: list = field(default_factory=list)      # (label, score, ci, delta)
    issues: list = field(default_factory=list)


def card_focus_probe(game_name, params, opponent="greedy", n_games=300, seed=900_000,
                     workers=None, margin=0.05, sim=None) -> ProbeResult:
    labels = make_game(game_name, params).all_action_labels()
    specs = []
    for l in labels:
        w = {x: 0.0 for x in labels}
        w[l] = 1.0
        specs.append(encode_weights(w))

    def run(s):
        return _score_many(s, game_name, params, specs, [opponent], n_games, seed)

    if sim is None:
        with Simulator(workers) as s:
            scores = run(s)
    else:
        scores = run(sim)
    res = ProbeResult(opponent, 0.5, (0.5, 0.5))
    for l, (tot, cnt) in zip(labels, scores):
        sc = tot / cnt
        ci = wilson(tot, cnt)
        res.rows.append((l, sc, ci, sc - 0.5))
        if sc - 0.5 > margin and ci[0] > 0.5:
            res.issues.append(Issue(
                "strategy", l, sc - 0.5,
                f"Favouring '{l}' beats {opponent} {sc:.1%} of the time "
                f"(CI {ci[0]:.1%}-{ci[1]:.1%}): the card is likely undercosted, or "
                f"stronger than it looks."))
    res.rows.sort(key=lambda r: -r[1])
    return res


def format_probe(res: ProbeResult) -> str:
    out = [f"=== Card focus probe (each strategy favours one card; vs {res.opponent}) ===",
           "A strategy with no bias would score 50%.",
           f"  {'focus card':<12}{'score':>8}{'95% CI':>16}{'vs 50%':>10}"]
    for l, sc, ci, d in res.rows:
        out.append(f"  {l:<12}{sc:>8.1%}   {ci[0]:.1%}-{ci[1]:.1%}{d:>+10.1%}")
    out.append("")
    out += [f"  [{i.kind}] {i.message}" for i in res.issues] or ["  No focus strategy stands out."]
    out.append("  (a focus score well below 50% means over-valuing that card is a mistake,"
               " which is expected for ordinary cards)")
    return "\n".join(out)


@dataclass
class GAResult:
    labels: list
    best_weights: dict
    best_spec: str
    verified_score: float
    verified_ci: tuple
    opponents: list
    history: list
    issues: list = field(default_factory=list)


def ga_search(game_name, params, opponents=("greedy",), pop_size=16, generations=8,
              games_per_eval=40, elite=2, mutation=0.3, seed=0, workers=None,
              verify_games=400, dominance_threshold=0.60, log=print) -> GAResult:
    game = make_game(game_name, params)
    labels = game.all_action_labels()
    if not labels:
        raise ValueError("This game exposes no action labels to build strategies from")
    rng = random.Random(seed)
    clip = lambda x: max(-1.0, min(1.0, x))
    to_spec = lambda v: encode_weights(dict(zip(labels, v)))
    pop = [[rng.uniform(-1, 1) for _ in labels] for _ in range(pop_size)]
    history = []

    with Simulator(workers) as sim:
        best_v, best_f = None, -1.0
        for gen in range(generations):
            gen_seed = 2_000_000 + seed * 10_000 + gen * 500
            scores = _score_many(sim, game_name, params, [to_spec(v) for v in pop],
                                 list(opponents), games_per_eval, gen_seed)
            fits = [t / c for t, c in scores]
            order = sorted(range(pop_size), key=lambda i: -fits[i])
            if fits[order[0]] > best_f:
                best_f, best_v = fits[order[0]], pop[order[0]][:]
            history.append({"generation": gen, "best": fits[order[0]],
                            "mean": sum(fits) / pop_size})
            if log:
                log(f"  gen {gen + 1}/{generations}: best {fits[order[0]]:.1%}, "
                    f"mean {sum(fits) / pop_size:.1%}")

            def pick():
                a, b = rng.sample(range(pop_size), 2)
                return pop[a] if fits[a] >= fits[b] else pop[b]

            nxt = [pop[i][:] for i in order[:elite]]
            while len(nxt) < pop_size:
                p1, p2 = pick(), pick()
                child = [x if rng.random() < 0.5 else y for x, y in zip(p1, p2)]
                child = [clip(x + rng.gauss(0, mutation)) if rng.random() < 0.3 else x
                         for x in child]
                nxt.append(child)
            pop = nxt

        # Fresh seeds, more games: the GA's own fitness is optimistically biased.
        spec = to_spec(best_v)
        (tot, cnt), = _score_many(sim, game_name, params, [spec], list(opponents),
                                  verify_games, 9_000_000 + seed)

    score, ci = tot / cnt, wilson(tot, cnt)
    weights = dict(zip(labels, best_v))
    res = GAResult(labels, weights, spec, score, ci, list(opponents), history)
    if ci[0] > dominance_threshold:
        top = [l for l, _ in sorted(weights.items(), key=lambda kv: -kv[1])[:3]]
        avoid = [l for l, w in weights.items() if w < -0.5]
        msg = (f"Found a strategy that wins {score:.1%} (CI {ci[0]:.1%}-{ci[1]:.1%}) "
               f"against {', '.join(opponents)}: favour {', '.join(top)}")
        if avoid:
            msg += f"; avoid {', '.join(avoid)}"
        res.issues.append(Issue("strategy", "ga", score - 0.5, msg + "."))
    return res


def format_ga(res: GAResult) -> str:
    out = [f"=== Strategy search (vs {', '.join(res.opponents)}) ===",
           f"Verified score on fresh seeds: {res.verified_score:.1%} "
           f"(CI {res.verified_ci[0]:.1%}-{res.verified_ci[1]:.1%})",
           "Card preferences relative to greedy (+ = valued more, - = valued less):"]
    for l, w in sorted(res.best_weights.items(), key=lambda kv: -kv[1]):
        out.append(f"  {l:<12}{w:+.2f}")
    out.append("")
    out += [f"  [{i.kind}] {i.message}" for i in res.issues] or [
        "  No dominant strategy found against this opponent pool. Add stronger "
        "opponents (e.g. --opponents greedy mcts:100) for more rigorous evidence."]
    return "\n".join(out)
