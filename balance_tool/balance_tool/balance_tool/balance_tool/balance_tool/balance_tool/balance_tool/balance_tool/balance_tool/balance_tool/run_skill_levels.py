"""Run the checks at several agent skill levels and compare the findings.

Example:
    python run_skill_levels.py --games 300 --mcts-iterations 50
"""
import argparse

from balance_tool.agents import GreedyAgent, MCTSAgent, RandomAgent
from balance_tool.card_duel import CardDuel
from balance_tool.experiments import card_swap_test
from balance_tool.report import seat_advantage
from balance_tool.simulate import run_games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=300)
    ap.add_argument("--swap-games", type=int, default=150)
    ap.add_argument("--mcts-iterations", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    game = CardDuel()
    agents = [RandomAgent(), GreedyAgent(), MCTSAgent(iterations=args.mcts_iterations)]
    print(f"\n{'agent':8s} {'P0 win rate':>12s} {'Pebble plays/game':>18s} {'Dragon vs Bolt':>15s} {'Pebble vs Bolt':>15s}")
    for agent in agents:
        res = run_games(game, [agent, agent], args.games, seed=args.seed)
        seat = seat_advantage(res)["rate"]
        pebble = sum(r.summary["plays"][p].get("Pebble", 0) for r in res for p in (0, 1)) / len(res)
        swap = {r["card"]: r["rate"] for r in card_swap_test(game, agent, "Bolt", args.swap_games,
                                                              seed=args.seed + 5, cards=["Dragon", "Pebble"])}
        print(f"{agent.name:8s} {seat:12.1%} {pebble:18.2f} {swap['Dragon']:15.1%} {swap['Pebble']:15.1%}")
    print()


if __name__ == "__main__":
    main()
