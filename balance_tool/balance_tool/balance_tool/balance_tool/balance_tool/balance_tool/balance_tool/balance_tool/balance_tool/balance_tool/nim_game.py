"""A second, very different game (Nim) to show the engine is general.
Take 1-3 stones from a pile; whoever takes the last stone wins."""
from .game_interface import Game


class NimState:
    def __init__(self, stones, player, turns):
        self.stones, self.player, self.turns = stones, player, turns


class Nim(Game):
    def __init__(self, stones=21, max_take=3):
        self.params = {"stones": stones, "max_take": max_take, "max_turns": stones}

    def initial_state(self, rng, **kwargs):
        return NimState(self.params["stones"], 0, 0)

    def current_player(self, state):
        return state.player

    def legal_actions(self, state):
        return [k for k in range(1, self.params["max_take"] + 1) if k <= state.stones]

    def apply(self, state, action):
        return NimState(state.stones - action, 1 - state.player, state.turns + 1)

    def is_terminal(self, state):
        return state.stones == 0

    def winner(self, state):
        return 1 - state.player      # the player who just took the last stone

    def action_value(self, state, action):
        return 1.0 if (state.stones - action) % (self.params["max_take"] + 1) == 0 else 0.0

    def summary(self, state):
        return {"turns": state.turns // 2 + 1}
