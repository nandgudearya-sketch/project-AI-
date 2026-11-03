"""The evaluation from the proposal, as runnable experiments.

1. Planted imbalances: does the analyzer flag each one, and stay quiet on the
   control (default) game?
2. Agent sanity: does skill increase with search budget? Do strong agents
   recover a known theoretical answer (Nim)? Human play is tested separately
   with ``python -m balancer play``.
3. Before/after: does the tuner fix a planted imbalance, verified on fresh seeds?
"""
from __future__ import annotations

from ..analysis.balance import analyze, wilson
from ..games import GAMES, make_game
from ..sim.harness import Simulator, agent_score
from ..tune.tuner import TuneConfig, format_tune, tune

PLANTED_CASES = [
    # (preset, expected issue kind, expected subject or None)
    ("default", None, None),
    ("planted_seat", "seat", "first"),
    ("planted_card", "dominant", "flare"),
    ("planted_engine", "dominant", "hearth"),
    ("planted_dud", "dead", "inferno"),
    ("planted_long", "timeout", None),
]


def planted_detection(agents=("greedy", "greedy"), n_games=2000, workers=None, log=print):
    cls = GAMES["ember"]
    labels = cls().all_action_labels()
    rows = []
    with Simulator(workers) as sim:
        for preset, kind, subject in PLANTED_CASES:
            params = cls.preset_params(preset)
            rep = analyze(sim.match("ember", params, list(agents), n_games, 11), labels)
            found = [(i.kind, i.subject) for i in rep.issues]
            if kind is None:
                ok = not found
            else:
                ok = rep.has(kind, subject)
            others = [f for f in found if not (f[0] == kind and (subject is None or f[1] == subject))]
            rows.append(dict(preset=preset, expected=(kind, subject), detected=ok,
                             other_findings=others))
            if log:
                exp = "nothing (control)" if kind is None else f"{kind}:{subject or '*'}"
                log(f"  {preset:<16} expect {exp:<22} -> {'PASS' if ok else 'FAIL'}"
                    + (f"   also flagged: {others}" if others else ""))
    return rows


def agent_ladder(game_name="ember", params=None,
                 ladder=("random", "mcts:25", "mcts:100", "mcts:400"),
                 references=(("mcts:400", "greedy"),), n_games=60, workers=None, log=print):
    """Each rung of the ladder plays the one below it; skill should increase with
    search budget. ``references`` adds extra pairings (e.g. against greedy)."""
    params = params or GAMES[game_name].preset_params()
    rows = []
    pairs = list(zip(ladder[1:], ladder)) + list(references)
    with Simulator(workers) as sim:
        for strong, weak in pairs:
            recs = sim.match(game_name, params, [strong, weak], n_games, 21)
            tot, cnt = agent_score(recs, strong)
            ci = wilson(tot, cnt)
            rows.append(dict(strong=strong, weak=weak, score=tot / cnt, ci=ci))
            if log:
                log(f"  {strong:<10} vs {weak:<10} {tot / cnt:6.1%}  "
                    f"(CI {ci[0]:.1%}-{ci[1]:.1%})  {'PASS' if ci[0] > 0.5 else 'unclear'}")
    return rows


def nim_theory_check(agent="mcts:1000", n_games=40, workers=None, log=print):
    """Nim with pile % (max_take+1) != 0 is a first-player win under perfect play,
    and a second-player win otherwise. Strong self-play should recover this."""
    rows = []
    with Simulator(workers) as sim:
        for pile in (13, 12):
            params = {"pile": pile, "max_take": 3}
            expected = 0 if pile % 4 else 1   # max_take 3 -> losing piles are multiples of 4
            recs = sim.match("nim", params, [agent, agent], n_games, 0)
            seat0 = sum(r.result(0) for r in recs) / len(recs)
            ok = (seat0 > 0.8) if expected == 0 else (seat0 < 0.2)
            rows.append(dict(pile=pile, expected_winner=expected + 1, seat1_score=seat0, ok=ok))
            if log:
                log(f"  pile {pile}: theory says seat {expected + 1} wins; "
                    f"seat 1 scored {seat0:.0%} -> {'PASS' if ok else 'FAIL'}")
    return rows


def before_after(workers=None, log=print, games=600, verify_games=3000):
    """Tune the planted seat imbalance and verify the fix on fresh seeds."""
    params = GAMES["ember"].preset_params("planted_seat")
    cfg = TuneConfig(tunables=["p2_start_points", "p2_extra_cards"], games=games,
                     iterations=15, verify_games=verify_games)
    res = tune("ember", params, cfg, workers=workers, log=log)
    if log:
        log(format_tune(res))
    return res


def run_all(workers=None, quick=False, log=print):
    scale = 0.25 if quick else 1.0
    log("\n[1] Planted imbalance detection (greedy self-play)")
    planted_detection(n_games=int(2000 * scale), workers=workers, log=log)
    log("\n[2a] Agent skill ladder (Ember Duel)")
    agent_ladder(n_games=max(40, int(120 * scale)), workers=workers, log=log)
    log("\n[2b] Known-answer check (Nim)")
    nim_theory_check(n_games=max(10, int(40 * scale)), workers=workers, log=log)
    log("\n[3] Before/after tuning of the planted seat imbalance")
    before_after(workers=workers, log=log, games=int(600 * scale),
                 verify_games=int(3000 * scale))
