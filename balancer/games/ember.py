"""Ember Duel: a small original two-player card game used as the main test case.

Rules
-----
* Each player has their own shuffled deck containing ``copies`` of every card.
* Players start with ``start_hand`` cards; the second player gets
  ``p2_extra_cards`` more as compensation for going second.
* At the start of your turn: gain energy equal to your turn number (capped at
  ``max_energy``; the first player also gets ``first_player_bonus_energy``),
  score your growth, then draw ``draw_per_turn`` cards.
* On your turn, play any affordable cards one at a time, then end your turn.
  Unspent energy is lost.
* The first player to reach ``target_points`` wins immediately. If the game
  reaches ``max_turns`` total turns, the higher score wins (equal = draw).

Card effects (all tunable): ``points`` (score now), ``draw`` (draw cards),
``energy`` (gain energy this turn), ``steal`` (opponent loses points),
``growth`` (score this much at the start of each of your future turns).
"""
from __future__ import annotations

import math
import random

from ..core.game import Game

END = -1

CARD_NAMES = [
    "spark", "ember", "flare", "blaze", "inferno",
    "kindle", "bellows", "siphon", "hearth", "phoenix",
]
EFFECTS = ("cost", "points", "draw", "energy", "steal", "growth")

_BASE_CARDS = {
    "spark":   dict(cost=1, points=1),
    "ember":   dict(cost=2, points=3),
    "flare":   dict(cost=3, points=4),
    "blaze":   dict(cost=5, points=7),
    "inferno": dict(cost=7, points=10),
    "kindle":  dict(cost=2, draw=2),
    "bellows": dict(cost=1, energy=2),
    "siphon":  dict(cost=3, steal=4),
    "hearth":  dict(cost=4, growth=1),
    "phoenix": dict(cost=6, points=4, growth=1),
}


def _default_params() -> dict:
    p = dict(
        target_points=40,
        max_turns=40,          # total turns (both players) before a points decision
        max_energy=8,
        start_hand=4,
        p2_extra_cards=1,
        p2_start_points=4,
        first_player_bonus_energy=0,
        draw_per_turn=1,
        hand_limit=10,
        copies=2,
    )
    for name, card in _BASE_CARDS.items():
        for eff in EFFECTS:
            p[f"{name}.{eff}"] = card.get(eff, 0)
    return p


def _param_space() -> dict:
    space = dict(
        target_points=(20, 80),
        max_turns=(20, 60),
        max_energy=(4, 12),
        start_hand=(2, 7),
        p2_extra_cards=(0, 3),
        p2_start_points=(0, 10),
        first_player_bonus_energy=(0, 3),
        draw_per_turn=(1, 2),
    )
    for name in CARD_NAMES:
        space[f"{name}.cost"] = (0, 10)
        space[f"{name}.points"] = (0, 15)
        for eff in ("draw", "energy", "steal", "growth"):
            space[f"{name}.{eff}"] = (0, 5)
    return space


class EmberState:
    __slots__ = ("hands", "decks", "points", "growth", "energy", "player",
                 "turns", "total_turns", "done", "win", "timed_out")

    def copy(self) -> "EmberState":
        s = EmberState.__new__(EmberState)
        s.hands = [self.hands[0][:], self.hands[1][:]]
        s.decks = [self.decks[0][:], self.decks[1][:]]
        s.points = self.points[:]
        s.growth = self.growth[:]
        s.energy = self.energy
        s.player = self.player
        s.turns = self.turns[:]
        s.total_turns = self.total_turns
        s.done = self.done
        s.win = self.win
        s.timed_out = self.timed_out
        return s


class EmberDuel(Game):
    name = "ember"
    rollout_depth = 6   # short rollouts, then the heuristic: random card play is noisy
    mcts_c = 0.5        # heuristic values are close together, so explore less
    DEFAULT_PARAMS = _default_params()
    PARAM_SPACE = _param_space()
    PRESETS = {
        # Planted imbalance 1: going first is much better.
        "planted_seat": {"p2_extra_cards": 0, "p2_start_points": 0},
        # Planted imbalance 2: one card is far too cheap for what it does.
        "planted_card": {"flare.cost": 1, "flare.points": 6},
        # Planted imbalance 2b: a growth engine that is far too cheap.
        "planted_engine": {"hearth.cost": 2},
        # Planted imbalance 3: one card is almost never playable.
        "planted_dud": {"inferno.cost": 10},
        # Planted imbalance 4: the target is so high that games time out.
        "planted_long": {"target_points": 200},
    }

    def __init__(self, params=None):
        super().__init__(params)
        p = self.params
        self.cost = [p[f"{n}.cost"] for n in CARD_NAMES]
        self.pts = [p[f"{n}.points"] for n in CARD_NAMES]
        self.draw = [p[f"{n}.draw"] for n in CARD_NAMES]
        self.egain = [p[f"{n}.energy"] for n in CARD_NAMES]
        self.steal = [p[f"{n}.steal"] for n in CARD_NAMES]
        self.grow = [p[f"{n}.growth"] for n in CARD_NAMES]

    def validate_params(self):
        p = self.params
        for key, val in p.items():
            if isinstance(val, (int, float)) and val < 0:
                raise ValueError(f"{key} must be non-negative")
        if p["target_points"] < 1 or p["max_turns"] < 2:
            raise ValueError("target_points >= 1 and max_turns >= 2 required")
        if p["copies"] < 1 or p["hand_limit"] < 1:
            raise ValueError("copies and hand_limit must be >= 1")

    # ------------------------------------------------------------ setup
    def initial_state(self, seed: int) -> EmberState:
        rng = random.Random(seed)
        p = self.params
        s = EmberState()
        s.decks = []
        for _ in range(2):
            deck = [c for c in range(len(CARD_NAMES)) for _ in range(p["copies"])]
            rng.shuffle(deck)
            s.decks.append(deck)
        s.hands = [[], []]
        s.points = [0, p["p2_start_points"]]
        s.growth = [0, 0]
        s.energy = 0
        s.player = 0
        s.turns = [0, 0]
        s.total_turns = 0
        s.done = False
        s.win = None
        s.timed_out = False
        self._draw(s, 0, p["start_hand"])
        self._draw(s, 1, p["start_hand"] + p["p2_extra_cards"])
        self._begin_turn(s)
        return s

    def clone(self, state):
        return state.copy()

    # ------------------------------------------------------------ helpers
    def _draw(self, s, player, n):
        deck, hand, limit = s.decks[player], s.hands[player], self.params["hand_limit"]
        for _ in range(n):
            if not deck:
                return
            card = deck.pop()
            if len(hand) < limit:
                hand.append(card)        # cards drawn over the limit are burned

    def _check_win(self, s, player):
        if s.points[player] >= self.params["target_points"]:
            s.done = True
            s.win = player

    def _begin_turn(self, s):
        p = s.player
        s.turns[p] += 1
        s.energy = min(s.turns[p], self.params["max_energy"])
        if p == 0:
            s.energy += self.params["first_player_bonus_energy"]
        s.points[p] += s.growth[p]
        self._check_win(s, p)
        if not s.done:
            self._draw(s, p, self.params["draw_per_turn"])

    # ------------------------------------------------------------ rules
    def current_player(self, state):
        return state.player

    def legal_actions(self, s):
        if s.done:
            return []
        acts = [END]
        seen = set()
        cost, e = self.cost, s.energy
        for c in s.hands[s.player]:
            if c not in seen and cost[c] <= e:
                seen.add(c)
                acts.append(c)
        return acts

    def step(self, s, a):
        p = s.player
        if a == END:
            s.total_turns += 1
            if s.total_turns >= self.params["max_turns"]:
                s.done = True
                s.timed_out = True
                if s.points[0] != s.points[1]:
                    s.win = 0 if s.points[0] > s.points[1] else 1
                return
            s.player = 1 - p
            self._begin_turn(s)
            return
        s.hands[p].remove(a)
        s.energy += self.egain[a] - self.cost[a]
        s.points[p] += self.pts[a]
        s.growth[p] += self.grow[a]
        if self.steal[a]:
            o = 1 - p
            s.points[o] = max(0, s.points[o] - self.steal[a])
        if self.draw[a]:
            self._draw(s, p, self.draw[a])
        self._check_win(s, p)

    def is_terminal(self, s):
        return s.done

    def winner(self, s):
        return s.win

    # ------------------------------------------------- hidden information
    def determinize(self, s, player, rng):
        """The viewer knows their own hand and both scores; they do not know the
        opponent's hand or either deck order. Re-deal those."""
        c = s.copy()
        o = 1 - player
        pool = c.hands[o] + c.decks[o]
        rng.shuffle(pool)
        n = len(c.hands[o])
        c.hands[o] = pool[:n]
        c.decks[o] = pool[n:]
        rng.shuffle(c.decks[player])
        return c

    # ------------------------------------------------------ agent helpers
    def _value(self, s, player):
        o = 1 - player
        remaining = max(0, self.params["max_turns"] - s.total_turns) / 2
        horizon = min(remaining, 6)
        mine = s.points[player] + s.growth[player] * horizon + 0.8 * len(s.hands[player])
        theirs = s.points[o] + s.growth[o] * horizon + 0.8 * len(s.hands[o])
        return mine - theirs

    def heuristic(self, s, player):
        if s.done:
            return self.returns(s)[player]
        return 1.0 / (1.0 + math.exp(-self._value(s, player) / 6.0))

    def rollout_action(self, s, rng):
        """Cheap informed rollout policy: usually play the card with the best
        rough immediate value, sometimes act randomly (including ending the turn)."""
        acts = self.legal_actions(s)
        if len(acts) == 1:
            return END
        if rng.random() < 0.7:
            return max(acts[1:], key=lambda c: self.pts[c] + 2 * self.grow[c]
                       + 0.8 * self.draw[c] + 0.5 * self.steal[c] + 0.1 * rng.random())
        return acts[rng.randrange(len(acts))]

    # ---------------------------------------------------------- analytics
    def all_action_labels(self):
        return list(CARD_NAMES)

    def action_label(self, s, a):
        return None if a == END else CARD_NAMES[a]

    def opening_labels(self, s, player):
        return {CARD_NAMES[c] for c in s.hands[player]}

    def turn_count(self, s):
        return s.total_turns

    def hit_turn_limit(self, s):
        return s.timed_out

    def final_scores(self, s):
        return list(s.points)

    # ------------------------------------------------------------- humans
    def card_text(self, c):
        bits = []
        if self.pts[c]:
            bits.append(f"+{self.pts[c]} pts")
        if self.draw[c]:
            bits.append(f"draw {self.draw[c]}")
        if self.egain[c]:
            bits.append(f"+{self.egain[c]} energy")
        if self.steal[c]:
            bits.append(f"opponent -{self.steal[c]} pts")
        if self.grow[c]:
            bits.append(f"+{self.grow[c]} growth")
        return f"{CARD_NAMES[c]} (cost {self.cost[c]}): {', '.join(bits) or 'no effect'}"

    def describe_action(self, s, a):
        return "end turn" if a == END else f"play {self.card_text(a)}"

    def render(self, s, viewer):
        o = 1 - viewer
        lines = [
            f"Turn {s.total_turns + 1}/{self.params['max_turns']}  "
            f"(target {self.params['target_points']} pts)",
            f"  You:      {s.points[viewer]} pts, growth {s.growth[viewer]}, "
            f"deck {len(s.decks[viewer])}",
            f"  Opponent: {s.points[o]} pts, growth {s.growth[o]}, "
            f"hand {len(s.hands[o])}, deck {len(s.decks[o])}",
        ]
        if s.player == viewer:
            lines.append(f"  Energy: {s.energy}")
        lines.append("  Your hand:")
        for c in sorted(s.hands[viewer]):
            lines.append(f"    - {self.card_text(c)}")
        return "\n".join(lines)
