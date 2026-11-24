"""The abstract game interface.

Every game plugged into the tool implements this class. Agents, the simulation
harness, the balance analyzer, the strategy search and the tuner only ever talk
to a game through these methods, which is what keeps the tool game-agnostic.

Conventions
-----------
* States are plain Python objects owned by the game. ``step`` mutates a state in
  place (fast, used inside search); ``apply`` returns a new state.
* All randomness (shuffling, dice) is decided when the state is created or
  determinized, so ``step`` is deterministic. This makes games reproducible
  from a seed and makes search agents simple.
* Every tunable number lives in ``self.params`` (a flat dict). The tuner only
  edits that dict, so no game code has to know tuning exists.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Any, Hashable


class Game(ABC):
    name: str = "base"
    num_players: int = 2
    #: How many moves MCTS rollouts play before falling back to ``heuristic``.
    #: Games without a useful heuristic should roll out to the end.
    rollout_depth: int = 1000
    #: UCB exploration constant for MCTS. ~1.0 suits win/loss rewards; games whose
    #: heuristic gives small value differences need a smaller constant.
    mcts_c: float = 1.0

    #: Every tunable parameter and its default value.
    DEFAULT_PARAMS: dict[str, Any] = {}
    #: Named parameter overrides (e.g. deliberately planted imbalances).
    PRESETS: dict[str, dict[str, Any]] = {}
    #: Integer bounds (low, high) for parameters the tuner may change.
    PARAM_SPACE: dict[str, tuple[int, int]] = {}

    def __init__(self, params: dict[str, Any] | None = None):
        merged = dict(self.DEFAULT_PARAMS)
        if params:
            unknown = set(params) - set(merged)
            if unknown:
                raise ValueError(f"Unknown params for {self.name}: {sorted(unknown)}")
            merged.update(params)
        self.params = merged
        self.validate_params()

    # ------------------------------------------------------------------ params
    @classmethod
    def preset_params(cls, preset: str | None = None) -> dict[str, Any]:
        params = dict(cls.DEFAULT_PARAMS)
        if preset in (None, "", "default"):
            return params
        if preset not in cls.PRESETS:
            raise ValueError(
                f"Unknown preset '{preset}' for {cls.name}. "
                f"Available: default, {', '.join(cls.PRESETS)}"
            )
        params.update(cls.PRESETS[preset])
        return params

    def validate_params(self) -> None:
        """Raise ValueError if the parameter combination is invalid."""

    # ------------------------------------------------------------- core rules
    @abstractmethod
    def initial_state(self, seed: int) -> Any: ...

    @abstractmethod
    def clone(self, state: Any) -> Any: ...

    @abstractmethod
    def current_player(self, state: Any) -> int: ...

    @abstractmethod
    def legal_actions(self, state: Any) -> list[Hashable]: ...

    @abstractmethod
    def step(self, state: Any, action: Hashable) -> None:
        """Apply ``action`` to ``state`` in place."""

    @abstractmethod
    def is_terminal(self, state: Any) -> bool: ...

    @abstractmethod
    def winner(self, state: Any) -> int | None:
        """Winning player index, or None for a draw. Only valid if terminal."""

    def apply(self, state: Any, action: Hashable) -> Any:
        new = self.clone(state)
        self.step(new, action)
        return new

    def returns(self, state: Any) -> list[float]:
        """Per-player result: 1 win, 0 loss, 0.5 each for a draw."""
        w = self.winner(state)
        if w is None:
            return [1.0 / self.num_players] * self.num_players
        return [1.0 if i == w else 0.0 for i in range(self.num_players)]

    # -------------------------------------------------- hidden information
    def determinize(self, state: Any, player: int, rng: random.Random) -> Any:
        """Return a copy of ``state`` in which everything ``player`` cannot see
        has been re-sampled consistently with what they can see.

        Perfect-information games keep the default (a plain copy)."""
        return self.clone(state)

    # ---------------------------------------------------- agent helpers
    def heuristic(self, state: Any, player: int) -> float:
        """Estimated probability in [0, 1] that ``player`` wins from ``state``.
        Used to cut off long rollouts and by the greedy agent."""
        return 0.5

    def rollout_action(self, state: Any, rng: random.Random) -> Hashable:
        """Default rollout policy for MCTS: uniformly random."""
        return rng.choice(self.legal_actions(state))

    # ----------------------------------------------------- analytics hooks
    def all_action_labels(self) -> list[str]:
        """Every label ``action_label`` can return (e.g. every card name)."""
        return []

    def action_label(self, state: Any, action: Hashable) -> str | None:
        """What to record when ``action`` is taken (e.g. the card played).
        Return None for actions not worth tracking (e.g. 'end turn')."""
        return None

    def opening_labels(self, state: Any, player: int) -> set[str]:
        """Labels ``player`` starts the game with (e.g. cards in the opening
        hand). Because this is decided by the shuffle alone, comparing win
        rates with and without a label is a randomized experiment: it measures
        how strong a card is without the confounds of 'who chose to play it'."""
        return set()

    def turn_count(self, state: Any) -> int:
        return 0

    def hit_turn_limit(self, state: Any) -> bool:
        """True if the game ended because of a length cap, not a real win."""
        return False

    def final_scores(self, state: Any) -> list[float]:
        return self.returns(state)

    # ------------------------------------------------------------ humans
    def render(self, state: Any, viewer: int) -> str:
        return repr(state)

    def describe_action(self, state: Any, action: Hashable) -> str:
        return str(action)
