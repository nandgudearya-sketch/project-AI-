"""Play many games between agents and record the results."""

import random


def play_game(game, agents, rng):
    """Play one game. agents[0] is player 0 (goes first), agents[1] is player 1."""
    state = game.initial_state(rng)
    while not game.is_terminal(state):
        player = game.current_player(state)
        action = agents[player].choose(game, state, rng)
        state = game.apply(state, action)
    result = {"winner": game.winner(state)}
    result.update(game.summary(state))
    return result


def run_games(game, agents, n_games, seed=0, swap_seats=False):
    """
    Play n_games and return a list of result dicts.

    swap_seats=False: agents[0] always goes first (use for seat-advantage tests
                      with identical agents).
    swap_seats=True:  alternate who goes first (use for skill comparisons, so
                      seat advantage doesn't bias the result). Each result
                      records which agent sat in seat 0 under "seat0_agent".
    """
    rng = random.Random(seed)
    results = []
    for i in range(n_games):
        seats = agents if not (swap_seats and i % 2) else [agents[1], agents[0]]
        r = play_game(game, seats, rng)
        r["seat0_agent"] = 0 if seats is agents else 1
        results.append(r)
    return results
