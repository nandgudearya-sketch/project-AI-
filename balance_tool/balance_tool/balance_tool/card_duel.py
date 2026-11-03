"""Card Duel: a small two-player card game with deliberately planted imbalances.

Each turn you gain mana (your own turn number, capped at max_mana), draw a card,
and may play any cards you can afford. Cards deal damage, heal, or draw.
First player to reduce the opponent to 0 HP wins.

Planted imbalances (ground truth for evaluating the tool):
  * Dragon costs 3 but deals 7 damage        -> too strong
  * Pebble costs 3 but deals 1 damage        -> rarely played
  * p1_extra_cards = 0                       -> no compensation for going second
"""
import copy

from .game_interface import Game

DEFAULT_PARAMS = {
    "start_hp": 20,
    "max_mana": 8,
    "start_hand": 3,
    "max_hand": 7,
    "max_turns": 15,          # turns per player before the game is decided on HP
    "p1_extra_cards": 0,      # starting cards given to the second player as compensation
    "p1_extra_hp": 0,         # extra starting HP for the second player as compensation
    "cards": {
        "Spark":  {"cost": 1, "kind": "damage", "value": 1},
        "Strike": {"cost": 2, "kind": "damage", "value": 2},
        "Bolt":   {"cost": 3, "kind": "damage", "value": 3},
        "Dragon": {"cost": 3, "kind": "damage", "value": 7},   # planted: too strong
        "Pebble": {"cost": 3, "kind": "damage", "value": 1},   # planted: too weak
        "Heal":   {"cost": 2, "kind": "heal",   "value": 3},
        "Study":  {"cost": 2, "kind": "draw",   "value": 2},
    },
    "deck": {"Spark": 3, "Strike": 3, "Bolt": 4, "Dragon": 2,
             "Pebble": 2, "Heal": 3, "Study": 3},
}


class State:
    __slots__ = ("hp", "hands", "decks", "mana", "turns", "player", "ply", "plays", "drawn")

    def copy(self):
        s = State.__new__(State)
        s.hp = self.hp[:]
        s.hands = [h[:] for h in self.hands]
        s.decks = [d[:] for d in self.decks]
        s.mana = self.mana[:]
        s.turns = self.turns[:]
        s.player = self.player
        s.ply = self.ply
        s.plays = [dict(p) for p in self.plays]
        s.drawn = [dict(d) for d in self.drawn]
        return s


class CardDuel(Game):
    def __init__(self, params=None):
        self.params = copy.deepcopy(DEFAULT_PARAMS)
        if params:
            self.params.update(copy.deepcopy(params))
        self.cards = self.params["cards"]
        self.max_plies = 2 * self.params["max_turns"]

    # ---- setup ----------------------------------------------------------
    def deck_list(self):
        out = []
        for name, n in sorted(self.params["deck"].items()):
            out += [name] * n
        return out

    def initial_state(self, rng, decks=None):
        decks = decks or [self.deck_list(), self.deck_list()]
        s = State()
        s.hp = [self.params["start_hp"], self.params["start_hp"] + self.params["p1_extra_hp"]]
        s.hands = [[], []]
        s.decks = []
        for d in decks:
            d = list(d)
            rng.shuffle(d)
            s.decks.append(d)
        s.mana = [0, 0]
        s.turns = [0, 0]
        s.player = 0
        s.ply = 0
        s.plays = [{}, {}]
        s.drawn = [{}, {}]
        for p in (0, 1):
            n = self.params["start_hand"] + (self.params["p1_extra_cards"] if p == 1 else 0)
            self._draw(s, p, n)
        self._start_turn(s)
        return s

    def _max_hp(self, p):
        return self.params["start_hp"] + (self.params["p1_extra_hp"] if p == 1 else 0)

    def _draw(self, s, p, n):
        for _ in range(n):
            if not s.decks[p]:
                return
            card = s.decks[p].pop()
            if len(s.hands[p]) < self.params["max_hand"]:
                s.hands[p].append(card)
                s.drawn[p][card] = s.drawn[p].get(card, 0) + 1

    def _start_turn(self, s):
        p = s.player
        s.turns[p] += 1
        s.mana[p] = min(s.turns[p], self.params["max_mana"])
        self._draw(s, p, 1)

    # ---- rules ----------------------------------------------------------
    def current_player(self, state):
        return state.player

    def is_terminal(self, state):
        return state.hp[0] <= 0 or state.hp[1] <= 0 or state.ply >= self.max_plies

    def winner(self, state):
        if state.hp[1] <= 0:
            return 0
        if state.hp[0] <= 0:
            return 1
        if state.hp[0] > state.hp[1]:
            return 0
        if state.hp[1] > state.hp[0]:
            return 1
        return None

    def legal_actions(self, state):
        if self.is_terminal(state):
            return []
        p = state.player
        acts = [("play", n) for n in sorted(set(state.hands[p]))
                if self.cards[n]["cost"] <= state.mana[p]]
        acts.append(("end",))
        return acts

    def apply(self, state, action):
        s = state.copy()
        p, opp = s.player, 1 - s.player
        if action[0] == "play":
            name = action[1]
            card = self.cards[name]
            s.hands[p].remove(name)
            s.mana[p] -= card["cost"]
            s.plays[p][name] = s.plays[p].get(name, 0) + 1
            if card["kind"] == "damage":
                s.hp[opp] -= card["value"]
            elif card["kind"] == "heal":
                s.hp[p] = min(self._max_hp(p), s.hp[p] + card["value"])
            elif card["kind"] == "draw":
                self._draw(s, p, card["value"])
            return s
        s.player = opp
        s.ply += 1
        if not self.is_terminal(s):
            self._start_turn(s)
        return s

    # ---- optional hooks -------------------------------------------------
    def determinize(self, state, player, rng):
        s = state.copy()
        rng.shuffle(s.decks[player])
        opp = 1 - player
        pool = s.hands[opp] + s.decks[opp]
        rng.shuffle(pool)
        k = len(s.hands[opp])
        s.hands[opp], s.decks[opp] = pool[:k], pool[k:]
        return s

    def action_value(self, state, action):
        """Benefit per mana spent. Lethal damage is always worth taking."""
        if action[0] != "play":
            return 0.0
        p = state.player
        card = self.cards[action[1]]
        cost = max(card["cost"], 1)
        if card["kind"] == "damage":
            if card["value"] >= state.hp[1 - p]:
                return 1000.0
            return card["value"] / cost
        if card["kind"] == "heal":
            missing = self._max_hp(p) - state.hp[p]
            return 0.8 * min(card["value"], missing) / cost
        if card["kind"] == "draw":
            return 1.5 * card["value"] / cost if state.decks[p] else 0.0
        return 0.0

    def pass_action(self, state):
        return ("end",)

    def evaluate(self, state, player):
        diff = (state.hp[player] - state.hp[1 - player]) / self.params["start_hp"]
        return max(0.0, min(1.0, 0.5 + 0.5 * diff))

    def summary(self, state):
        return {"turns": max(state.turns), "plays": state.plays, "drawn": state.drawn,
                "hp": state.hp[:], "timeout": state.hp[0] > 0 and state.hp[1] > 0}

    def describe(self, state, player):
        opp = 1 - player
        return (f"You: {state.hp[player]} HP | Opponent: {state.hp[opp]} HP | "
                f"Opponent hand size: {len(state.hands[opp])}\n"
                f"Your mana: {state.mana[player]} | Your hand: {', '.join(state.hands[player]) or '(empty)'}")
