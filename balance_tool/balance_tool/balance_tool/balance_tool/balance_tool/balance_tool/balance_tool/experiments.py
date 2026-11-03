"""Card swap test: compare two decks that differ in exactly one card."""
from .card_duel import CardDuel
from .report import wilson
from .simulate import run_games


def card_swap_test(game, agent, reference, games_per_card, seed=0, cards=None):
    """For every card X: deck A = base deck with one `reference` card replaced by X,
    deck B = the base deck. Seats alternate, so any win-rate difference is caused by X."""
    game = game or CardDuel()
    base = game.deck_list()
    if reference not in base:
        raise ValueError(f"Reference card {reference!r} is not in the deck")
    candidates = cards or [c for c in game.params["cards"] if c != reference]
    out = []
    for k, card in enumerate(candidates):
        deck_a = list(base)
        deck_a[deck_a.index(reference)] = card
        results = run_games(game, [agent, agent], games_per_card, seed=seed + k,
                            swap_seats=True, decks=[deck_a, list(base)])
        score = sum(1.0 if r.agent_winner == 0 else 0.5 if r.agent_winner is None else 0.0
                    for r in results)
        rate = score / len(results)
        lo, hi = wilson(score, len(results))
        if lo > 0.5 and rate >= 0.55:
            verdict = "TOO STRONG"
        elif hi < 0.5 and rate <= 0.45:
            verdict = "too weak"
        else:
            verdict = "similar"
        out.append({"card": card, "reference": reference, "rate": rate, "ci": (lo, hi), "verdict": verdict})
    return out


def print_swap_report(swap):
    ref = swap[0]["reference"] if swap else "?"
    print("\n" + "=" * 60)
    print(f"CARD SWAP TEST  (deck with card X instead of {ref}  vs  normal deck)")
    print("=" * 60)
    for r in swap:
        print(f"  {r['card']:8s} win rate {r['rate']:5.1%}  (95% CI {r['ci'][0]:.1%}-{r['ci'][1]:.1%})  -> {r['verdict']}")
    print()
