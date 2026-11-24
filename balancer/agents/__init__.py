"""Agents are created from short spec strings so they can be sent to worker
processes and written in configs:

    random            uniformly random legal moves
    greedy            one-ply lookahead on the game heuristic
    mcts:N            ISMCTS with N iterations per move (e.g. mcts:50, mcts:400)
    weighted:a=1;b=-0.5   a fixed priority strategy over action labels
    human             you, in the terminal
"""
from .base import Agent
from .mcts import MCTSAgent
from .simple import (GreedyAgent, HumanAgent, RandomAgent, WeightedAgent,
                     decode_weights, encode_weights)


def make_agent(spec: str) -> Agent:
    kind, _, arg = spec.partition(":")
    if kind == "random":
        return RandomAgent()
    if kind == "greedy":
        return GreedyAgent()
    if kind == "human":
        return HumanAgent()
    if kind == "mcts":
        agent = MCTSAgent(int(arg) if arg else 200)
        agent.spec = spec
        return agent
    if kind == "weighted":
        agent = WeightedAgent(decode_weights(arg))
        agent.spec = spec
        return agent
    raise ValueError(f"Unknown agent spec '{spec}'")


__all__ = ["Agent", "make_agent", "MCTSAgent", "GreedyAgent", "RandomAgent",
           "WeightedAgent", "HumanAgent", "encode_weights", "decode_weights"]
