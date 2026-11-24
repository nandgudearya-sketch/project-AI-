"""JSON API for the "Claim" page: play Claim against the AI, run the balance
analyzer on any game, and see the saved comparison of all games.

Kept separate from ``server.py`` (which is specific to Ember Duel) so the two
pages can change independently; ``server.py`` only forwards ``/api/games/*``
requests here.
"""
from __future__ import annotations

import json
import math
import random
import threading
import time
import uuid
from pathlib import Path

from ..agents import make_agent
from ..analysis.balance import analyze, skill_gap
from ..games import GAMES, make_game
from ..sim.harness import Simulator

DIFFICULTIES = {"easy": "random", "medium": "greedy", "hard": "mcts:300"}
SIM_AGENTS = ["random", "greedy", "mcts:50", "mcts:100"]
MAX_SIM_GAMES = 2000
MAX_SESSIONS = 200
COMPARE_FILE = Path(__file__).resolve().parents[2] / "docs" / "figures" / "game_comparison.json"

INFO = {
    "ember": {"title": "Ember Duel", "kind": "Card game with hidden hands",
              "tests": "Card strength (planted: Flare too cheap)"},
    "nim": {"title": "Nim", "kind": "Perfect information, solved by maths",
            "tests": "A known answer (pile 20: the second player should always win)"},
    "grid": {"title": "Claim", "kind": "Perfect-information board game",
             "tests": "First-move advantage (planted: no compensation for moving second)",
             "rules": "Take turns claiming a square. You score its number, plus a bonus "
                      "for each of your own squares next to it. When the board is full, "
                      "the higher score wins. The second player starts with bonus points "
                      "to make up for moving second."},
}
PRESET_NOTES = {
    ("ember", "planted_card"): "Flare costs 1 and scores 6.",
    ("ember", "planted_seat"): "The second player loses their compensation.",
    ("ember", "planted_engine"): "Hearth costs 2.",
    ("ember", "planted_dud"): "Inferno costs more than you can ever afford.",
    ("ember", "planted_long"): "The target is 200 points, so games time out.",
    ("nim", "second_player_wins"): "Pile of 20: with perfect play the second player wins.",
    ("grid", "planted_seat"): "No bonus points for moving second.",
    ("grid", "planted_snowball"): "Big bonus for neighbouring squares.",
}

_sessions: dict[str, dict] = {}
_lock = threading.Lock()
_sim_lock = threading.Lock()


def _num(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


# ------------------------------------------------------------------ play
def _log(sess, who, text):
    sess["log"].append({"who": who, "text": text})


def _step(sess, who, a):
    g, s = sess["game"], sess["state"]
    _log(sess, who, f"claimed square {a + 1} (value {s.owner[-1][a]}, "
                    f"+{g.gain(s, a, s.player)} points)")
    g.step(s, a)


def _view(sess):
    g, s, me = sess["game"], sess["state"], sess["seat"]
    o = 1 - me
    done = g.is_terminal(s)
    mine = (not done) and s.player == me
    result = None
    if done:
        w = g.winner(s)
        result = "draw" if w is None else ("win" if w == me else "loss")
    n = g.params["size"]
    return {
        "id": sess["id"], "preset": sess["preset"], "seat": me + 1, "your_turn": mine,
        "result": result, "log": sess["log"][-40:], "size": n,
        "you": s.scores[me], "ai": s.scores[o], "adj_bonus": g.params["adj_bonus"],
        "p2_bonus": g.params["p2_start_points"],
        "cells": [{"id": i, "value": s.owner[-1][i],
                   "owner": None if s.owner[i] is None else ("you" if s.owner[i] == me else "ai"),
                   "gain": g.gain(s, i, me) if (mine and s.owner[i] is None) else None}
                  for i in range(n * n)],
    }


def _advance(sess):
    g, s, me = sess["game"], sess["state"], sess["seat"]
    while not g.is_terminal(s) and s.player != me:
        _step(sess, "ai", sess["agent"].act(g, s, sess["rng"]))
    if g.is_terminal(s):
        w = g.winner(s)
        _log(sess, "system", "Draw." if w is None else ("You win!" if w == me else "The AI wins."))


def new_game(preset="default", difficulty="medium", seat=1, seed=None):
    if preset not in ("default", *GAMES["grid"].PRESETS):
        raise ValueError(f"Unknown preset '{preset}'")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown difficulty '{difficulty}'")
    if seat not in (1, 2):
        raise ValueError("seat must be 1 or 2")
    seed = random.randrange(10**9) if seed is None else int(seed)
    g = make_game("grid", GAMES["grid"].preset_params(preset))
    sess = {"id": uuid.uuid4().hex[:12], "game": g, "state": g.initial_state(seed),
            "seat": seat - 1, "preset": preset, "agent": make_agent(DIFFICULTIES[difficulty]),
            "rng": random.Random(seed + 1), "log": [], "touched": time.time()}
    bonus = g.params["p2_start_points"]
    _log(sess, "system", "You go first." if seat == 1 else
         f"The AI goes first. You start with {bonus} bonus points.")
    _advance(sess)
    with _lock:
        if len(_sessions) >= MAX_SESSIONS:
            del _sessions[min(_sessions, key=lambda k: _sessions[k]["touched"])]
        _sessions[sess["id"]] = sess
    return _view(sess)


def act(session_id, action):
    with _lock:
        sess = _sessions.get(session_id)
    if sess is None:
        raise KeyError("This game has expired. Start a new game.")
    g, s = sess["game"], sess["state"]
    if g.is_terminal(s):
        raise ValueError("The game is over. Start a new game.")
    if s.player != sess["seat"]:
        raise ValueError("It is not your turn.")
    action = int(action)
    if action not in g.legal_actions(s):
        raise ValueError("That square is already taken.")
    _step(sess, "you", action)
    _advance(sess)
    sess["touched"] = time.time()
    return _view(sess)


# --------------------------------------------------------------- balance
def simulate(name="grid", preset="default", agents=("mcts:50", "mcts:50"), games=600,
             luck=True, workers=None):
    if name not in GAMES:
        raise ValueError(f"Unknown game '{name}'")
    if preset not in ("default", *GAMES[name].PRESETS):
        raise ValueError(f"Unknown preset '{preset}'")
    agents = list(agents)
    if len(agents) != 2 or any(a not in SIM_AGENTS for a in agents):
        raise ValueError(f"Agents must be two of: {', '.join(SIM_AGENTS)}")
    games = max(20, min(int(games), MAX_SIM_GAMES))
    params = GAMES[name].preset_params(preset)
    labels = make_game(name, params).all_action_labels()
    start = time.time()
    with _sim_lock, Simulator(workers) as sim:
        rep = analyze(sim.match(name, params, agents, games, 11), labels)
        sk = skill_gap(name, params, "mcts:100", "random", 100, sim=sim) if luck else None
    issues = [{"kind": i.kind, "subject": i.subject, "message": i.message} for i in rep.issues]
    if sk and sk["issue"]:
        issues.append({"kind": "luck", "subject": "skill", "message": sk["issue"].message})
    return {
        "game": name, "preset": preset, "agents": agents, "games": rep.n_games,
        "seconds": round(time.time() - start, 1),
        "seat1": rep.seat0_score, "seat1_ci": list(rep.seat0_ci),
        "length": {"median": rep.length_p50, "p10": rep.length_p10, "p90": rep.length_p90,
                   "timeout_rate": rep.timeout_rate},
        "skill": None if sk is None else {"score": sk["score"], "ci": list(sk["ci"])},
        "labels": [{"name": c.label.capitalize(), "play_rate": c.play_rate,
                    "lift": c.lift if c.n_oh else None, "z": _num(c.z) if c.n_oh else None}
                   for c in rep.cards],
        "issues": issues,
    }


def compare():
    """Saved results of ``python -m balancer compare --json docs/figures/game_comparison.json``."""
    if not COMPARE_FILE.exists():
        raise KeyError("No saved comparison yet. Run: python -m balancer compare "
                       "--json docs/figures/game_comparison.json")
    return {"rows": json.loads(COMPARE_FILE.read_text())}


def config():
    return {
        "games": [{"id": k, **INFO[k],
                   "presets": [{"id": "default", "note": "The balanced version."}] +
                              [{"id": p, "note": PRESET_NOTES.get((k, p), "")}
                               for p in GAMES[k].PRESETS]}
                  for k in INFO],
        "difficulties": [{"id": "easy", "label": "Easy", "about": "Random moves"},
                         {"id": "medium", "label": "Medium", "about": "Takes the best square now"},
                         {"id": "hard", "label": "Hard", "about": "Tree search (MCTS)"}],
        "sim_agents": SIM_AGENTS,
    }


def handle_get(path):
    if path == "/api/games/config":
        return config()
    if path == "/api/games/compare":
        return compare()
    return None


def handle_post(path, data, workers=None):
    if path == "/api/games/new":
        return new_game(data.get("preset", "default"), data.get("difficulty", "medium"),
                        int(data.get("seat", 1)), data.get("seed"))
    if path == "/api/games/act":
        return act(data.get("id", ""), data.get("action"))
    if path == "/api/games/simulate":
        return simulate(data.get("game", "grid"), data.get("preset", "default"),
                        data.get("agents", ["mcts:50", "mcts:50"]), data.get("games", 600),
                        bool(data.get("luck", True)), workers)
    return None
