"""
Game-playing agents at different skill levels.

    RandomAgent  - weakest: picks any legal move
    GreedyAgent  - medium: always takes the move with the best quick score
    MCTSAgent    - strongest: Monte Carlo Tree Search, more iterations = stronger

All agents only use the Game interface, so they work on any game.
"""

import math


class RandomAgent:
    name = "random"

    def choose(self, game, state, rng):
        return rng.choice(game.legal_actions(state))


class GreedyAgent:
    name = "greedy"

    def choose(self, game, state, rng):
        actions = game.legal_actions(state)
        best = max(game.action_value(state, a) for a in actions)
        return rng.choice([a for a in actions if game.action_value(state, a) == best])


class _Node:
    __slots__ = ("parent", "action", "mover", "children", "visits", "wins")

    def __init__(self, parent, action, mover):
        self.parent = parent
        self.action = action
        self.mover = mover        # the player who made `action`
        self.children = {}        # action -> _Node
        self.visits = 0
        self.wins = 0.0


class MCTSAgent:
    """
    Monte Carlo Tree Search with determinization.

    Each iteration:
      1. Determinize: re-guess hidden info (opponent's hand) so we don't cheat.
      2. Select:   walk down the tree using UCB1 (balance exploring vs. exploiting).
      3. Expand:   add one new child node for an untried move.
      4. Rollout:  play the rest of the game with a cheap random policy.
      5. Backprop: update win counts back up to the root.
    """

    def __init__(self, iterations=200, exploration=1.4):
        self.iterations = iterations
        self.c = exploration
        self.name = f"mcts{iterations}"

    def choose(self, game, state, rng):
        legal = game.legal_actions(state)
        if len(legal) == 1:
            return legal[0]

        me = game.current_player(state)
        root = _Node(None, None, None)

        for _ in range(self.iterations):
            s = game.determinize(state, me, rng)
            node = root

            # Selection + expansion
            while not game.is_terminal(s):
                actions = game.legal_actions(s)
                untried = [a for a in actions if a not in node.children]
                mover = game.current_player(s)
                if untried:
                    a = rng.choice(untried)
                    child = _Node(node, a, mover)
                    node.children[a] = child
                    node = child
                    s = game.apply(s, a)
                    break
                a = max(actions, key=lambda act: self._ucb(node, node.children[act]))
                node = node.children[a]
                s = game.apply(s, a)

            # Rollout
            while not game.is_terminal(s):
                s = game.apply(s, self._rollout_action(game, s, rng))

            # Backpropagation
            w = game.winner(s)
            while node is not None:
                node.visits += 1
                if node.mover is not None:
                    node.wins += 1.0 if w == node.mover else (0.5 if w is None else 0.0)
                node = node.parent

        best = max(legal, key=lambda a: root.children[a].visits if a in root.children else -1)
        return best

    def _ucb(self, parent, child):
        exploit = child.wins / child.visits
        explore = self.c * math.sqrt(math.log(parent.visits) / child.visits)
        return exploit + explore

    @staticmethod
    def _rollout_action(game, state, rng):
        # Slightly smarter than uniform random: usually pick a move the game's
        # heuristic considers useful, otherwise rollouts are long and uninformative.
        actions = game.legal_actions(state)
        useful = [a for a in actions if game.action_value(state, a) > 0]
        if useful and rng.random() < 0.8:
            return rng.choice(useful)
        return rng.choice(actions)
