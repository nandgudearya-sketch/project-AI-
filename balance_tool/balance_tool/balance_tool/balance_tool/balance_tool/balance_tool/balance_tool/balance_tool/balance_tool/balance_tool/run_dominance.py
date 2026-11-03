"""Search for dominant strategies and dominant decks.

Example:
    python run_dominance.py
"""
import argparse

from balance_tool.agents import GreedyAgent
from balance_tool.card_duel import CardDuel
from balance_tool.strategies import candidate_strategies, find_dominant_strategies, search_decks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=200, help="games per matchup")
    ap.add_argument("--deck-iterations", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    game = CardDuel()
    print("\nSTRATEGY TOURNAMENT (fixed card-priority strategies, round robin)")
    rows = find_dominant_strategies(game, candidate_strategies(game, seed=args.seed), args.games, args.seed)
    for r in rows:
        tag = "  <-- DOMINANT (beats every other strategy)" if r["dominant"] else ""
        print(f"  {r['strategy']:20s} average {r['average']:.1%}   worst matchup {r['worst']:.1%}{tag}")
    if not any(r["dominant"] for r in rows):
        print("  No strategy beats every other strategy.")

    print("\nDECK SEARCH (hill climbing against the default deck, greedy agent)")
    deck, rate = search_decks(game, GreedyAgent(), args.deck_iterations, args.games, args.seed)
    print("  Best deck found:", deck)
    print(f"  Win rate vs default deck (fresh games): {rate:.1%}")
    if rate > 0.6:
        print("  FLAG: a deck exists that clearly beats the default deck (dominant deck choice)")
    print()


if __name__ == "__main__":
    main()
