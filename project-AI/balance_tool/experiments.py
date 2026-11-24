"""
Controlled experiments that measure card strength directly.

Why we need this: in a game where both players share the same deck list,
"win rate when a card is played" is misleading. Weak cards get played by
whoever has spare mana (usually the player already winning), so they look
strong. Strong cards are in both decks equally, so they look average.

The card swap test fixes this. For each card X:
  - Deck A is the normal deck.
  - Deck B is the same, but every copy of X is replaced by a reference card.
  - Play many games A vs B, alternating who goes first.
If deck A wins more than 50%, X is stronger than the reference card.
Because the decks differ only in X, the difference is caused by X.
"""

import random

from .card_duel import CardDuel
from .report import wilson_interval
from .simulate import play_game


def card_swap_test(base_params, agent, reference, n_games=1000, seed=0, margin=0.10):
    rng = random.Random(seed)
    cards = CardDuel(base_params).cards
    results = {}

    for card in cards:
        if card == reference:
            continue
        wins_with_card = 0
        decisive = 0
        for i in range(n_games):
            swapped_seat = i % 2  # alternate seats to cancel first-player advantage
            params = dict(base_params or {})
            params["deck_swap"] = {swapped_seat: (card, reference)}
            r = play_game(CardDuel(params), [agent, agent], rng)
            if r["winner"] is None:
                continue
            decisive += 1
            if r["winner"] != swapped_seat:
                wins_with_card += 1
        rate = wins_with_card / decisive if decisive else 0.5
        results[card] = {"win_rate": rate, "ci": wilson_interval(wins_with_card, decisive)}

    warnings = []
    for card, s in results.items():
        lo, hi = s["ci"]
        if lo > 0.5 + margin / 2 and s["win_rate"] > 0.5 + margin:
            warnings.append(f"'{card}' is much stronger than '{reference}': the deck with it "
                            f"wins {s['win_rate']:.1%} (95% CI {lo:.1%}-{hi:.1%}).")
        if hi < 0.5 - margin / 2 and s["win_rate"] < 0.5 - margin:
            warnings.append(f"'{card}' is much weaker than '{reference}': the deck with it "
                            f"wins only {s['win_rate']:.1%} (95% CI {lo:.1%}-{hi:.1%}).")
    return {"reference": reference, "cards": results, "warnings": warnings}


def print_swap_report(swap):
    print(f"CARD SWAP TEST (each card vs. reference card '{swap['reference']}')")
    print(f"  {'card':<10}{'deck win rate':>15}{'95% CI':>16}")
    for card, s in sorted(swap["cards"].items(), key=lambda kv: -kv[1]["win_rate"]):
        lo, hi = s["ci"]
        print(f"  {card:<10}{s['win_rate']:>15.1%}{f'{lo:.0%}-{hi:.0%}':>16}")
    print("\nCARD PROBLEMS FOUND:")
    for w in swap["warnings"] or ["None detected."]:
        print(f"  - {w}")
    print()
