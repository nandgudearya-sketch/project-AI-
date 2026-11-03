"""Interface every game must implement so agents, simulator and checks work unchanged."""
from abc import ABC, abstractmethod


class Game(ABC):
    params = {}

    @abstractmethod
    def initial_state(self, rng, **kwargs):
        """Return a fresh starting state (use rng for any shuffling)."""

    @abstractmethod
    def current_player(self, state):
        """Return 0 or 1."""

    @abstractmethod
    def legal_actions(self, state):
        """Return a list of hashable actions (empty if terminal)."""

    @abstractmethod
    def apply(self, state, action):
        """Return the NEW state after the action (do not modify the old one)."""

    @abstractmethod
    def is_terminal(self, state):
        """True when the game is over."""

    @abstractmethod
    def winner(self, state):
        """0, 1, or None for a draw (only valid when terminal)."""

    # ---- optional hooks -------------------------------------------------
    def determinize(self, state, player, rng):
        """Return a copy of state where hidden info (from `player`'s view) is re-sampled.
        Games with perfect information can keep this default."""
        return state

    def action_value(self, state, action):
        """Cheap heuristic value of an action (used by the greedy agent)."""
        return 0.0

    def pass_action(self, state):
        """The 'do nothing / end turn' action, or None if the game has none."""
        return None

    def evaluate(self, state, player):
        """Heuristic in [0,1] of how good `state` is for `player` (MCTS cut-off)."""
        return 0.5

    def summary(self, state):
        """Extra statistics saved for reports, e.g. {'turns': 7}."""
        return {}

    def describe(self, state, player):
        """Human-readable text of the state from `player`'s point of view."""
        return str(state)
