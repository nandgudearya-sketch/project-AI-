"""Balance checks: seat advantage, game length, card usage, skill vs luck."""
import math
from statistics import mean, median


def wilson(score, n, z=1.96):
    """95% confidence interval for a proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = score / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def seat_advantage(results):
    n = len(results)
    score = sum(1.0 if r.seat_winner == 0 else 0.5 if r.seat_winner is None else 0.0 for r in results)
    rate = score / n
    lo, hi = wilson(score, n)
    flags = []
    if lo > 0.5 and rate > 0.55:
        flags.append("FLAG: player 0 (moves first) has an advantage")
    elif hi < 0.5 and rate < 0.45:
        flags.append("FLAG: player 1 (moves second) has an advantage")
    return {"check": "Seat advantage", "rate": rate, "ci": (lo, hi), "flags": flags,
            "lines": [f"Player 0 win rate: {rate:.1%}  (95% CI {lo:.1%}-{hi:.1%}, {n} games)"]}


def game_length(results, max_turns):
    turns = [r.turns for r in results]
    timeouts = sum(1 for r in results if r.summary.get("timeout"))
    pct = timeouts / len(results)
    flags = []
    if pct > 0.2:
        flags.append("FLAG: many games stall until the turn limit")
    if mean(turns) < 0.2 * max_turns:
        flags.append("FLAG: games are very short")
    return {"check": "Game length", "flags": flags,
            "lines": [f"Average {mean(turns):.1f} turns per player (median {median(turns):.0f}); "
                      f"{pct:.1%} of games hit the turn limit of {max_turns}"]}


def card_strength(results):
    """Usage statistics per card. (Strength itself is measured by the card swap test.)"""
    n = len(results)
    plays, drawn = {}, {}
    for r in results:
        for p in (0, 1):
            for c, k in r.summary.get("plays", [{}, {}])[p].items():
                plays[c] = plays.get(c, 0) + k
            for c, k in r.summary.get("drawn", [{}, {}])[p].items():
                drawn[c] = drawn.get(c, 0) + k
    cards = sorted(drawn)
    rates = {c: plays.get(c, 0) / drawn[c] for c in cards}
    med = median(rates.values()) if rates else 0
    flags, lines = [], []
    for c in cards:
        lines.append(f"{c:8s} played {plays.get(c, 0) / n:5.2f} times per game; "
                     f"played in {rates[c]:5.1%} of the times it was drawn")
        if rates[c] < 0.35 * med:
            flags.append(f"FLAG: {c} is rarely played ({plays.get(c, 0) / n:.2f} times per game)")
    return {"check": "Card usage", "flags": flags, "lines": lines}


def skill_gap(results, strong_agent=0):
    n = len(results)
    score = sum(1.0 if r.agent_winner == strong_agent else 0.5 if r.agent_winner is None else 0.0
                for r in results)
    rate = score / n
    lo, hi = wilson(score, n)
    flags = []
    if rate < 0.6:
        flags.append("FLAG: outcomes look mostly luck-driven (skilled agent barely beats random)")
    return {"check": "Skill vs. luck", "rate": rate, "ci": (lo, hi), "flags": flags,
            "lines": [f"Greedy beats random {rate:.1%} of the time  (95% CI {lo:.1%}-{hi:.1%})"]}


def print_report(*sections):
    print("\n" + "=" * 60)
    print("BALANCE REPORT")
    print("=" * 60)
    for sec in sections:
        print(f"\n[{sec['check']}]")
        for line in sec["lines"]:
            print("  " + line)
        for flag in sec["flags"]:
            print("  " + flag)
        if not sec["flags"]:
            print("  OK: no problem detected")
    print()
