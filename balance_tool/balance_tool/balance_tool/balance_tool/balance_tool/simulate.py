"""Run many games between agents and collect results."""
import random
from dataclasses import dataclass


@dataclass
class GameResult:
    seat_winner: object      # 0, 1 or None (draw): who won by seat (0 = moves first)
    agent_winner: object     # index into the agents list, or None
    turns: int
    seat_agents: tuple       # (agent index in seat 0, agent index in seat 1)
    summary: dict


def run_games(game, agents, n_games, seed=0, swap_seats=False, decks=None):
    """Play n_games. agents = [agent_a, agent_b]. With swap_seats the agents alternate seats
    every game (cancels first-player advantage). decks = optional [deck_for_a, deck_for_b]."""
    results = []
    for i in range(n_games):
        order = [1, 0] if (swap_seats and i % 2 == 1) else [0, 1]
        rng_game = random.Random(seed * 1_000_003 + i)
        rng_agent = random.Random(seed * 7_919 + i + 17)
        if decks is not None:
            state = game.initial_state(rng_game, decks=[decks[order[0]], decks[order[1]]])
        else:
            state = game.initial_state(rng_game)
        guard = 0
        while not game.is_terminal(state) and guard < 100000:
            seat = game.current_player(state)
            action = agents[order[seat]].choose(game, state, rng_agent)
            state = game.apply(state, action)
            guard += 1
        w = game.winner(state)
        summary = game.summary(state)
        results.append(GameResult(
            seat_winner=w,
            agent_winner=None if w is None else order[w],
            turns=summary.get("turns", 0),
            seat_agents=(order[0], order[1]),
            summary=summary,
        ))
    return results
