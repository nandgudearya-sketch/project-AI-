"""Claim: a perfect-information board game (fourth test game: first-move advantage).

Rules
-----
* The board is a ``size`` x ``size`` grid. Each cell shows a value from 1 to
  ``max_value``, dealt at random from the seed and visible to both players.
* Players alternately claim one empty cell. Claiming scores the cell's value
  plus ``adj_bonus`` for every orthogonally adjacent cell you already own.
* When the board is full the higher score wins. The second player starts with
  ``p2_start_points`` as compensation for moving second.

What it tests: there is no hidden information and no luck after the deal, so
balance problems come from move order. Without compensation (``planted_seat``)
the first player, who takes the best cell first, should be flagged. A large
adjacency bonus (``planted_snowball``) rewards building clusters and makes the
game more about skill.
"""
from __future__ import annotations

import math
import random

from ..core.game import Game


class GridState:
    __slots__ = ("owner", "scores", "player", "moves")

    def copy(self):
        s = GridState.__new__(GridState)
        s.owner = self.owner[:]
        s.scores = self.scores[:]
        s.player = self.player
        s.moves = self.moves
        return s


class Claim(Game):
    name = "grid"
    rollout_depth = 1000
    mcts_c = 0.7
    DEFAULT_PARAMS = dict(size=4, max_value=5, adj_bonus=1, p2_start_points=2)
    PARAM_SPACE = dict(size=(3, 6), max_value=(2, 9), adj_bonus=(0, 5),
                       p2_start_points=(0, 12))
    PRESETS = {
        # Planted imbalance: no compensation for moving second.
        "planted_seat": {"p2_start_points": 0},
        # Planted change: clusters are worth a lot.
        "planted_snowball": {"adj_bonus": 4},
    }

    def __init__(self, params=None):
        super().__init__(params)
        n = self.params["size"]
        self.n_cells = n * n
        self.neighbors = []
        for i in range(self.n_cells):
            r, c = divmod(i, n)
            self.neighbors.append([rr * n + cc for rr, cc in
                                   ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1))
                                   if 0 <= rr < n and 0 <= cc < n])

    def validate_params(self):
        p = self.params
        if p["size"] < 2 or p["max_value"] < 1:
            raise ValueError("size >= 2 and max_value >= 1 required")
        if p["adj_bonus"] < 0 or p["p2_start_points"] < 0:
            raise ValueError("adj_bonus and p2_start_points must be non-negative")

    def initial_state(self, seed):
        rng = random.Random(seed)
        vals = tuple(rng.randint(1, self.params["max_value"]) for _ in range(self.n_cells))
        s = GridState()
        # Cells hold None (empty), 0 or 1; the last slot carries the board values.
        s.owner = [None] * self.n_cells + [vals]
        s.scores = [0, self.params["p2_start_points"]]
        s.player = 0
        s.moves = 0
        return s

    def clone(self, s):
        return s.copy()

    def current_player(self, s):
        return s.player

    def legal_actions(self, s):
        return [i for i in range(self.n_cells) if s.owner[i] is None]

    def gain(self, s, cell, player):
        own = s.owner
        return s.owner[-1][cell] + self.params["adj_bonus"] * sum(
            own[j] == player for j in self.neighbors[cell])

    def step(self, s, a):
        p = s.player
        s.scores[p] += self.gain(s, a, p)
        s.owner[a] = p
        s.moves += 1
        s.player = 1 - p

    def is_terminal(self, s):
        return s.moves >= self.n_cells

    def winner(self, s):
        a, b = s.scores
        return None if a == b else (0 if a > b else 1)

    # --------------------------------------------------------- agent helpers
    def heuristic(self, s, player):
        if self.is_terminal(s):
            return self.returns(s)[player]
        scale = 2.0 + self.params["max_value"]
        return 1.0 / (1.0 + math.exp(-(s.scores[player] - s.scores[1 - player]) / scale))

    def rollout_action(self, s, rng):
        """Usually take the cell with the best immediate gain, sometimes explore."""
        acts = self.legal_actions(s)
        if rng.random() < 0.3:
            return acts[rng.randrange(len(acts))]
        p = s.player
        return max(acts, key=lambda c: self.gain(s, c, p) + 0.01 * rng.random())

    # ------------------------------------------------------------- analytics
    def turn_count(self, s):
        return s.moves

    def final_scores(self, s):
        return list(s.scores)

    # ---------------------------------------------------------------- humans
    def render(self, s, viewer):
        n, vals = self.params["size"], s.owner[-1]
        mark = {None: "", viewer: "*", 1 - viewer: "x"}
        rows = []
        for r in range(n):
            rows.append(" ".join(f"{i:>2}:{vals[i]}{mark[s.owner[i]]:<1}"
                                 for i in range(r * n, r * n + n)))
        return (f"You {s.scores[viewer]}  Opponent {s.scores[1 - viewer]}"
                f"   (* yours, x theirs)\n" + "\n".join(rows))

    def describe_action(self, s, a):
        return f"claim cell {a} (value {s.owner[-1][a]}, gain {self.gain(s, a, s.player)})"
