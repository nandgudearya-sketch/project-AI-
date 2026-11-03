"""Plug a second game (Nim) into the same agents, simulator and checks.

Example:
    python run_second_game.py
    python run_second_game.py --stones 20      # 20 stones: the SECOND player should win
"""
import argparse

from balance_tool.agents import GreedyAgent, RandomAgent
from balance_tool.nim_game import Nim
from balance_tool.report import game_length, print_report, seat_advantage, skill_gap
from balance_tool.simulate import run_games


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stones", type=int, default=21)
    ap.add_argument("--games", type=int, default=1000)
    args = ap.parse_args()
    game = Nim(stones=args.stones)
    mirror = run_games(game, [GreedyAgent(), GreedyAgent()], args.games, seed=0)
    skill = run_games(game, [GreedyAgent(), RandomAgent()], args.games, seed=1, swap_seats=True)
    print_report(seat_advantage(mirror), game_length(mirror, game.params["max_turns"]),
                 skill_gap(skill, strong_agent=0))


if __name__ == "__main__":
    main()
