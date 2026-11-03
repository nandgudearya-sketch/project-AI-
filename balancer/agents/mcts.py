"""Single-observer Information Set MCTS (Cowling, Powley & Whitehouse, 2012).

Each iteration samples a determinization (a guess at the hidden cards that is
consistent with what this player can see), then runs UCT on a single tree
shared across determinizations. Because legal moves differ between
determinizations, UCB uses an "availability" count (how many times the move
was legal when its parent was visited) instead of the parent's visit count.

Skill is controlled by ``iterations``: more iterations means stronger play.
Rollouts run for ``rollout_depth`` moves (default: the game's own
``rollout_depth``) and are then scored with the game heuristic. Card games use
short rollouts because long random card play is mostly noise.
"""
from __future__ import annotations

import math

from .base import Agent


class _Node:
    __slots__ = ("parent", "player", "children", "visits", "value", "avail")

    def __init__(self, parent, player):
        self.parent = parent
        self.player = player       # the player who made the move into this node
        self.children = {}
        self.visits = 0
        self.value = 0.0
        self.avail = 1


class MCTSAgent(Agent):
    def __init__(self, iterations: int = 200, c: float | None = None,
                 rollout_depth: int | None = None):
        self.iterations = iterations
        self.c = c
        self.rollout_depth = rollout_depth
        self.spec = f"mcts:{iterations}"

    def act(self, game, state, rng):
        legal = game.legal_actions(state)
        if len(legal) == 1:
            return legal[0]
        me = game.current_player(state)
        root = _Node(None, None)
        c = self.c if self.c is not None else game.mcts_c
        log, sqrt = math.log, math.sqrt

        for _ in range(self.iterations):
            s = game.determinize(state, me, rng)
            node = root
            # Selection and expansion
            while not game.is_terminal(s):
                acts = game.legal_actions(s)
                children = node.children
                untried = []
                for a in acts:
                    ch = children.get(a)
                    if ch is None:
                        untried.append(a)
                    else:
                        ch.avail += 1
                mover = game.current_player(s)
                if untried:
                    a = untried[rng.randrange(len(untried))]
                    game.step(s, a)
                    child = _Node(node, mover)
                    children[a] = child
                    node = child
                    break
                best_a, best_u = None, float("-inf")
                for a in acts:
                    ch = children[a]
                    u = ch.value / ch.visits + c * sqrt(log(ch.avail) / ch.visits)
                    if u > best_u:
                        best_a, best_u = a, u
                game.step(s, best_a)
                node = children[best_a]
            # Simulation
            rewards = self._rollout(game, s, rng)
            # Backpropagation
            while node is not root:
                node.visits += 1
                node.value += rewards[node.player]
                node = node.parent

        return max(legal, key=lambda a: root.children[a].visits if a in root.children else -1)

    def _rollout(self, game, s, rng):
        depth = self.rollout_depth if self.rollout_depth is not None else game.rollout_depth
        for _ in range(depth):
            if game.is_terminal(s):
                return game.returns(s)
            game.step(s, game.rollout_action(s, rng))
        if game.is_terminal(s):
            return game.returns(s)
        return [game.heuristic(s, i) for i in range(game.num_players)]
