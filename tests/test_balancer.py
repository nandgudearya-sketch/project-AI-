"""Run with:  python -m unittest discover tests"""
import random
import unittest

from balancer.agents import GreedyAgent, MCTSAgent, RandomAgent, make_agent
from balancer.analysis import analyze, wilson
from balancer.games import GAMES, make_game
from balancer.games.ember import CARD_NAMES, END
from balancer.sim import play_game, run_games


class TestEmberEngine(unittest.TestCase):
    def setUp(self):
        self.g = make_game("ember")

    def test_random_games_terminate_and_conserve_cards(self):
        total = len(CARD_NAMES) * self.g.params["copies"]
        for seed in range(200):
            s = self.g.initial_state(seed)
            rng = random.Random(seed)
            while not self.g.is_terminal(s):
                for p in (0, 1):
                    self.assertLessEqual(len(s.hands[p]) + len(s.decks[p]), total)
                    self.assertGreaterEqual(s.points[p], 0)
                self.g.step(s, rng.choice(self.g.legal_actions(s)))
            self.assertIn(self.g.winner(s), (0, 1, None))

    def test_same_seed_same_game(self):
        a = play_game(self.g, [RandomAgent(), RandomAgent()], 42)
        b = play_game(self.g, [RandomAgent(), RandomAgent()], 42)
        self.assertEqual((a.winner, a.turns, a.plays), (b.winner, b.turns, b.plays))

    def test_legal_actions_are_affordable(self):
        s = self.g.initial_state(3)
        for a in self.g.legal_actions(s):
            if a != END:
                self.assertLessEqual(self.g.cost[a], s.energy)
                self.assertIn(a, s.hands[s.player])

    def test_apply_does_not_mutate(self):
        s = self.g.initial_state(5)
        before = (s.hands[0][:], s.points[:], s.energy)
        self.g.apply(s, self.g.legal_actions(s)[-1])
        self.assertEqual(before, (s.hands[0][:], s.points[:], s.energy))

    def test_determinize_keeps_visible_info(self):
        s = self.g.initial_state(7)
        rng = random.Random(0)
        for _ in range(20):
            d = self.g.determinize(s, 0, rng)
            self.assertEqual(sorted(d.hands[0]), sorted(s.hands[0]))
            self.assertEqual(len(d.hands[1]), len(s.hands[1]))
            self.assertEqual(sorted(d.hands[1] + d.decks[1]), sorted(s.hands[1] + s.decks[1]))
            self.assertEqual(d.points, s.points)

    def test_turn_limit(self):
        g = make_game("ember", {"target_points": 999, "max_turns": 10})
        s = g.initial_state(1)
        while not g.is_terminal(s):
            g.step(s, END)
        self.assertTrue(g.hit_turn_limit(s))
        self.assertEqual(s.total_turns, 10)

    def test_bad_params_rejected(self):
        with self.assertRaises(ValueError):
            make_game("ember", {"nonexistent": 1})
        with self.assertRaises(ValueError):
            make_game("ember", {"flare.cost": -1})

    def test_all_presets_valid(self):
        for name, cls in GAMES.items():
            for preset in ["default", *cls.PRESETS]:
                make_game(name, cls.preset_params(preset))


class TestAgents(unittest.TestCase):
    def test_specs(self):
        for spec in ["random", "greedy", "mcts:10", "weighted:spark=1;flare=-0.5"]:
            self.assertIsNotNone(make_agent(spec))
        with self.assertRaises(ValueError):
            make_agent("nope")

    def test_agents_return_legal_moves(self):
        g = make_game("ember")
        s = g.initial_state(11)
        rng = random.Random(0)
        for agent in [RandomAgent(), GreedyAgent(), MCTSAgent(30),
                      make_agent("weighted:flare=1")]:
            self.assertIn(agent.act(g, s, rng), g.legal_actions(s))

    def test_mcts_finds_winning_nim_move(self):
        g = make_game("nim", {"pile": 7, "max_take": 3})
        s = g.initial_state(0)
        self.assertEqual(MCTSAgent(400).act(g, s, random.Random(0)), 3)  # leave 4

    def test_greedy_beats_random(self):
        recs = run_games("ember", make_game("ember").params, ["greedy", "random"], 40, workers=1)
        greedy_score = sum(r.result(r.seats.index("greedy")) for r in recs) / len(recs)
        self.assertGreater(greedy_score, 0.8)


class TestAnalysis(unittest.TestCase):
    def test_wilson(self):
        lo, hi = wilson(50, 100)
        self.assertAlmostEqual((lo + hi) / 2, 0.5, places=2)
        self.assertLess(hi - lo, 0.21)
        self.assertEqual(wilson(0, 0), (0.0, 1.0))

    def test_detects_planted_seat_advantage(self):
        cls = GAMES["ember"]
        params = cls.preset_params("planted_seat")
        recs = run_games("ember", params, ["greedy", "greedy"], 600, workers=1)
        rep = analyze(recs, cls().all_action_labels())
        self.assertTrue(rep.has("seat", "first"))

    def test_detects_dead_card(self):
        cls = GAMES["ember"]
        params = cls.preset_params("planted_dud")
        recs = run_games("ember", params, ["greedy", "greedy"], 400, workers=1)
        rep = analyze(recs, cls().all_action_labels())
        self.assertTrue(rep.has("dead", "inferno"))


if __name__ == "__main__":
    unittest.main()
