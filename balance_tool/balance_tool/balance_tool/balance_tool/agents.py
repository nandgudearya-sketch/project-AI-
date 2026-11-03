"""Agents of increasing skill: Random < Greedy < MCTS."""
import math


class Agent:
    name = "agent"

    def choose(self, game, state, rng):
        raise NotImplementedError


class RandomAgent(Agent):
    name = "random"

    def choose(self, game, state, rng):
        return rng.choice(game.legal_actions(state))


class GreedyAgent(Agent):
    """Takes the action with the best heuristic value; ends the turn when nothing is worth doing."""
    name = "greedy"

    def __init__(self, min_value=0.5):
        self.min_value = min_value

    def choose(self, game, state, rng):
        legal = game.legal_actions(state)
        best = max(((game.action_value(state, a), rng.random(), a) for a in legal))
        value, _, action = best
        if value < self.min_value:
            p = game.pass_action(state)
            if p is not None and p in legal:
                return p
        return action


class _Node:
    __slots__ = ("action", "parent", "player", "children", "visits", "value", "avail")

    def __init__(self, action, parent, player):
        self.action, self.parent, self.player = action, parent, player
        self.children = {}
        self.visits = 0
        self.value = 0.0
        self.avail = 0


class MCTSAgent(Agent):
    """Single-observer information-set MCTS: each iteration samples a determinization
    of the hidden information, so the agent plays fairly (it never peeks at the opponent's hand)."""
    name = "mcts"

    def __init__(self, iterations=100, exploration=0.7, rollout_depth=30, rollout_epsilon=0.2):
        self.iterations = iterations
        self.c = exploration
        self.rollout_depth = rollout_depth
        self.rollout_epsilon = rollout_epsilon
        self._greedy = GreedyAgent()

    def choose(self, game, state, rng):
        legal = game.legal_actions(state)
        if len(legal) == 1:
            return legal[0]
        root_player = game.current_player(state)
        root = _Node(None, None, None)
        for _ in range(self.iterations):
            s = game.determinize(state, root_player, rng)
            node = root
            while not game.is_terminal(s):
                legal_here = game.legal_actions(s)
                untried = [a for a in legal_here if a not in node.children]
                if untried:
                    a = rng.choice(untried)
                    child = _Node(a, node, game.current_player(s))
                    node.children[a] = child
                    s = game.apply(s, a)
                    node = child
                    break
                for a in legal_here:
                    node.children[a].avail += 1
                best = max(legal_here, key=lambda a: self._ucb(node.children[a]))
                node = node.children[best]
                s = game.apply(s, best)
            result = self._rollout(game, s, root_player, rng)
            while node.parent is not None:
                node.visits += 1
                node.value += result if node.player == root_player else 1.0 - result
                node = node.parent
        return max(root.children.values(), key=lambda n: n.visits).action

    def _ucb(self, n):
        return n.value / n.visits + self.c * math.sqrt(math.log(max(n.avail, 1) + 1) / n.visits)

    def _rollout(self, game, s, root_player, rng):
        depth = 0
        while not game.is_terminal(s) and depth < self.rollout_depth:
            if rng.random() < self.rollout_epsilon:
                a = rng.choice(game.legal_actions(s))
            else:
                a = self._greedy.choose(game, s, rng)
            s = game.apply(s, a)
            depth += 1
        if game.is_terminal(s):
            w = game.winner(s)
            return 0.5 if w is None else (1.0 if w == root_player else 0.0)
        return game.evaluate(s, root_player)
