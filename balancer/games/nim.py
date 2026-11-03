"""Subtraction Nim: a tiny second game that proves the engine is general.

Players alternately take 1..``max_take`` tokens from a pile; whoever takes the
last token wins. Theory gives a known answer to check the tool against: the
first player wins with perfect play unless ``pile % (max_take + 1) == 0``.
Weak (random) agents hide this; strong agents expose it.
"""
from __future__ import annotations

from ..core.game import Game


class NimState:
    __slots__ = ("pile", "player", "moves", "win")

    def __init__(self, pile, player=0, moves=0, win=None):
        self.pile, self.player, self.moves, self.win = pile, player, moves, win


class Nim(Game):
    name = "nim"
    DEFAULT_PARAMS = {"pile": 21, "max_take": 3}
    PARAM_SPACE = {"pile": (5, 40), "max_take": (2, 6)}
    PRESETS = {"second_player_wins": {"pile": 20}}

    def validate_params(self):
        if self.params["pile"] < 1 or self.params["max_take"] < 1:
            raise ValueError("pile and max_take must be >= 1")

    def initial_state(self, seed):
        return NimState(self.params["pile"])

    def clone(self, s):
        return NimState(s.pile, s.player, s.moves, s.win)

    def current_player(self, s):
        return s.player

    def legal_actions(self, s):
        if s.pile <= 0:
            return []
        return list(range(1, min(self.params["max_take"], s.pile) + 1))

    def step(self, s, a):
        s.pile -= a
        s.moves += 1
        if s.pile == 0:
            s.win = s.player
        else:
            s.player = 1 - s.player

    def is_terminal(self, s):
        return s.pile <= 0

    def winner(self, s):
        return s.win

    def all_action_labels(self):
        return [f"take{k}" for k in range(1, self.params["max_take"] + 1)]

    def action_label(self, s, a):
        return f"take{a}"

    def turn_count(self, s):
        return s.moves

    def render(self, s, viewer):
        return f"Pile: {s.pile} tokens (take 1-{self.params['max_take']})"

    def describe_action(self, s, a):
        return f"take {a}"
