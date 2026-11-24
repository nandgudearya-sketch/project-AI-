"""Game registry. To plug in a new game, implement ``Game`` and add it here.

    ember   Ember Duel: card game with hidden hands (main test case)
    nim     Subtraction Nim: perfect information, known theoretical answer
    pig     Pig Race: push-your-luck dice game
    grid    Claim: perfect-information board game, tests first-move advantage
"""
from .ember import EmberDuel
from .grid import Claim
from .nim import Nim
from .pig import PigRace

GAMES = {g.name: g for g in (EmberDuel, Nim, PigRace, Claim)}


def make_game(name, params=None):
    if name not in GAMES:
        raise ValueError(f"Unknown game '{name}'. Available: {', '.join(GAMES)}")
    return GAMES[name](params)
