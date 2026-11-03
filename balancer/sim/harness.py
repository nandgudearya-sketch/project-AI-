"""Runs games, in parallel when possible, and records what happened.

Seat swapping uses a "duplicate" format: games 2k and 2k+1 use the same seed
(same shuffled decks) with the agents' seats swapped. This cancels most of the
card luck when comparing agents and halves the noise of seat-advantage
estimates. Fixed seeds also give "common random numbers" for the tuner, so two
parameter sets are compared on identical deals.
"""
from __future__ import annotations

import os
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field

from ..agents import make_agent
from ..games import make_game

MAX_ACTIONS = 20_000


@dataclass
class GameRecord:
    seed: int
    seats: list            # agent spec in each seat
    winner: int | None     # seat index, None for a draw
    turns: int
    actions: int
    timed_out: bool
    scores: list
    plays: list = field(default_factory=list)    # per seat: {label: count}
    opening: list = field(default_factory=list)  # per seat: [labels at start]

    def result(self, seat: int) -> float:
        if self.winner is None:
            return 0.5
        return 1.0 if self.winner == seat else 0.0


def play_game(game, agents, seed: int, seats=None) -> GameRecord:
    rng = random.Random(seed * 1_000_003 + 17)
    s = game.initial_state(seed)
    opening = [sorted(game.opening_labels(s, p)) for p in range(game.num_players)]
    plays = [dict() for _ in range(game.num_players)]
    n = 0
    while not game.is_terminal(s):
        p = game.current_player(s)
        a = agents[p].act(game, s, rng)
        label = game.action_label(s, a)
        if label is not None:
            plays[p][label] = plays[p].get(label, 0) + 1
        game.step(s, a)
        n += 1
        if n > MAX_ACTIONS:
            raise RuntimeError("Game exceeded the action cap; check for infinite loops")
    return GameRecord(
        seed=seed,
        seats=list(seats or [getattr(ag, "spec", "?") for ag in agents]),
        winner=game.winner(s),
        turns=game.turn_count(s),
        actions=n,
        timed_out=game.hit_turn_limit(s),
        scores=list(game.final_scores(s)),
        plays=plays,
        opening=opening,
    )


def _play_job(job) -> GameRecord:
    game_name, params, seats, seed = job
    game = make_game(game_name, params)
    agents = [make_agent(spec) for spec in seats]
    return play_game(game, agents, seed, seats)


def match_jobs(game_name, params, specs, n_games, base_seed=0, swap=True):
    jobs = []
    for i in range(n_games):
        if swap:
            seats = list(specs) if i % 2 == 0 else list(reversed(specs))
            seed = base_seed + i // 2
        else:
            seats, seed = list(specs), base_seed + i
        jobs.append((game_name, dict(params), seats, seed))
    return jobs


class Simulator:
    """Holds a process pool so many batches can reuse the same workers.

        with Simulator(workers=8) as sim:
            records = sim.match("ember", params, ["mcts:100", "greedy"], 1000)
    """

    def __init__(self, workers: int | None = None):
        self.workers = max(1, workers if workers else (os.cpu_count() or 1))
        self._pool = None

    def __enter__(self):
        if self.workers > 1:
            self._pool = ProcessPoolExecutor(self.workers)
        return self

    def __exit__(self, *exc):
        if self._pool is not None:
            self._pool.shutdown()
            self._pool = None

    def play(self, jobs) -> list[GameRecord]:
        if self._pool is None or len(jobs) < 2:
            return [_play_job(j) for j in jobs]
        chunk = max(1, len(jobs) // (self.workers * 4))
        return list(self._pool.map(_play_job, jobs, chunksize=chunk))

    def match(self, game_name, params, specs, n_games, base_seed=0, swap=True):
        return self.play(match_jobs(game_name, params, specs, n_games, base_seed, swap))


def run_games(game_name, params, specs, n_games, base_seed=0, swap=True, workers=None):
    with Simulator(workers) as sim:
        return sim.match(game_name, params, specs, n_games, base_seed, swap)


def agent_score(records, spec) -> tuple[float, int]:
    """Total result and number of games for one agent spec."""
    total, n = 0.0, 0
    for r in records:
        for seat, s in enumerate(r.seats):
            if s == spec:
                total += r.result(seat)
                n += 1
    return total, n
