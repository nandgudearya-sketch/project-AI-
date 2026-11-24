"""Tests for Claim (the third game), the cross-game comparison and the Claim web
page API. Run with:  python -m unittest discover tests"""
import random
import unittest

from balancer.agents import GreedyAgent, MCTSAgent, RandomAgent
from balancer.games import GAMES, make_game
from balancer.sim import play_game


class TestClaim(unittest.TestCase):
    def test_registered(self):
        self.assertEqual(set(GAMES), {"ember", "nim", "grid"})

    def test_random_games_fill_the_board(self):
        g = make_game("grid")
        for seed in range(100):
            s = g.initial_state(seed)
            rng = random.Random(seed)
            while not g.is_terminal(s):
                g.step(s, rng.choice(g.legal_actions(s)))
            self.assertTrue(all(o in (0, 1) for o in s.owner[:-1]))
            self.assertIn(g.winner(s), (0, 1, None))

    def test_adjacency_bonus(self):
        g = make_game("grid", {"size": 3, "adj_bonus": 2, "p2_start_points": 0})
        s = g.initial_state(1)
        vals = s.owner[-1]
        g.step(s, 0)          # player 1 takes corner 0
        g.step(s, 8)          # player 2 takes the far corner
        g.step(s, 1)          # player 1 takes cell 1, next to its cell 0
        self.assertEqual(s.scores[0], vals[0] + vals[1] + 2)
        self.assertEqual(s.scores[1], vals[8])

    def test_claimed_squares_are_not_legal(self):
        g = make_game("grid")
        s = g.initial_state(3)
        g.step(s, 5)
        self.assertNotIn(5, g.legal_actions(s))
        self.assertEqual(len(g.legal_actions(s)), g.n_cells - 1)

    def test_same_seed_same_game_and_legal_agents(self):
        g = make_game("grid")
        a = play_game(g, [GreedyAgent(), RandomAgent()], 7)
        b = play_game(g, [GreedyAgent(), RandomAgent()], 7)
        self.assertEqual((a.winner, a.scores), (b.winner, b.scores))
        s = g.initial_state(3)
        for agent in (RandomAgent(), GreedyAgent(), MCTSAgent(20)):
            self.assertIn(agent.act(g, s, random.Random(0)), g.legal_actions(s))

    def test_presets_valid_and_bad_params_rejected(self):
        for preset in ["default", *GAMES["grid"].PRESETS]:
            make_game("grid", GAMES["grid"].preset_params(preset))
        with self.assertRaises(ValueError):
            make_game("grid", {"no_such_param": 1})
        with self.assertRaises(ValueError):
            make_game("grid", {"adj_bonus": -1})


class TestClaimWebAPI(unittest.TestCase):
    def test_game_flow(self):
        from balancer.web import games_api
        v = games_api.new_game("default", "medium", 1, seed=2)
        self.assertTrue(v["your_turn"])
        while not v["result"]:
            free = [c["id"] for c in v["cells"] if c["gain"] is not None]
            v = games_api.act(v["id"], free[0])
        self.assertIn(v["result"], ("win", "loss", "draw"))
        with self.assertRaises(ValueError):
            games_api.act(v["id"], 0)

    def test_rejects_taken_square(self):
        from balancer.web import games_api
        v = games_api.new_game("default", "easy", 2, seed=1)   # AI moves first
        taken = next(c["id"] for c in v["cells"] if c["owner"] == "ai")
        with self.assertRaises(ValueError):
            games_api.act(v["id"], taken)


class TestCompare(unittest.TestCase):
    def test_compare_runs_on_all_games(self):
        from balancer.evaluation.compare import compare_games, format_compare
        rows = compare_games(agent="greedy", strong="greedy", n_games=40,
                             skill_games=20, workers=1, log=None)
        self.assertEqual([r.game for r in rows], ["ember", "nim", "grid"])
        self.assertIn("Planted imbalance detection", format_compare(rows))


if __name__ == "__main__":
    unittest.main()
