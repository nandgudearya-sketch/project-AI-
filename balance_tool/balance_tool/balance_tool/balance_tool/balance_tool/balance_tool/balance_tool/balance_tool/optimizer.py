"""Parameter optimizer: search for parameter changes that bring win rates close to 50%."""
import copy
import math
import random

from .card_duel import CardDuel
from .experiments import card_swap_test
from .report import seat_advantage
from .simulate import run_games

# Parameters the optimizer may change.  "Dragon.cost" means cards -> Dragon -> cost.
DEFAULT_SEARCH_SPACE = {
    "p1_extra_cards": [0, 1, 2, 3, 4],
    "p1_extra_hp": [0, 1, 2, 3, 4, 5, 6],
    "Dragon.cost": [3, 4, 5, 6],
    "Dragon.value": [3, 4, 5, 6, 7],
    "Pebble.cost": [1, 2, 3],
    "Pebble.value": [1, 2, 3, 4],
}


def set_param(params, key, value):
    if "." in key:
        card, field = key.split(".")
        params["cards"][card][field] = value
    else:
        params[key] = value


def get_param(params, key):
    if "." in key:
        card, field = key.split(".")
        return params["cards"][card][field]
    return params[key]


def measure(params, agent, games, swap_games, seed, reference="Bolt"):
    """Return (seat win rate of player 0, {card: swap win rate})."""
    game = CardDuel(params)
    mirror = run_games(game, [agent, agent], games, seed=seed)
    seat = seat_advantage(mirror)["rate"]
    swap = card_swap_test(game, agent, reference, swap_games, seed=seed + 1000)
    return seat, {r["card"]: r["rate"] for r in swap}


def loss(seat, swap, w_seat=2.0, w_card=3.0, cards=("Dragon", "Pebble")):
    """0 = perfectly balanced. Measures how far win rates are from 50%."""
    card_dev = sum(abs(swap[c] - 0.5) for c in cards if c in swap) / max(len(cards), 1)
    return w_seat * abs(seat - 0.5) + w_card * card_dev


def optimize(start_params, agent, search_space=None, method="hill", steps=40,
             games=400, swap_games=150, seed=0, log=print):
    """Stochastic hill climbing ('hill') or simulated annealing ('anneal').
    Every candidate is scored with the same random seeds, which reduces noise."""
    space = search_space or DEFAULT_SEARCH_SPACE
    rng = random.Random(seed)
    current = copy.deepcopy(start_params)
    seat, swap = measure(current, agent, games, swap_games, seed)
    cur_loss = loss(seat, swap)
    best, best_loss = copy.deepcopy(current), cur_loss
    log(f"start: loss={cur_loss:.3f} seat={seat:.1%} " + " ".join(f"{c}={v:.0%}" for c, v in swap.items() if c in ('Dragon', 'Pebble')))
    for step in range(steps):
        key = rng.choice(list(space))
        options = space[key]
        cand = copy.deepcopy(current)
        old = get_param(cand, key)
        new = rng.choice([v for v in options if v != old])
        set_param(cand, key, new)
        seat, swap = measure(cand, agent, games, swap_games, seed)
        cand_loss = loss(seat, swap)
        if method == "anneal":
            temp = 0.05 * (1 - step / steps) + 1e-6
            accept = cand_loss < cur_loss or rng.random() < math.exp(-(cand_loss - cur_loss) / temp)
        else:
            accept = cand_loss <= cur_loss
        if accept:
            current, cur_loss = cand, cand_loss
            log(f"step {step + 1}: {key} {old} -> {new}   loss={cand_loss:.3f} seat={seat:.1%}")
            if cur_loss < best_loss:
                best, best_loss = copy.deepcopy(current), cur_loss
    return best, best_loss


def verify(before, after, agent, games=2000, swap_games=500, seed=12345):
    """Re-measure both parameter sets with FRESH seeds, so the improvement is not overfitted."""
    rows = {}
    for label, params in (("before", before), ("after", after)):
        seat, swap = measure(params, agent, games, swap_games, seed)
        rows[label] = (seat, swap)
    return rows


def print_verification(rows, changes):
    print("\n" + "=" * 60)
    print("BEFORE / AFTER (fresh simulations)")
    print("=" * 60)
    print("Changes: " + (", ".join(f"{k}: {a} -> {b}" for k, (a, b) in changes.items()) or "none"))
    for label in ("before", "after"):
        seat, swap = rows[label]
        print(f"  {label:6s} player-0 win rate {seat:.1%} | Dragon-vs-Bolt {swap['Dragon']:.1%} | Pebble-vs-Bolt {swap['Pebble']:.1%}")
    print()
