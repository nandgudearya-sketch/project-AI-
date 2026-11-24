"""
Turn simulation results into balance findings.

Each check returns a dict with the numbers plus a list of human-readable
warnings. We use 95% confidence intervals so we only flag a problem when
the data actually supports it, not just random noise.
"""

import math
from collections import defaultdict

Z = 1.96  # 95% confidence


def wilson_interval(wins, n):
    """95% confidence interval for a win rate (works well even for small n)."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / denom
    margin = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / denom
    return (centre - margin, centre + margin)


def seat_advantage(results):
    """Does going first (or second) win too often? Use with identical agents."""
    p0 = sum(1 for r in results if r["winner"] == 0)
    p1 = sum(1 for r in results if r["winner"] == 1)
    draws = len(results) - p0 - p1
    decisive = p0 + p1
    rate = p0 / decisive if decisive else 0.5
    lo, hi = wilson_interval(p0, decisive)
    warnings = []
    if lo > 0.5:
        warnings.append(f"First-player advantage: player 0 wins {rate:.1%} of decisive games "
                        f"(95% CI {lo:.1%}-{hi:.1%}).")
    elif hi < 0.5:
        warnings.append(f"Second-player advantage: player 0 wins only {rate:.1%} "
                        f"(95% CI {lo:.1%}-{hi:.1%}).")
    return {"p0_wins": p0, "p1_wins": p1, "draws": draws,
            "p0_win_rate": rate, "ci": (lo, hi), "warnings": warnings}


def game_length(results, max_turns):
    """Do games run too long or hit the turn limit?"""
    turns = [r["turns"] for r in results if "turns" in r]
    if not turns:
        return {"warnings": []}
    avg = sum(turns) / len(turns)
    timeouts = sum(1 for t in turns if t >= max_turns) / len(turns)
    warnings = []
    if timeouts > 0.10:
        warnings.append(f"{timeouts:.1%} of games hit the {max_turns}-turn limit; "
                        f"the game may stall or run too long.")
    return {"avg_turns": avg, "timeout_rate": timeouts, "warnings": warnings}


def card_strength(results, rarely_played=0.15):
    """
    For each card: in games where a player played it, how often did that player win?

    The win rate here is CORRELATION ONLY, so it raises no strength warnings.
    A weak card can look strong because players who are already winning have
    spare mana to play it. Use experiments.card_swap_test for strength.

    It does flag cards that are almost never played (the "never useful" problem).
    """
    played_in = defaultdict(int)
    won_with = defaultdict(int)
    total_plays = defaultdict(int)

    for r in results:
        if "plays" not in r:
            continue
        for player in (0, 1):
            cards = r["plays"][player]
            for c in cards:
                total_plays[c] += 1
            for c in set(cards):
                played_in[c] += 1
                if r["winner"] == player:
                    won_with[c] += 1

    stats, warnings = {}, []
    for c in sorted(played_in, key=lambda c: -won_with[c] / played_in[c]):
        n = played_in[c]
        rate = won_with[c] / n
        lo, hi = wilson_interval(won_with[c], n)
        stats[c] = {"games": n, "win_rate": rate, "ci": (lo, hi),
                    "plays_per_game": total_plays[c] / len(results)}
        if stats[c]["plays_per_game"] < rarely_played:
            warnings.append(f"'{c}' is rarely played ({stats[c]['plays_per_game']:.2f} times "
                            f"per game); it may never be worth using.")
    return {"cards": stats, "warnings": warnings}


def skill_gap(results, strong_agent=0, threshold=0.70):
    """
    How often does the stronger agent beat the weaker one? Results must come
    from run_games(..., swap_seats=True). If even a big skill gap doesn't win
    reliably, the game may be decided mostly by luck.
    """
    wins = 0
    for r in results:
        strong_seat = 0 if r["seat0_agent"] == strong_agent else 1
        if r["winner"] == strong_seat:
            wins += 1
    rate = wins / len(results)
    warnings = []
    if rate < threshold:
        warnings.append(f"The stronger agent only wins {rate:.1%} of games; "
                        f"outcomes may depend too much on luck.")
    return {"strong_win_rate": rate, "warnings": warnings}


def print_report(seat, length, cards, skill=None):
    print("=" * 60)
    print("BALANCE REPORT")
    print("=" * 60)

    print(f"\nSeat advantage: P0 wins {seat['p0_wins']}, P1 wins {seat['p1_wins']}, "
          f"draws {seat['draws']}")
    lo, hi = seat["ci"]
    print(f"  P0 win rate (decisive games): {seat['p0_win_rate']:.1%}  [95% CI {lo:.1%}-{hi:.1%}]")

    if "avg_turns" in length:
        print(f"\nGame length: {length['avg_turns']:.1f} turns on average, "
              f"{length['timeout_rate']:.1%} hit the turn limit")

    print("\nCards (win rate of the player who played it; correlation only):")
    print(f"  {'card':<10}{'win rate':>10}{'95% CI':>18}{'plays/game':>12}")
    for c, s in cards["cards"].items():
        lo, hi = s["ci"]
        print(f"  {c:<10}{s['win_rate']:>10.1%}{f'{lo:.0%}-{hi:.0%}':>18}"
              f"{s['plays_per_game']:>12.2f}")

    if skill:
        print(f"\nSkill check: stronger agent wins {skill['strong_win_rate']:.1%} of games")

    all_warnings = seat["warnings"] + length["warnings"] + cards["warnings"]
    if skill:
        all_warnings += skill["warnings"]
    print("\nPROBLEMS FOUND:")
    if all_warnings:
        for w in all_warnings:
            print(f"  - {w}")
    else:
        print("  None detected.")
    print()
