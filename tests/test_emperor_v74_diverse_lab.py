import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Offline tests for unique-position v7.4 self-play tooling (no ChessMaker needed)."""
import unittest
from emperor_v74_diverse_selfplay import BOARDS, LAYOUT_ROWS, position_signature, summarize
from analyze_emperor_v74_selfplay import analyse_games


class DiverseLabTests(unittest.TestCase):
    def test_thirteen_layouts_are_unique(self):
        self.assertEqual(len(BOARDS), 13)
        self.assertEqual(len(set(LAYOUT_ROWS.values())), 13)

    def test_new_standard_layouts_have_one_of_each_back_rank_piece(self):
        expected = sorted(["Right", "Bishop", "King", "Queen", "Knight"])
        for name in BOARDS:
            if int(name[6:]) >= 5:
                black, white = LAYOUT_ROWS[name]
                self.assertEqual(sorted(black), expected, name)
                self.assertEqual(sorted(white), expected, name)
                self.assertEqual(black[2], "King", name)
                self.assertEqual(white[2], "King", name)

    def test_position_signature_includes_side_to_move(self):
        state = [{"piece": "king", "side": "white", "x": 2, "y": 4},
                 {"piece": "king", "side": "black", "x": 2, "y": 0}]
        self.assertNotEqual(position_signature(state, "white"), position_signature(state, "black"))

    def test_analyser_finds_immediate_major_hang(self):
        before = [
            {"piece": "right", "side": "white", "x": 0, "y": 4},
            {"piece": "king", "side": "white", "x": 2, "y": 4},
            {"piece": "right", "side": "black", "x": 0, "y": 0},
            {"piece": "king", "side": "black", "x": 2, "y": 0},
        ]
        after = [
            {"piece": "right", "side": "white", "x": 3, "y": 2},
            {"piece": "king", "side": "white", "x": 2, "y": 4},
            {"piece": "right", "side": "black", "x": 0, "y": 0},
            {"piece": "king", "side": "black", "x": 2, "y": 0},
        ]
        game = {"game_id": 1, "board": "sample0", "opening_signature": "abc",
                "opening_side_to_move": "white", "opening_plies": 4,
                "outcome": "BLACK_WIN", "plies": 6,
                "moves": [
                    {"ply": 5, "side": "white", "pre_state": before, "post_state": after,
                     "move": {"piece": "right", "from": [0, 4], "to": [3, 2], "captures": []}, "search": {}},
                    {"ply": 6, "side": "black", "pre_state": after,
                     "post_state": [p for p in after if not (p["side"] == "white" and p["piece"] == "right")],
                     "move": {"piece": "bishop", "from": [1, 4], "to": [3, 2], "captures": [[3, 2]]}, "search": {}},
                ]}
        report, events, bank, _ = analyse_games([game])
        self.assertEqual(report["major_piece_hangs"], 1)
        self.assertTrue(any(e["type"] == "immediate_major_piece_hang" for e in events))
        self.assertTrue(any(row["type"] == "immediate_major_piece_hang" for row in bank))

    def test_analyser_identifies_promotion_allowed_on_next_ply(self):
        state = [
            {"piece": "pawn", "side": "white", "x": 4, "y": 1},
            {"piece": "king", "side": "white", "x": 2, "y": 4},
            {"piece": "king", "side": "black", "x": 2, "y": 0},
        ]
        next_state = [
            {"piece": "queen", "side": "white", "x": 4, "y": 0},
            {"piece": "king", "side": "white", "x": 2, "y": 4},
            {"piece": "king", "side": "black", "x": 2, "y": 0},
        ]
        game = {"game_id": 2, "board": "sample1", "opening_signature": "def",
                "opening_side_to_move": "black", "opening_plies": 5,
                "outcome": "WHITE_WIN", "plies": 7,
                "moves": [
                    {"ply": 6, "side": "black", "pre_state": state, "post_state": state,
                     "move": {"piece": "king", "from": [2, 0], "to": [1, 0], "captures": []}, "search": {}},
                    {"ply": 7, "side": "white", "pre_state": state, "post_state": next_state,
                     "move": {"piece": "pawn", "from": [4, 1], "to": [4, 0], "captures": []}, "search": {}},
                ]}
        report, events, _, _ = analyse_games([game])
        self.assertEqual(report["promotions_allowed_next_ply"], 1)
        self.assertTrue(any(e["type"] == "promotion_played" for e in events))

    def test_guard_diagnostics_are_counted(self):
        state = [{"piece": "king", "side": "white", "x": 2, "y": 4},
                 {"piece": "king", "side": "black", "x": 2, "y": 0}]
        game = {"game_id": 3, "board": "sample2", "opening_signature": "ghi",
                "opening_side_to_move": "white", "opening_plies": 4,
                "outcome": "DRAW", "plies": 5,
                "moves": [{"ply": 5, "side": "white", "pre_state": state, "post_state": state,
                           "move": {"piece": "king", "from": [2, 4], "to": [1, 4], "captures": []},
                           "search": {"material_guard": True, "material_guard_replacement": True,
                                      "promotion_guard": True, "promotion_guard_replacement": False}}]}
        report, _, _, _ = analyse_games([game])
        self.assertEqual(report["guard_counters"]["material_guard_triggers"], 1)
        self.assertEqual(report["guard_counters"]["material_guard_replacements"], 1)
        self.assertEqual(report["guard_counters"]["promotion_guard_triggers"], 1)

    def test_complete_trajectory_hash_includes_randomized_opening(self):
        common_move = {"ply": 5, "side": "white", "move": {"piece": "pawn", "from": [0, 3], "to": [0, 2], "captures": []}}
        games = [
            {"game_id": 1, "opening_plies": 4, "opening_signature": "a", "opening_moves": [
                {"side": "white", "piece": "pawn", "from": [0, 3], "to": [0, 2], "captures": []}], "moves": [common_move]},
            {"game_id": 2, "opening_plies": 4, "opening_signature": "b", "opening_moves": [
                {"side": "white", "piece": "pawn", "from": [1, 3], "to": [1, 2], "captures": []}], "moves": [common_move]},
        ]
        result = summarize(games)
        self.assertEqual(result["unique_complete_trajectories"], 2)
        self.assertEqual(result["repeated_trajectory_games"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
