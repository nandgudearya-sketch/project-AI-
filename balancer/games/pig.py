"""Pig Race: a push-your-luck dice game, the third test case for the tool.

Rules (two players, alternating turns). On your turn you either:

* ``roll``: roll a die. A 1 ("bust") wipes your turn points and ends your turn.
  Any other number is added to your turn points. If your banked score plus
  turn points reaches ``target`` you win at once.
* ``hold``: bank your turn points and end your turn (needs turn points > 0).

If nobody has won after ``max_turns`` turns the higher banked score wins.

Fairness: going first is an edge in Pig. ``p2_start_points`` is the
compensation given to the second player, so it is the knob the tuner turns.
Unlike Nim there is luck, and unlike Ember there is no hidden hand: the only
hidden information is the future dice, which ``determinize`` re-rolls so search
agents cannot peek at the dice that are about to be thrown.

All dice are fixed by the seed when the state is created, so ``step`` is
deterministic and games are reproducible like the other games.
"""
from __future__ import annotations

import random

from ..core.game import Game

STREAM = 600  # pre-rolled dice per game; far more than any game uses

ROLL, HOLD = "roll", "hold"


class PigState:
    __slots__ = ("scores", "turn_pts", "player", "rolls", "idx", "turns", "win", "done")

    def __init__(self, scores, rolls, turn_pts=0, player=0, idx=0, turns=0,
                 win=None, done=False):
        self.scores, self.rolls = scores, rolls
        self.turn_pts, self.player, self.idx = turn_pts, player, idx
        self.turns, self.win, self.done = turns, win, done


class PigRace(Game):
    name = "pig"
    # mcts_c / rollout_depth: rollouts run to the end (no strong heuristic).
    DEFAULT_PARAMS = {"target": 50, "die_sides": 6, "p2_start_points": 0,
                      "max_turns": 60}
    PARAM_SPACE = {"target": (20, 100), "die_sides": (3, 12),
                   "p2_start_points": (0, 15), "max_turns": (20, 120)}
    PRESETS = {
        # Compensation that roughly cancels the first-move edge.
        "compensated": {"p2_start_points": 4},
        # Over-compensated: seat 2 should now be favoured.
        "planted_p2_edge": {"p2_start_points": 12},
        # A tiny target makes the first roller almost decisive.
        "planted_short": {"target": 20},
        # A huge target with few turns: games end on the turn limit.
        "planted_timeout": {"target": 100, "max_turns": 20},
    }

    def validate_params(self):
        p = self.params
        if p["die_sides"] < 2:
            raise ValueError("die_sides must be >= 2")
        if p["target"] < 1 or p["max_turns"] < 1:
            raise ValueError("target and max_turns must be >= 1")
        if p["p2_start_points"] < 0:
            raise ValueError("p2_start_points must be >= 0")

    # ------------------------------------------------------------ core rules
    def _dice(self, rng):
        return [rng.randint(1, self.params["die_sides"]) for _ in range(STREAM)]

    def initial_state(self, seed):
        rng = random.Random(seed)
        return PigState([0, self.params["p2_start_points"]], self._dice(rng))

    def clone(self, s):
        # ``rolls`` is never mutated, so clones share it.
        return PigState(list(s.scores), s.rolls, s.turn_pts, s.player, s.idx,
                        s.turns, s.win, s.done)

    def determinize(self, s, player, rng):
        c = self.clone(s)
        # Nobody can know the dice still to come: re-roll them.
        c.rolls = s.rolls[:s.idx] + [rng.randint(1, self.params["die_sides"])
                                     for _ in range(len(s.rolls) - s.idx)]
        return c

    def current_player(self, s):
        return s.player

    def legal_actions(self, s):
        if s.done:
            return []
        return [ROLL, HOLD] if s.turn_pts > 0 else [ROLL]

    def _pass_turn(self, s):
        s.turn_pts = 0
        s.player = 1 - s.player
        s.turns += 1
        if s.turns >= self.params["max_turns"]:
            s.done = True
            a, b = s.scores
            s.win = None if a == b else (0 if a > b else 1)

    def step(self, s, action):
        p = s.player
        if action == HOLD:
            s.scores[p] += s.turn_pts
            self._pass_turn(s)
            return
        r = s.rolls[s.idx % len(s.rolls)]
        s.idx += 1
        if r == 1:
            self._pass_turn(s)
            return
        s.turn_pts += r
        if s.scores[p] + s.turn_pts >= self.params["target"]:
            s.scores[p] += s.turn_pts
            s.turn_pts = 0
            s.win, s.done = p, True

    def is_terminal(self, s):
        return s.done

    def winner(self, s):
        return s.win

    # -------------------------------------------------------- agent helpers
    def heuristic(self, s, player):
        t = self.params["target"]
        me, opp = s.scores[player], s.scores[1 - player]
        return min(1.0, max(0.0, 0.5 + (me - opp) / (2.0 * t)))

    # ------------------------------------------------------ analytics hooks
    def all_action_labels(self):
        return [ROLL, HOLD]

    def action_label(self, s, a):
        return a

    def turn_count(self, s):
        return s.turns

    def hit_turn_limit(self, s):
        return s.done and s.turns >= self.params["max_turns"] and s.win is not None \
            and max(s.scores) < self.params["target"]

    def final_scores(self, s):
        return self.returns(s)

    # ------------------------------------------------------------ humans
    def render(self, s, viewer):
        you = s.scores[viewer]
        opp = s.scores[1 - viewer]
        return (f"Target {self.params['target']} | you {you} | opponent {opp} | "
                f"turn points at risk: {s.turn_pts}")

    def describe_action(self, s, a):
        return "roll the die" if a == ROLL else f"hold and bank {s.turn_pts}"
