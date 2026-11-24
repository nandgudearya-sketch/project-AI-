"""
Card Duel: a small original two-player card game used as our test case.

Rules
-----
- Each player starts with some HP and their own shuffled deck.
- At the start of your turn your mana refills to (your turn number),
  capped at max_mana, and you draw one card.
- On your turn you may play any number of cards you can afford, then END.
- Cards can deal damage to the opponent, heal you, or draw more cards.
- Reduce the opponent to 0 HP to win. If max_turns is reached, the
  player with more HP wins (equal HP = draw).

Everything that affects balance lives in PARAMS, so the tool can tweak it.

PLANTED IMBALANCES (so we can check the tool finds them):
- "Dragon" is far too strong for its cost.
- "Pebble" is far too weak for its cost.
- No compensation for going second, so player 0 may have an advantage.
"""

import copy

from .game_interface import Game

END = "END"

DEFAULT_PARAMS = {
    "starting_hp": 20,
    "starting_hand": 4,
    "second_player_bonus_cards": 0,  # extra cards for player 1 at the start
    "max_mana": 8,
    "max_turns": 40,                 # total turns (both players) before the game ends
    "copies_per_card": 3,
    # For experiments: {player: (card_removed, card_added)} swaps one card type
    # in that player's deck only. Leave empty for normal games.
    "deck_swap": {},
    "cards": {
        #            cost  damage  heal  draw
        "Spark":    {"cost": 1, "damage": 2, "heal": 0, "draw": 0},
        "Bolt":     {"cost": 2, "damage": 3, "heal": 0, "draw": 0},
        "Fireball": {"cost": 4, "damage": 6, "heal": 0, "draw": 0},
        "Mend":     {"cost": 2, "damage": 0, "heal": 4, "draw": 0},
        "Insight":  {"cost": 2, "damage": 0, "heal": 0, "draw": 2},
        "Dragon":   {"cost": 3, "damage": 7, "heal": 0, "draw": 0},  # planted: too strong
        "Pebble":   {"cost": 3, "damage": 1, "heal": 0, "draw": 0},  # planted: too weak
    },
}


class PlayerState:
    __slots__ = ("hp", "mana", "hand", "deck", "turns_taken")

    def __init__(self, hp, mana, hand, deck, turns_taken):
        self.hp = hp
        self.mana = mana
        self.hand = hand
        self.deck = deck
        self.turns_taken = turns_taken

    def clone(self):
        return PlayerState(self.hp, self.mana, list(self.hand), list(self.deck), self.turns_taken)


class DuelState:
    __slots__ = ("players", "current", "turn", "done", "plays")

    def __init__(self, players, current, turn, done, plays):
        self.players = players
        self.current = current
        self.turn = turn
        self.done = done
        self.plays = plays  # plays[p] = list of card names player p played

    def clone(self):
        return DuelState(
            [p.clone() for p in self.players],
            self.current, self.turn, self.done,
            [list(self.plays[0]), list(self.plays[1])],
        )


class CardDuel(Game):

    def __init__(self, params=None):
        self.params = copy.deepcopy(DEFAULT_PARAMS)
        if params:
            for key, value in params.items():
                if key == "cards":
                    for name, stats in value.items():
                        self.params["cards"].setdefault(name, {}).update(stats)
                else:
                    self.params[key] = value
        self.cards = self.params["cards"]

    # ---------------- setup ----------------

    def initial_state(self, rng):
        p = self.params
        players = []
        for i in range(2):
            deck = [name for name in self.cards for _ in range(p["copies_per_card"])]
            if i in p["deck_swap"]:
                out_card, in_card = p["deck_swap"][i]
                deck = [in_card if c == out_card else c for c in deck]
            rng.shuffle(deck)
            hand_size = p["starting_hand"] + (p["second_player_bonus_cards"] if i == 1 else 0)
            hand = [deck.pop() for _ in range(min(hand_size, len(deck)))]
            players.append(PlayerState(p["starting_hp"], 0, hand, deck, 0))
        state = DuelState(players, current=0, turn=0, done=False, plays=[[], []])
        self._start_turn(state)
        return state

    def _start_turn(self, state):
        me = state.players[state.current]
        me.turns_taken += 1
        me.mana = min(me.turns_taken, self.params["max_mana"])
        self._draw(me, 1)

    @staticmethod
    def _draw(player, n):
        for _ in range(n):
            if player.deck:
                player.hand.append(player.deck.pop())

    # ---------------- Game interface ----------------

    def current_player(self, state):
        return state.current

    def legal_actions(self, state):
        me = state.players[state.current]
        playable = {c for c in me.hand if self.cards[c]["cost"] <= me.mana}
        return sorted(playable) + [END]

    def apply(self, state, action):
        s = state.clone()
        me = s.players[s.current]
        opp = s.players[1 - s.current]

        if action == END:
            s.turn += 1
            if s.turn >= self.params["max_turns"]:
                s.done = True
            else:
                s.current = 1 - s.current
                self._start_turn(s)
            return s

        card = self.cards[action]
        me.hand.remove(action)
        me.mana -= card["cost"]
        opp.hp -= card["damage"]
        me.hp = min(me.hp + card["heal"], self.params["starting_hp"])
        self._draw(me, card["draw"])
        s.plays[s.current].append(action)
        if opp.hp <= 0:
            s.done = True
        return s

    def is_terminal(self, state):
        return state.done

    def winner(self, state):
        hp0, hp1 = state.players[0].hp, state.players[1].hp
        if hp0 > hp1:
            return 0
        if hp1 > hp0:
            return 1
        return None

    # ---------------- optional hooks ----------------

    def determinize(self, state, player, rng):
        s = state.clone()
        rng.shuffle(s.players[player].deck)  # I don't know my own deck order
        opp = s.players[1 - player]
        hidden = opp.hand + opp.deck          # I don't know their hand or deck
        rng.shuffle(hidden)
        n = len(opp.hand)
        opp.hand, opp.deck = hidden[:n], hidden[n:]
        return s

    def action_value(self, state, action):
        if action == END:
            return 0.0
        c = self.cards[action]
        opp = state.players[1 - state.current]
        if c["damage"] >= opp.hp:
            return 1000.0  # lethal: always take it
        return c["damage"] + 0.75 * c["heal"] + 1.5 * c["draw"]

    def summary(self, state):
        return {"turns": state.turn, "plays": state.plays}
