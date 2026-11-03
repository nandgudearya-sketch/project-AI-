from __future__ import annotations

from .base import Agent


class RandomAgent(Agent):
    spec = "random"

    def act(self, game, state, rng):
        return rng.choice(game.legal_actions(state))


class GreedyAgent(Agent):
    """Plans the rest of its own turn: depth-first search over its own action
    sequences until the turn passes, scoring each end point with the game's
    heuristic, and plays the first move of the best sequence. It never models
    the opponent, so it is a fast, predictable baseline.

    Planning a whole turn (rather than one move) matters for cards whose value
    is enabling other plays, such as an energy card.

    ``bias`` optionally adds ``bias_scale * weight`` to a plan's value for every
    labelled action in it. This is how strategies are expressed: "greedy, but
    values hearth more and siphon less". With no bias it is plain greedy."""

    spec = "greedy"

    def __init__(self, node_budget: int = 400, bias: dict | None = None,
                 bias_scale: float = 0.08):
        self.node_budget = node_budget
        self.bias = bias or {}
        self.bias_scale = bias_scale

    def act(self, game, state, rng):
        legal = game.legal_actions(state)
        if len(legal) == 1:
            return legal[0]
        me = game.current_player(state)
        view = game.determinize(state, me, rng)
        self._nodes = 0
        scored = [(self._value_after(game, view, a, me), rng.random(), a) for a in legal]
        return max(scored)[2]

    def _bonus(self, game, s, a):
        if not self.bias:
            return 0.0
        label = game.action_label(s, a)
        return self.bias_scale * self.bias.get(label, 0.0) if label else 0.0

    def _value_after(self, game, s, a, me):
        self._nodes += 1
        bonus = self._bonus(game, s, a)
        nxt = game.apply(s, a)
        if game.is_terminal(nxt):
            return game.returns(nxt)[me] + bonus
        if game.current_player(nxt) != me:
            # Turn passed: judge the position we left, before the opponent's
            # start-of-turn effects, so passing isn't unfairly penalised.
            return game.heuristic(s, me) + bonus
        if self._nodes >= self.node_budget:
            return game.heuristic(nxt, me) + bonus
        return bonus + max(self._value_after(game, nxt, b, me)
                           for b in game.legal_actions(nxt))


class WeightedAgent(GreedyAgent):
    """A strategy: the greedy turn planner with a per-label bias (weights in
    [-1, 1]). Positive weight = values that card more than the heuristic does,
    negative = less. These are the strategies the strategy search evolves.
    All-zero weights is exactly the greedy agent, which makes greedy a fair
    baseline for comparing strategies."""

    def __init__(self, weights: dict[str, float]):
        super().__init__(bias=weights)
        self.weights = weights
        self.spec = encode_weights(weights)


def encode_weights(weights: dict[str, float]) -> str:
    return "weighted:" + ";".join(f"{k}={v:.4f}" for k, v in weights.items())


def decode_weights(body: str) -> dict[str, float]:
    out = {}
    for part in body.split(";"):
        if part:
            k, v = part.split("=")
            out[k] = float(v)
    return out


class HumanAgent(Agent):
    spec = "human"

    def act(self, game, state, rng):
        me = game.current_player(state)
        legal = game.legal_actions(state)
        print("\n" + game.render(state, me))
        for i, a in enumerate(legal):
            print(f"  [{i}] {game.describe_action(state, a)}")
        while True:
            raw = input("Your move: ").strip()
            if raw.isdigit() and int(raw) < len(legal):
                return legal[int(raw)]
            print(f"Enter a number from 0 to {len(legal) - 1}.")
