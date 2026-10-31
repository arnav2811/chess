"""Offline structural tests for agent_v72_mobility_aware.py.

These tests deliberately stub extension.board_utils so they can run without
ChessMaker installed. They test the new ordering-key logic, not live gameplay.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V71_CANDIDATES = [
    ROOT / "agent_v71_adaptive_tactical_hybrid.py",
    ROOT / "engine_audit" / "agent_v71_adaptive_tactical_hybrid.py",
]
V71 = next((p for p in V71_CANDIDATES if p.exists()), V71_CANDIDATES[0])
V72 = ROOT / "agent_v72_mobility_aware.py"

# Stub only the external helper import; the tested routines below do not call it.
extension_pkg = types.ModuleType("extension")
extension_pkg.__path__ = []
board_utils_mod = types.ModuleType("extension.board_utils")
board_utils_mod.list_legal_moves_for = lambda board, player: []
sys.modules.setdefault("extension", extension_pkg)
sys.modules["extension.board_utils"] = board_utils_mod

spec = importlib.util.spec_from_file_location("agent_v72_test", V72)
agent = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = agent
assert spec.loader is not None
spec.loader.exec_module(agent)


class Position:
    def __init__(self, x, y):
        self.x, self.y = x, y


class Player:
    def __init__(self, name):
        self.name = name


class Right:
    def __init__(self, side, x, y):
        self.player = Player(side)
        self.position = Position(x, y)


class Queen:
    def __init__(self, side, x, y):
        self.player = Player(side)
        self.position = Position(x, y)


class Move:
    def __init__(self, x, y, captures=()):
        self.position = Position(x, y)
        self.captures = set(captures)


class Square:
    def __init__(self, piece=None):
        self.piece = piece


class Board:
    def __init__(self, pieces):
        self._pieces = pieces
        self.current_player = Player("white")
        self.map = {(p.position.x, p.position.y): p for p in pieces}

    def get_pieces(self):
        return list(self._pieces)

    def __getitem__(self, pos):
        if hasattr(pos, "x"):
            key = (pos.x, pos.y)
        else:
            key = tuple(pos)
        return Square(self.map.get(key))


class V72Tests(unittest.TestCase):
    def setUp(self):
        agent._killer_moves = {}
        agent._history = {}

    def test_puct_is_disabled_by_default(self):
        self.assertFalse(agent._ENABLE_ROOT_PUCT)
        self.assertTrue(agent._ENABLE_CHECK_EXTENSION)
        self.assertTrue(agent._ENABLE_QUIET_CHECK_ORDERING)

    def test_history_keys_separate_side_and_piece_type(self):
        white_right = Right("white", 0, 2)
        black_right = Right("black", 0, 2)
        white_queen = Queen("white", 0, 2)
        move = Move(1, 2)
        agent._update_history(white_right, move, 4)
        self.assertGreater(agent._history[agent._heuristic_move_key(white_right, move)], 0)
        self.assertNotIn(agent._heuristic_move_key(black_right, move), agent._history)
        self.assertNotIn(agent._heuristic_move_key(white_queen, move), agent._history)

    def test_killer_buckets_separate_side_and_piece_type(self):
        white_right = Right("white", 0, 2)
        black_right = Right("black", 0, 2)
        white_queen = Queen("white", 0, 2)
        move = Move(1, 2)
        agent._store_killer(3, white_right, move)
        self.assertIn(agent._move_key(white_right, move),
                      agent._killer_moves[agent._killer_bucket(white_right, 3)])
        self.assertNotIn(agent._killer_bucket(black_right, 3), agent._killer_moves)
        self.assertNotIn(agent._killer_bucket(white_queen, 3), agent._killer_moves)

    def test_quiet_check_orders_above_killer(self):
        checking_right = Right("white", 0, 2)
        killer_queen = Queen("white", 0, 0)
        checking_move = Move(3, 2)  # Right attacks enemy king at (4, 2).
        killer_move = Move(1, 0)
        enemy_king = type("King", (), {})()
        enemy_king.player = Player("black")
        enemy_king.position = Position(4, 2)
        board = Board([checking_right, killer_queen, enemy_king])
        agent._store_killer(0, killer_queen, killer_move)
        ordered = agent._order_moves([(killer_queen, killer_move),
                                     (checking_right, checking_move)], board, 0)
        self.assertEqual(agent._move_key(*ordered[0]),
                         agent._move_key(checking_right, checking_move))

    def test_eval_function_body_unchanged_from_v71(self):
        def function_body(path, name):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            body = list(fn.body)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                body = body[1:]
            return ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)
        if not V71.exists():
            self.skipTest("Place agent_v71_adaptive_tactical_hybrid.py beside this test to compare evaluator bodies.")
        self.assertEqual(function_body(V71, "evaluate_for_white"),
                         function_body(V72, "evaluate_for_white"))


    def test_sample1_right_infiltration_is_detected_as_check(self):
        black_right = Right("black", 0, 3)
        white_king = type("King", (), {})()
        white_king.player = Player("white")
        white_king.position = Position(2, 4)
        board = Board([black_right, white_king])
        self.assertTrue(agent._is_in_check(board))

        # The precursor move Right (1,1)->(0,3) is correctly recognised as a
        # direct check against the king at (2,4), due to Right's knight jump.
        precursor = Right("black", 1, 1)
        precursor_board = Board([precursor, white_king])
        checking_move = Move(0, 3)
        check_data = agent._check_prefilter_data(precursor_board, "black")
        self.assertTrue(agent._move_might_give_check(
            precursor_board, precursor, checking_move, check_data))

    def test_check_extension_has_absolute_ply_cap(self):
        self.assertEqual(agent._CHECK_EXTENSION_MAX_PLY, 10)
        source = V72.read_text(encoding="utf-8")
        self.assertIn("_ENABLE_CHECK_EXTENSION and in_check and depth >= 1", source)
        self.assertIn("ply_from_root < _CHECK_EXTENSION_MAX_PLY", source)
        self.assertIn("_last_check_extensions += 1", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
