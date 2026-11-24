"""A small JSON API plus one static page, using only the standard library.

The page never sees hidden information: the API sends the human player's own
hand, public scores, and only the *number* of cards in the opponent's hand.
Every AI move is chosen by the same agents the simulator uses.
"""
from __future__ import annotations

import json
import math
import random
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..agents import make_agent
from ..analysis.balance import analyze
from ..games import GAMES, make_game
from ..games.ember import CARD_NAMES, END
from ..sim.harness import Simulator
from . import games_api

STATIC = Path(__file__).parent / "static"

DIFFICULTIES = {
    "easy": {"spec": "random", "label": "Easy", "about": "Plays any legal move"},
    "medium": {"spec": "greedy", "label": "Medium", "about": "Plans its own turn, ignores yours"},
    "hard": {"spec": "mcts:300", "label": "Hard", "about": "Tree search over possible futures"},
}
PRESET_NOTES = {
    "default": "The balanced version of the game.",
    "planted_seat": "The second player loses their compensation.",
    "planted_card": "Flare costs 1 and scores 6.",
    "planted_engine": "Hearth costs 2.",
    "planted_dud": "Inferno costs 10, more than your maximum energy.",
    "planted_long": "The target is 200 points, so games time out.",
}
SIM_AGENTS = ["random", "greedy", "mcts:50", "mcts:200"]
MAX_SESSIONS = 200
MAX_SIM_GAMES = 4000

_sessions: dict[str, dict] = {}
_lock = threading.Lock()
_sim_lock = threading.Lock()


# ------------------------------------------------------------------ game API
def _card_info(g, c):
    kind = ("growth" if g.grow[c] else "steal" if g.steal[c] else
            "draw" if g.draw[c] else "energy" if g.egain[c] else "points")
    effects = []
    if g.pts[c]:
        effects.append(f"+{g.pts[c]} points")
    if g.grow[c]:
        effects.append(f"+{g.grow[c]} growth")
    if g.draw[c]:
        effects.append(f"Draw {g.draw[c]}")
    if g.egain[c]:
        effects.append(f"+{g.egain[c]} energy")
    if g.steal[c]:
        effects.append(f"Opponent −{g.steal[c]}")
    return {"id": c, "name": CARD_NAMES[c].capitalize(), "cost": g.cost[c],
            "kind": kind, "effects": effects}


def _describe(g, a):
    if a == END:
        return "ended the turn"
    info = _card_info(g, a)
    return f"played {info['name']} ({', '.join(info['effects']) or 'no effect'})"


def _view(sess):
    g, s, me = sess["game"], sess["state"], sess["seat"]
    o = 1 - me
    my_turn = (not s.done) and s.player == me
    legal = set(g.legal_actions(s)) if my_turn else set()
    hand = []
    for c in sorted(s.hands[me], key=lambda c: (g.cost[c], c)):
        info = _card_info(g, c)
        info["playable"] = c in legal
        hand.append(info)
    result = None
    if s.done:
        result = "draw" if s.win is None else ("win" if s.win == me else "loss")
    return {
        "id": sess["id"],
        "preset": sess["preset"],
        "difficulty": sess["difficulty"],
        "target": g.params["target_points"],
        "max_turns": g.params["max_turns"],
        "turn": min(s.total_turns + 1, g.params["max_turns"]),
        "your_turn": my_turn,
        "energy": s.energy if my_turn else 0,
        "you": {"points": s.points[me], "growth": s.growth[me], "deck": len(s.decks[me]),
                "seat": me + 1},
        "opponent": {"points": s.points[o], "growth": s.growth[o], "deck": len(s.decks[o]),
                     "hand": len(s.hands[o]),
                     "revealed": [_card_info(g, c) for c in s.hands[o]] if s.done else None},
        "hand": hand,
        "log": sess["log"][-40:],
        "result": result,
        "timed_out": s.timed_out,
    }


def _log(sess, who, text):
    s = sess["state"]
    sess["log"].append({"who": who, "text": text, "turn": s.total_turns + 1})


def _run_ai(sess, announce=False):
    g, s, me = sess["game"], sess["state"], sess["seat"]
    while not s.done and s.player != me:
        a = sess["agent"].act(g, s, sess["rng"])
        _log(sess, "ai", _describe(g, a))
        g.step(s, a)
        announce = True
    if s.done:
        if s.win is None:
            _log(sess, "system", "The game is a draw.")
        else:
            _log(sess, "system", "You win." if s.win == me else "The AI wins.")
    elif announce:
        _log(sess, "system", f"Your turn. You have {s.energy} energy.")


def new_game(preset="default", difficulty="medium", seat=1, seed=None):
    if preset not in ("default", *GAMES["ember"].PRESETS):
        raise ValueError(f"Unknown preset '{preset}'")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown difficulty '{difficulty}'")
    if seat not in (1, 2):
        raise ValueError("seat must be 1 or 2")
    seed = random.randrange(10**9) if seed is None else int(seed)
    g = make_game("ember", GAMES["ember"].preset_params(preset))
    sess = {"id": uuid.uuid4().hex[:12], "game": g, "state": g.initial_state(seed),
            "seat": seat - 1, "agent": make_agent(DIFFICULTIES[difficulty]["spec"]),
            "rng": random.Random(seed + 1), "log": [], "preset": preset,
            "difficulty": difficulty, "touched": time.time()}
    _log(sess, "system", "You go first." if seat == 1 else
         "The AI goes first. You start with bonus points and an extra card.")
    _run_ai(sess, announce=True)
    with _lock:
        if len(_sessions) >= MAX_SESSIONS:
            oldest = min(_sessions, key=lambda k: _sessions[k]["touched"])
            del _sessions[oldest]
        _sessions[sess["id"]] = sess
    return _view(sess)


def act(session_id, action):
    with _lock:
        sess = _sessions.get(session_id)
    if sess is None:
        raise KeyError("This game has expired. Start a new game.")
    g, s = sess["game"], sess["state"]
    if s.done:
        raise ValueError("The game is over. Start a new game.")
    if s.player != sess["seat"]:
        raise ValueError("It is not your turn.")
    action = int(action)
    if action not in g.legal_actions(s):
        raise ValueError("You can't play that card right now.")
    _log(sess, "you", _describe(g, action))
    g.step(s, action)
    _run_ai(sess)
    sess["touched"] = time.time()
    return _view(sess)


# --------------------------------------------------------------- balance API
def _num(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    return x


def simulate(preset="default", agents=("greedy", "greedy"), games=1000, workers=None):
    if preset not in ("default", *GAMES["ember"].PRESETS):
        raise ValueError(f"Unknown preset '{preset}'")
    agents = list(agents)
    if len(agents) != 2 or any(a not in SIM_AGENTS for a in agents):
        raise ValueError(f"Agents must be two of: {', '.join(SIM_AGENTS)}")
    games = max(20, min(int(games), MAX_SIM_GAMES))
    params = GAMES["ember"].preset_params(preset)
    labels = make_game("ember", params).all_action_labels()
    start = time.time()
    with _sim_lock, Simulator(workers) as sim:
        recs = sim.match("ember", params, agents, games, 11)
    rep = analyze(recs, labels)
    return {
        "preset": preset, "agents": agents, "games": rep.n_games,
        "seconds": round(time.time() - start, 1),
        "seat1": rep.seat0_score, "seat1_ci": list(rep.seat0_ci),
        "draws": rep.draws,
        "length": {"mean": rep.length_mean, "p10": rep.length_p10,
                   "median": rep.length_p50, "p90": rep.length_p90,
                   "timeout_rate": rep.timeout_rate},
        "agent_scores": {k: {"score": v["score"], "ci": list(v["ci"])}
                         for k, v in rep.agent_scores.items()},
        "cards": [{"name": c.label.capitalize(), "play_rate": c.play_rate,
                   "lift": c.lift, "z": _num(c.z), "wr_oh": _num(c.wr_oh),
                   "wr_not": _num(c.wr_not)} for c in sorted(rep.cards, key=lambda c: -c.lift)],
        "issues": [{"kind": i.kind, "subject": i.subject, "message": i.message}
                   for i in rep.issues],
    }


def config():
    g = make_game("ember")
    return {
        "difficulties": [{"id": k, **{x: v[x] for x in ("label", "about")}}
                         for k, v in DIFFICULTIES.items()],
        "presets": [{"id": k, "note": v} for k, v in PRESET_NOTES.items()],
        "sim_agents": SIM_AGENTS,
        "cards": [_card_info(g, c) for c in range(len(CARD_NAMES))],
        "rules": {k: g.params[k] for k in ("target_points", "max_turns", "max_energy",
                                           "start_hand", "p2_extra_cards", "p2_start_points")},
    }


# ------------------------------------------------------------------- Pig API
PIG_PRESET_NOTES = {
    "default": "No compensation: the first player has a small edge.",
    "compensated": "Second player starts with 4 points, which evens things out.",
    "planted_p2_edge": "Second player starts with 12 points (too generous).",
    "planted_short": "Target is only 20, so games are very short.",
    "planted_timeout": "Target 100 but only 20 turns, so most games time out.",
}


def _pig_view(sess):
    g, s, me = sess["game"], sess["state"], sess["seat"]
    my_turn = (not s.done) and s.player == me
    result = None
    if s.done:
        result = "draw" if s.win is None else ("win" if s.win == me else "loss")
    return {
        "id": sess["id"], "preset": sess["preset"], "difficulty": sess["difficulty"],
        "target": g.params["target"], "max_turns": g.params["max_turns"],
        "turn": min(s.turns + 1, g.params["max_turns"]),
        "your_turn": my_turn, "turn_pts": s.turn_pts,
        "you": s.scores[me], "opponent": s.scores[1 - me], "seat": me + 1,
        "can_hold": my_turn and s.turn_pts > 0,
        "last_roll": sess.get("last_roll"),
        "log": sess["log"][-40:], "result": result,
    }


def _pig_step(sess, a, who):
    g, s = sess["game"], sess["state"]
    before_pts, idx = s.turn_pts, s.idx
    g.step(s, a)
    if a == "hold":
        text = f"held and banked {before_pts}"
    else:
        r = s.rolls[idx % len(s.rolls)]
        sess["last_roll"] = r
        text = f"rolled a {r}" + (" (bust, turn points lost)" if r == 1 else "")
    sess["log"].append({"who": who, "text": text, "turn": s.turns + 1})


def _pig_run_ai(sess):
    g, s, me = sess["game"], sess["state"], sess["seat"]
    while not s.done and s.player != me:
        _pig_step(sess, sess["agent"].act(g, s, sess["rng"]), "ai")
    if s.done:
        msg = ("The game is a draw." if s.win is None else
               "You win." if s.win == me else "The AI wins.")
        sess["log"].append({"who": "system", "text": msg, "turn": s.turns + 1})


def pig_new(preset="default", difficulty="medium", seat=1, seed=None):
    if preset not in PIG_PRESET_NOTES:
        raise ValueError(f"Unknown preset '{preset}'")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"Unknown difficulty '{difficulty}'")
    if seat not in (1, 2):
        raise ValueError("seat must be 1 or 2")
    seed = random.randrange(10**9) if seed is None else int(seed)
    g = make_game("pig", GAMES["pig"].preset_params(preset))
    # Greedy's turn planner does not suit Pig (see README); Medium uses a light MCTS.
    spec = "mcts:40" if difficulty == "medium" else DIFFICULTIES[difficulty]["spec"]
    sess = {"id": uuid.uuid4().hex[:12], "game": g, "state": g.initial_state(seed),
            "seat": seat - 1, "agent": make_agent(spec), "rng": random.Random(seed + 1),
            "log": [], "preset": preset, "difficulty": difficulty, "touched": time.time()}
    sess["log"].append({"who": "system", "turn": 1, "text":
                        "You go first." if seat == 1 else "The AI goes first."})
    _pig_run_ai(sess)
    with _lock:
        if len(_sessions) >= MAX_SESSIONS:
            del _sessions[min(_sessions, key=lambda k: _sessions[k]["touched"])]
        _sessions[sess["id"]] = sess
    return _pig_view(sess)


def pig_act(session_id, action):
    with _lock:
        sess = _sessions.get(session_id)
    if sess is None:
        raise KeyError("This game has expired. Start a new game.")
    g, s = sess["game"], sess["state"]
    if s.done:
        raise ValueError("The game is over. Start a new game.")
    if s.player != sess["seat"]:
        raise ValueError("It is not your turn.")
    if action not in g.legal_actions(s):
        raise ValueError("You can't do that right now.")
    _pig_step(sess, action, "you")
    _pig_run_ai(sess)
    sess["touched"] = time.time()
    return _pig_view(sess)


def pig_config():
    return {"difficulties": [{"id": k, **{x: v[x] for x in ("label", "about")}}
                             for k, v in DIFFICULTIES.items()],
            "presets": [{"id": k, "note": v} for k, v in PIG_PRESET_NOTES.items()]}


# ---------------------------------------------------------------- HTTP layer
class Handler(BaseHTTPRequestHandler):
    server_version = "EmberDuel/1.0"
    workers = None

    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def _send(self, status, body: bytes, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode())

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(HTTPStatus.OK, (STATIC / "index.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/pig":
            self._send(HTTPStatus.OK, (STATIC / "pig.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/api/pig/config":
            self._json(HTTPStatus.OK, pig_config())
        elif self.path == "/api/config":
            self._json(HTTPStatus.OK, config())
        elif self.path in ("/games", "/games.html"):
            self._send(HTTPStatus.OK, (STATIC / "games.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/games/figure.png" and games_api.COMPARE_FILE.with_suffix(".png").exists():
            self._send(HTTPStatus.OK, games_api.COMPARE_FILE.with_suffix(".png").read_bytes(),
                       "image/png")
        elif self.path.startswith("/api/games/"):
            try:
                out = games_api.handle_get(self.path)
            except KeyError as e:
                return self._json(HTTPStatus.NOT_FOUND, {"error": str(e.args[0])})
            if out is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            self._json(HTTPStatus.OK, out)
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/new":
                out = new_game(data.get("preset", "default"), data.get("difficulty", "medium"),
                               int(data.get("seat", 1)), data.get("seed"))
            elif self.path == "/api/pig/new":
                out = pig_new(data.get("preset", "default"), data.get("difficulty", "medium"),
                              int(data.get("seat", 1)), data.get("seed"))
            elif self.path == "/api/pig/act":
                out = pig_act(data.get("id", ""), data.get("action"))
            elif self.path == "/api/act":
                out = act(data.get("id", ""), data.get("action"))
            elif self.path == "/api/simulate":
                out = simulate(data.get("preset", "default"),
                               data.get("agents", ["greedy", "greedy"]),
                               data.get("games", 1000), self.workers)
            elif self.path.startswith("/api/games/"):
                out = games_api.handle_post(self.path, data, self.workers)
                if out is None:
                    return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            else:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            self._json(HTTPStatus.OK, out)
        except KeyError as e:
            self._json(HTTPStatus.GONE, {"error": str(e.args[0])})
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})


def serve(host="127.0.0.1", port=8000, open_browser=True, workers=None):
    Handler.workers = workers
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Ember Duel is running at {url}  |  Pig Race at {url}/pig  (press Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
