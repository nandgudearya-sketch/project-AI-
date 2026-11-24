"""
The contract every game must follow so the tool can test it.

To plug in a new game, write a class that inherits from Game and fills
in these methods. Agents, the simulator, and the balance report only
ever talk to a game through this interface, so they work for any game.
"""

from abc import ABC, abstractmethod


class Game(ABC):

    @abstractmethod
    def initial_state(self, rng):
        """Return the starting state. Use rng for all randomness (shuffling)."""

    @abstractmethod
    def current_player(self, state):
        """Return 0 or 1: whose move it is."""

    @abstractmethod
    def legal_actions(self, state):
        """Return a list of actions the current player may take."""

    @abstractmethod
    def apply(self, state, action):
        """Return a NEW state after the action. Never modify the input state."""

    @abstractmethod
    def is_terminal(self, state):
        """Return True if the game is over."""

    @abstractmethod
    def winner(self, state):
        """Return 0 or 1 for the winner, or None for a draw."""

    # ---- Optional hooks (override for better agents / richer reports) ----

    def determinize(self, state, player, rng):
        """
        Return a copy of the state where information hidden from `player`
        (opponent's hand, deck order) is randomly re-guessed. Used by MCTS
        so it doesn't cheat by seeing hidden cards.
        """
        return state

    def action_value(self, state, action):
        """Quick heuristic score of an action, used by the greedy agent."""
        return 0.0

    def summary(self, state):
        """
        Return a dict describing a finished game for the balance report,
        e.g. {"turns": 23, "plays": [[...p0 cards...], [...p1 cards...]]}.
        """
        return {}
