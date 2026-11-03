from __future__ import annotations

import random
from abc import ABC, abstractmethod


class Agent(ABC):
    """An agent picks an action. It receives the true state, but a fair agent
    must only use what its player can see: search agents call
    ``game.determinize`` first so hidden information is re-sampled."""

    spec: str = "agent"

    @abstractmethod
    def act(self, game, state, rng: random.Random): ...
