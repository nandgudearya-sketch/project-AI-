"""Play Card Duel against an agent to check that it plays reasonably.

Example:
    python play_human.py --agent greedy
    python play_human.py --agent mcts --iterations 200
"""
import argparse
import random

from balance_tool.agents import GreedyAgent, MCTSAgent, RandomAgent
from balance_tool.card_duel import CardDuel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="greedy", choices=["random", "greedy", "mcts"])
    ap.add_argument("--iterations", type=int, default=200)
    ap.add_argument("--seat", type=int, default=0, choices=[0, 1], help="0 = you move first")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    agent = {"random": RandomAgent(), "greedy": GreedyAgent(),
             "mcts": MCTSAgent(iterations=args.iterations)}[args.agent]
    game = CardDuel()
    rng = random.Random(args.seed)
    state = game.initial_state(rng)
    me = args.seat
    print(f"\nYou are player {me}. Cards: " + ", ".join(
        f"{n}({c['cost']} mana, {c['kind']} {c['value']})" for n, c in game.cards.items()))
    while not game.is_terminal(state):
        p = game.current_player(state)
        if p == me:
            print("\n" + game.describe(state, me))
            legal = game.legal_actions(state)
            for i, a in enumerate(legal):
                print(f"  [{i}] {'Play ' + a[1] if a[0] == 'play' else 'End turn'}")
            choice = None
            while choice is None:
                try:
                    choice = legal[int(input("Your choice: "))]
                except (ValueError, IndexError):
                    print("Please type one of the numbers above.")
            action = choice
        else:
            action = agent.choose(game, state, rng)
            print(f"\nOpponent: {'plays ' + action[1] if action[0] == 'play' else 'ends turn'}")
        state = game.apply(state, action)
    w = game.winner(state)
    print("\nYou win!" if w == me else "\nDraw." if w is None else "\nThe agent wins.")


if __name__ == "__main__":
    main()
