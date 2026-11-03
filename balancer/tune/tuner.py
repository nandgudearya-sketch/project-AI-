"""Proposing parameter changes that reduce imbalance, then verifying them.

The objective combines the balance report's findings into one number (lower is
fairer). Noise handling, which is the crux of tuning from simulations:

* Common random numbers: every candidate is evaluated on the same seeds, so
  differences come from the parameters rather than from luckier deals.
* Noise-aware card term: a card's opening-hand lift only counts beyond one
  standard error, so the tuner does not chase noise.
* Held-out verification: the final proposal is re-tested on fresh seeds with
  more games. The tuner only reports success if the improvement holds there.

Search is (1+lambda) hill climbing over integer parameters with a small
penalty per changed parameter, so it prefers minimal edits a designer can
actually make.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..analysis.balance import BalanceReport, analyze
from ..games import GAMES, make_game
from ..sim.harness import Simulator


@dataclass
class TuneConfig:
    tunables: list
    agents: tuple = ("greedy", "greedy")
    games: int = 800
    iterations: int = 25
    neighbors: int = 6
    patience: int = 6
    seed: int = 0
    w_seat: float = 4.0
    w_card: float = 1.0
    w_dead: float = 0.5
    w_timeout: float = 1.0
    w_change: float = 0.01
    verify_games: int = 3000


def imbalance(rep: BalanceReport, n_changed: int, cfg: TuneConfig,
              dead_rate: float = 0.10) -> dict:
    seat = abs(rep.seat0_score - 0.5)
    # Sum (not mean) so a single mispriced card is not diluted by fair ones;
    # subtract one standard error so pure noise contributes little.
    card = sum(max(0.0, abs(c.lift) - c.se) for c in rep.cards if c.se != float("inf"))
    dead = (sum(c.play_rate < dead_rate for c in rep.cards) / len(rep.cards)
            if rep.cards else 0.0)
    parts = {
        "seat": cfg.w_seat * seat,
        "cards": cfg.w_card * card,
        "dead": cfg.w_dead * dead,
        "timeout": cfg.w_timeout * rep.timeout_rate,
        "changes": cfg.w_change * n_changed,
    }
    parts["total"] = sum(parts.values())
    return parts


@dataclass
class TuneResult:
    base_params: dict
    best_params: dict
    changes: dict
    history: list
    base_report: BalanceReport
    best_report: BalanceReport
    base_score: dict
    best_score: dict
    verified: bool
    notes: list = field(default_factory=list)


def _changed(base, params, tunables):
    return {k: (base[k], params[k]) for k in tunables if params[k] != base[k]}


def tune(game_name, base_params, cfg: TuneConfig, workers=None, log=print) -> TuneResult:
    cls = GAMES[game_name]
    for k in cfg.tunables:
        if k not in cls.PARAM_SPACE:
            raise ValueError(f"'{k}' is not tunable. Tunable: {sorted(cls.PARAM_SPACE)}")
    rng = random.Random(cfg.seed)
    labels = make_game(game_name, base_params).all_action_labels()
    train_seed = 3_000_000 + cfg.seed * 10_000
    cache = {}

    def evaluate(sim, params, seed, n_games):
        key = (tuple(sorted(params.items())), seed, n_games)
        if key not in cache:
            recs = sim.match(game_name, params, list(cfg.agents), n_games, seed)
            rep = analyze(recs, labels)
            n_ch = len(_changed(base_params, params, cfg.tunables))
            cache[key] = (imbalance(rep, n_ch, cfg), rep)
        return cache[key]

    def neighbour(params):
        for _ in range(50):
            cand = dict(params)
            for k in rng.sample(cfg.tunables, min(len(cfg.tunables), rng.choice([1, 1, 2]))):
                lo, hi = cls.PARAM_SPACE[k]
                step = rng.choice([-1, 1]) * (2 if hi - lo > 10 and rng.random() < 0.3 else 1)
                cand[k] = max(lo, min(hi, cand[k] + step))
            if cand != params:
                try:
                    make_game(game_name, cand)
                    return cand
                except ValueError:
                    continue
        return None

    history = []
    with Simulator(workers) as sim:
        current = dict(base_params)
        cur_score, _ = evaluate(sim, current, train_seed, cfg.games)
        history.append({"iteration": 0, "objective": cur_score["total"], "changes": {}})
        if log:
            log(f"  start: objective {cur_score['total']:.4f}")
        stale = 0
        for it in range(1, cfg.iterations + 1):
            cands = [c for c in (neighbour(current) for _ in range(cfg.neighbors)) if c]
            scored = [(evaluate(sim, c, train_seed, cfg.games)[0]["total"], i, c)
                      for i, c in enumerate(cands)]
            if not scored:
                break
            best_total, _, best_c = min(scored)
            if best_total < cur_score["total"] - 1e-9:
                current = best_c
                cur_score, _ = evaluate(sim, current, train_seed, cfg.games)
                stale = 0
                ch = _changed(base_params, current, cfg.tunables)
                history.append({"iteration": it, "objective": cur_score["total"],
                                "changes": ch})
                if log:
                    pretty = ", ".join(f"{k} {a}->{b}" for k, (a, b) in ch.items())
                    log(f"  iter {it}: objective {cur_score['total']:.4f}  [{pretty}]")
            else:
                stale += 1
                if stale >= cfg.patience:
                    if log:
                        log(f"  no improvement for {cfg.patience} iterations; stopping")
                    break

        verify_seed = 7_000_000 + cfg.seed * 10_000
        base_score, base_rep = evaluate(sim, dict(base_params), verify_seed, cfg.verify_games)
        best_score, best_rep = evaluate(sim, current, verify_seed, cfg.verify_games)

    changes = _changed(base_params, current, cfg.tunables)
    verified = bool(changes) and best_score["total"] < base_score["total"]
    notes = []
    if not changes:
        notes.append("The tuner found no change that improved balance on the training seeds.")
    elif not verified:
        notes.append("The proposed change improved the training seeds but NOT the fresh "
                     "verification seeds; treat it as noise, not a fix.")
    notes.append(f"Results hold for agents {', '.join(cfg.agents)}. Balance can differ at "
                 f"other skill levels, so re-verify with stronger agents before printing.")
    return TuneResult(dict(base_params), current, changes, history, base_rep, best_rep,
                      base_score, best_score, verified, notes)


def format_tune(res: TuneResult) -> str:
    out = ["=== Tuning result ==="]
    if res.changes:
        out.append("Proposed changes:")
        for k, (a, b) in res.changes.items():
            out.append(f"  {k}: {a} -> {b}")
    else:
        out.append("No changes proposed.")

    def row(name, a, b, pct=True):
        f = (lambda x: f"{x:.1%}") if pct else (lambda x: f"{x:.4f}")
        return f"  {name:<26}{f(a):>12}{f(b):>12}"

    br, ar = res.base_report, res.best_report
    out += ["", f"Verification on fresh seeds ({br.n_games} games each):",
            f"  {'':<26}{'before':>12}{'after':>12}",
            row("seat 1 score", br.seat0_score, ar.seat0_score),
            f"  {'  95% CI':<26}{br.seat0_ci[0]:.1%}-{br.seat0_ci[1]:.1%}".ljust(40)
            + f"{ar.seat0_ci[0]:.1%}-{ar.seat0_ci[1]:.1%}".rjust(12),
            row("max |card lift|", max((abs(c.lift) for c in br.cards), default=0),
                max((abs(c.lift) for c in ar.cards), default=0)),
            row("hit turn limit", br.timeout_rate, ar.timeout_rate),
            f"  {'issues flagged':<26}{len(br.issues):>12}{len(ar.issues):>12}",
            row("objective (lower=fairer)", res.base_score["total"],
                res.best_score["total"], pct=False),
            "",
            "VERIFIED: the improvement holds on held-out seeds." if res.verified
            else "NOT VERIFIED."]
    out += [f"Note: {n}" for n in res.notes]
    if ar.issues:
        out += ["", "Remaining issues after the change:"]
        out += [f"  [{i.kind}] {i.message}" for i in ar.issues]
    return "\n".join(out)
