"""Convenience entry point: ``python main.py <command>`` does the same as
``python -m balancer <command>``.

With no command it runs a quick tour of the tool on Ember Duel: a balance
report and a card ablation on the planted_card preset, so a first-time user
sees the analyzer flag the planted overpowered card.

Examples:
    python main.py                                   # quick tour
    python main.py simulate --agents mcts:100 greedy --games 500
    python main.py ablate --preset planted_engine
    python main.py evaluate --quick
"""
import sys

from balancer.__main__ import main

TOUR = [
    ["simulate", "--preset", "planted_card", "--games", "1000"],
    ["ablate", "--preset", "planted_card", "--seeds", "300"],
]


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        for argv in TOUR:
            print(f"\n$ python -m balancer {' '.join(argv)}\n")
            main(argv)
