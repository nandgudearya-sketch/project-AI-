"""Command-line interface.  Run ``python -m balancer --help``."""
from __future__ import annotations

import argparse
import json
import random
import sys
import time

from .agents import make_agent
from .analysis import analyze, format_report, skill_gap
from .games import GAMES, make_game
from .search import card_focus_probe, format_ga, format_probe, ga_search
from .sim import Simulator, play_game
from .tune import TuneConfig, format_tune, tune


def _params(args) -> dict:
    cls = GAMES[args.game]
    params = cls.preset_params(args.preset)
    for kv in args.set or []:
        k, _, v = kv.partition("=")
        if k not in params:
            sys.exit(f"Unknown parameter '{k}'. Use 'list' to see parameters.")
        params[k] = type(params[k])(float(v)) if isinstance(params[k], (int, float)) else v
    make_game(args.game, params)  # validate
    return params


def _common(p):
    p.add_argument("--game", default="ember", choices=sorted(GAMES))
    p.add_argument("--preset", default="default", help="parameter preset (see 'list')")
    p.add_argument("--set", nargs="*", metavar="KEY=VALUE",
                   help="override parameters, e.g. --set flare.cost=2 target_points=35")
    p.add_argument("--workers", type=int, default=None, help="processes (default: all CPUs)")
    p.add_argument("--seed", type=int, default=0)


def cmd_list(args):
    for name, cls in GAMES.items():
        print(f"{name}: presets = default, {', '.join(cls.PRESETS) or '-'}")
        print("  parameters:")
        for k, v in cls.DEFAULT_PARAMS.items():
            rng = cls.PARAM_SPACE.get(k)
            print(f"    {k:<28}{v!s:>6}   {'tunable ' + str(rng) if rng else ''}")


def cmd_simulate(args):
    params = _params(args)
    labels = make_game(args.game, params).all_action_labels()
    t = time.time()
    with Simulator(args.workers) as sim:
        recs = sim.match(args.game, params, args.agents, args.games, args.seed)
        luck = None
        if args.luck:
            luck = skill_gap(args.game, params, args.strong, "random", args.luck_games, sim=sim)
    rep = analyze(recs, labels)
    print(format_report(rep, f"{args.game} / {args.preset} / {' vs '.join(args.agents)}"))
    if luck:
        print(f"\nSkill vs luck: {luck['strong']} beats random {luck['score']:.1%} "
              f"(CI {luck['ci'][0]:.1%}-{luck['ci'][1]:.1%})")
        if luck["issue"]:
            print(f"  [luck] {luck['issue'].message}")
    print(f"\n({len(recs)} games in {time.time() - t:.1f}s)")
    if args.json:
        with open(args.json, "w") as f:
            json.dump({"params": params, "report": rep.to_dict(), "luck": luck},
                      f, indent=2, default=str)
        print(f"Saved {args.json}")


def cmd_probe(args):
    res = card_focus_probe(args.game, _params(args), args.opponent, args.games,
                           workers=args.workers)
    print(format_probe(res))


def cmd_search(args):
    print("Evolving strategies...")
    res = ga_search(args.game, _params(args), tuple(args.opponents), args.pop,
                    args.generations, args.games, seed=args.seed, workers=args.workers,
                    verify_games=args.verify_games)
    print(format_ga(res))


def cmd_tune(args):
    params = _params(args)
    cfg = TuneConfig(tunables=args.params, agents=tuple(args.agents), games=args.games,
                     iterations=args.iterations, seed=args.seed,
                     verify_games=args.verify_games)
    print(f"Tuning {', '.join(args.params)} ...")
    res = tune(args.game, params, cfg, workers=args.workers)
    print(format_tune(res))


def cmd_play(args):
    game = make_game(args.game, _params(args))
    seat = args.seat - 1
    agents = [None, None]
    agents[seat] = make_agent("human")
    agents[1 - seat] = make_agent(args.opponent)
    seed = args.seed or random.randrange(10**6)
    rec = play_game(game, agents, seed)
    print("\n=== Game over ===")
    print(f"Final scores: {rec.scores}")
    if rec.winner is None:
        print("Draw.")
    else:
        print("You win!" if rec.winner == seat else f"{args.opponent} wins.")


def cmd_evaluate(args):
    from .evaluation import run_all
    run_all(workers=args.workers, quick=args.quick)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="balancer",
                                 description="Automated playtesting and balance tuning")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="show games, presets and parameters")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("simulate", help="play many games and print a balance report")
    _common(p)
    p.add_argument("--agents", nargs=2, default=["greedy", "greedy"])
    p.add_argument("--games", type=int, default=2000)
    p.add_argument("--luck", action="store_true", help="also measure skill vs luck")
    p.add_argument("--strong", default="mcts:200")
    p.add_argument("--luck-games", type=int, default=100)
    p.add_argument("--json", help="save the report as JSON")
    p.set_defaults(fn=cmd_simulate)

    p = sub.add_parser("probe", help="card-focus probe for dominant strategies")
    _common(p)
    p.add_argument("--opponent", default="greedy")
    p.add_argument("--games", type=int, default=300)
    p.set_defaults(fn=cmd_probe)

    p = sub.add_parser("search", help="genetic search for dominant strategies")
    _common(p)
    p.add_argument("--opponents", nargs="+", default=["greedy"])
    p.add_argument("--pop", type=int, default=16)
    p.add_argument("--generations", type=int, default=8)
    p.add_argument("--games", type=int, default=40, help="games per evaluation")
    p.add_argument("--verify-games", type=int, default=400)
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("tune", help="propose and verify parameter changes")
    _common(p)
    p.add_argument("--params", nargs="+", required=True, help="parameters the tuner may change")
    p.add_argument("--agents", nargs=2, default=["greedy", "greedy"])
    p.add_argument("--games", type=int, default=800, help="games per candidate")
    p.add_argument("--iterations", type=int, default=25)
    p.add_argument("--verify-games", type=int, default=3000)
    p.set_defaults(fn=cmd_tune)

    p = sub.add_parser("play", help="play against an agent in the terminal")
    _common(p)
    p.add_argument("--opponent", default="mcts:200")
    p.add_argument("--seat", type=int, choices=[1, 2], default=1)
    p.set_defaults(fn=cmd_play)

    p = sub.add_parser("evaluate", help="run the full evaluation suite")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--quick", action="store_true")
    p.set_defaults(fn=cmd_evaluate)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
