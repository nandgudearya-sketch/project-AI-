"""Search for parameter changes that fix the planted imbalances, then verify them.

Examples:
    python run_optimizer.py                      # quick run
    python run_optimizer.py --steps 80 --method anneal
"""
import argparse
import copy

from balance_tool.agents import GreedyAgent
from balance_tool.card_duel import DEFAULT_PARAMS
from balance_tool.optimizer import (DEFAULT_SEARCH_SPACE, get_param, optimize,
                                    print_verification, verify)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=40)
    ap.add_argument("--method", default="hill", choices=["hill", "anneal"])
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--swap-games", type=int, default=150)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    start = copy.deepcopy(DEFAULT_PARAMS)
    agent = GreedyAgent()
    best, best_loss = optimize(start, agent, method=args.method, steps=args.steps,
                               games=args.games, swap_games=args.swap_games, seed=args.seed)
    changes = {}
    for key in DEFAULT_SEARCH_SPACE:
        a, b = get_param(start, key), get_param(best, key)
        if a != b:
            changes[key] = (a, b)
    rows = verify(start, best, agent)
    print_verification(rows, changes)


if __name__ == "__main__":
    main()
