"""Dominant strategy search: fixed strategies and deck choices that beat everything else."""
import itertools
import random

from .agents import Agent
from .report import wilson
from .simulate import run_games


class PriorityAgent(Agent):
    """Fixed strategy: always play the first affordable (and useful) card in a priority list."""

    def __init__(self, order, name="priority"):
        self.order = list(order)
        self.name = name

    def choose(self, game, state, rng):
        legal = game.legal_actions(state)
        plays = {a[1]: a for a in legal if a[0] == "play"}
        for card in self.order:
            if card in plays and game.action_value(state, plays[card]) > 0:
                return plays[card]
        return game.pass_action(state)


def candidate_strategies(game, n_random=8, seed=0):
    cards = game.params["cards"]
    names = sorted(cards)
    rng = random.Random(seed)
    strategies = {
        "cheapest-first": sorted(names, key=lambda c: cards[c]["cost"]),
        "priciest-first": sorted(names, key=lambda c: -cards[c]["cost"]),
        "strongest-first": sorted(names, key=lambda c: -cards[c]["value"]),
        "efficiency-first": sorted(names, key=lambda c: -cards[c]["value"] / cards[c]["cost"]),
    }
    for i in range(n_random):
        order = names[:]
        rng.shuffle(order)
        strategies[f"random-order-{i + 1}"] = order
    return {n: PriorityAgent(o, n) for n, o in strategies.items()}


def find_dominant_strategies(game, strategies, games=200, seed=0):
    """Round-robin tournament (seats alternate). A strategy is dominant if it beats ALL others."""
    names = list(strategies)
    score = {a: {} for a in names}
    for k, (a, b) in enumerate(itertools.combinations(names, 2)):
        res = run_games(game, [strategies[a], strategies[b]], games, seed=seed + k, swap_seats=True)
        s = sum(1.0 if r.agent_winner == 0 else 0.5 if r.agent_winner is None else 0.0 for r in res)
        score[a][b] = s / games
        score[b][a] = 1 - s / games
    rows = []
    for a in names:
        rates = score[a]
        worst = min(rates.values())
        lo = wilson(worst * games, games)[0]
        rows.append({"strategy": a, "average": sum(rates.values()) / len(rates), "worst": worst,
                     "dominant": lo > 0.5})
    rows.sort(key=lambda r: -r["average"])
    return rows


def search_decks(game, agent, iterations=40, games=200, seed=0):
    """Hill-climb over deck compositions (same size as the default deck) to find a deck
    that beats the default deck. A large win rate means a dominant deck exists."""
    rng = random.Random(seed)
    base = game.deck_list()
    names = sorted(game.params["cards"])

    def rate_of(deck, s):
        res = run_games(game, [agent, agent], games, seed=s, swap_seats=True, decks=[deck, base])
        return sum(1.0 if r.agent_winner == 0 else 0.5 if r.agent_winner is None else 0.0 for r in res) / games

    best, best_rate = list(base), 0.5
    for _ in range(iterations):
        cand = list(best)
        cand[rng.randrange(len(cand))] = rng.choice(names)
        r = rate_of(cand, seed)
        if r > best_rate:
            best, best_rate = cand, r
    fresh = rate_of(best, seed + 99991)   # re-check with new seeds
    counts = {c: best.count(c) for c in names if best.count(c)}
    return counts, fresh
