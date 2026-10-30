import unittest
from pathlib import Path
import selfplay_control_runner as runner


class SelfPlayScheduleTests(unittest.TestCase):
    def test_100_game_schedule_balances_boards(self):
        tasks = runner.build_schedule("v69", 100, 730069, 14.0, 300.0)
        self.assertEqual(len(tasks), 100)
        counts = {b: sum(t["board"] == b for t in tasks) for b in runner.BOARDS}
        self.assertEqual(counts, {b: 20 for b in runner.BOARDS})

    def test_pairs_swap_colour_random_streams(self):
        tasks = runner.build_schedule("v71", 50, 730169, 14.0, 300.0)
        by_pair = {}
        for t in tasks:
            by_pair.setdefault(t["pair_id"], []).append(t)
        self.assertEqual(len(by_pair), 25)
        for pair in by_pair.values():
            self.assertEqual(len(pair), 2)
            a = next(x for x in pair if x["pair_variant"] == "A")
            b = next(x for x in pair if x["pair_variant"] == "B")
            self.assertEqual(a["board"], b["board"])
            self.assertEqual(a["seed"], b["seed"])
            self.assertEqual(a["white_rng_seed"], b["black_rng_seed"])
            self.assertEqual(a["black_rng_seed"], b["white_rng_seed"])

    def test_selfplay_summary_counts_winner_colours(self):
        results = [
            {"game_id": 1, "pair_id": 1, "board": "sample0", "winner_color": "white", "outcome": "WHITE_WIN", "plies": 20, "wall_time_s": 10},
            {"game_id": 2, "pair_id": 1, "board": "sample0", "winner_color": "white", "outcome": "WHITE_WIN", "plies": 22, "wall_time_s": 12},
            {"game_id": 3, "pair_id": 2, "board": "sample1", "winner_color": "black", "outcome": "BLACK_WIN", "plies": 18, "wall_time_s": 9},
            {"game_id": 4, "pair_id": 2, "board": "sample1", "winner_color": None, "outcome": "DRAW", "plies": 30, "wall_time_s": 15},
        ]
        s = runner.summarize(results, "v69", elapsed=20)
        self.assertEqual(s["games_completed"], 4)
        self.assertEqual(s["winner_color"]["white_wins"], 2)
        self.assertEqual(s["winner_color"]["black_wins"], 1)
        self.assertEqual(s["winner_color"]["draws"], 1)
        self.assertEqual(s["paired_rng_stream_results"]["white_wins_both"], 1)
        self.assertEqual(s["paired_rng_stream_results"]["draw_or_mixed"], 1)

    def test_terminal_parser(self):
        self.assertEqual(runner.terminal_winner("Checkmate - black loses"), ("white", False))
        self.assertEqual(runner.terminal_winner("Stalemate (no more possible moves) - white loses"), ("black", False))
        self.assertEqual(runner.terminal_winner("Draw - fivefold repetition"), (None, True))

    def test_expected_source_hashes_match_bundle_candidates(self):
        for filename, expected in runner.ENGINE_HASHES.items():
            self.assertEqual(runner.canonical_sha256(Path(runner.ROOT) / filename), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
