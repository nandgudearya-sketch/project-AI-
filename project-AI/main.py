"""
Run a balance test on Card Duel.

Examples:
    python main.py                         # 2000 greedy-vs-greedy games
    python main.py --agent mcts --games 100
    python main.py --agent random --games 5000
"""

import argparse

from balance_tool.agents import GreedyAgent, MCTSAgent, RandomAgent
from balance_tool.card_duel import CardDuel
from balance_tool.experiments import card_swap_test, print_swap_report
from balance_tool.report import (card_strength, game_length, print_report,
                                 seat_advantage, skill_gap)
from balance_tool.simulate import run_games


def make_agent(name, iterations):
    if name == "random":
        return RandomAgent()
    if name == "greedy":
        return GreedyAgent()
    if name == "mcts":
        return MCTSAgent(iterations=iterations)
    raise ValueError(f"Unknown agent: {name}")


def main():
    parser = argparse.ArgumentParser(description="Automated playtesting for Card Duel")
    parser.add_argument("--games", type=int, default=2000)
    parser.add_argument("--agent", default="greedy", choices=["random", "greedy", "mcts"])
    parser.add_argument("--iterations", type=int, default=100, help="MCTS iterations per move")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--reference", default="Bolt",
                        help="Card treated as 'fair' in the card swap test")
    parser.add_argument("--swap-games", type=int, default=1000,
                        help="Games per card in the card swap test (0 to skip)")
    args = parser.parse_args()

    game = CardDuel()
    agent = make_agent(args.agent, args.iterations)

    print(f"Playing {args.games} games of {agent.name} vs {agent.name}...")
    mirror = run_games(game, [agent, agent], args.games, seed=args.seed)

    print(f"Playing {args.games} games of greedy vs random (seats alternate)...")
    skill_results = run_games(game, [GreedyAgent(), RandomAgent()], args.games,
                              seed=args.seed + 1, swap_seats=True)

    print_report(
        seat_advantage(mirror),
        game_length(mirror, game.params["max_turns"]),
        card_strength(mirror),
        skill_gap(skill_results, strong_agent=0),
    )

    if args.swap_games > 0:
        print(f"Running card swap test ({args.swap_games} games per card)...")
        swap = card_swap_test(None, agent, args.reference, args.swap_games, seed=args.seed + 2)
        print_swap_report(swap)


if __name__ == "__main__":
    main()
