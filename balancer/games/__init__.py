"""Game registry. To plug in a new game, implement ``Game`` and add it here."""
from .ember import EmberDuel
from .nim import Nim

GAMES = {g.name: g for g in (EmberDuel, Nim)}


def make_game(name, params=None):
    if name not in GAMES:
        raise ValueError(f"Unknown game '{name}'. Available: {', '.join(GAMES)}")
    return GAMES[name](params)
