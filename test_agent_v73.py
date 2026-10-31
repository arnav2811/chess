"""Offline regression tests for agent_v73_emperor.py.

These tests intentionally stub the ChessMaker board utility import. They verify
search-policy helpers and structural invariants, not live ChessMaker gameplay.
Run from the project root with: python -m unittest -v test_agent_v73.py
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
import unittest
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENGINE_PATH = ROOT / "agent_v73_emperor.py"
V71_PATH = ROOT / "agent_v71_adaptive_tactical_hybrid.py"

# Make the module importable without ChessMaker installed.
extension_pkg = types.ModuleType("extension")
extension_pkg.__path__ = []
board_utils = types.ModuleType("extension.board_utils")
board_utils.list_legal_moves_for = lambda board, player: []
sys.modules["extension"] = extension_pkg
sys.modules["extension.board_utils"] = board_utils

spec = importlib.util.spec_from_file_location("agent_v73_emperor", ENGINE_PATH)
engine = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(engine)


class Position:
    def __init__(self, x: int, y: int):
        self.x, self.y = x, y


class Player:
    def __init__(self, name: str):
        self.name = name


class Right:
    def __init__(self, x=0, y=0, side="white"):
        self.position = Position(x, y)
        self.player = Player(side)


class QuietMove:
    def __init__(self, x=1, y=1):
        self.position = Position(x, y)
        self.captures = set()


class EmptySquare:
    piece = None


class SignatureBoard:
    def __init__(self):
        self._squares = [[EmptySquare() for _ in range(5)] for _ in range(5)]
        self.current_player = Player("white")


class SearchPolicyTests(unittest.TestCase):
    def setUp(self):
        engine._killer_moves = {}
        engine._history = {}
        engine._last_root_evals = []
        engine._last_root_exact_evals = []
        engine._last_random_tiebreak = False

    def test_candidate_defaults_are_deterministic_and_puct_off(self):
        self.assertFalse(engine._ENABLE_ROOT_PUCT)
        self.assertFalse(engine._ENABLE_CHECK_EXTENSION)
        self.assertFalse(engine._ENABLE_ROOT_RANDOM_TIEBREAK)

    def test_lmr_starts_conservatively(self):
        p, m = Right(), QuietMove()
        self.assertEqual(engine._lmr_reduction(2, 10, p, m, False, False, 3), 0)
        self.assertEqual(engine._lmr_reduction(3, 2, p, m, False, False, 3), 0)
        self.assertEqual(engine._lmr_reduction(3, 3, p, m, False, False, 3), 1)

    def test_dynamic_lmr_two_ply_only_for_late_deep_quiet_move(self):
        p, m = Right(), QuietMove()
        self.assertEqual(engine._lmr_reduction(8, 11, p, m, False, False, 4), 2)
        self.assertEqual(engine._lmr_reduction(7, 11, p, m, False, False, 4), 1)

    def test_lmr_protects_tactical_checked_killer_and_strong_history_moves(self):
        p, m = Right(), QuietMove()
        self.assertEqual(engine._lmr_reduction(9, 15, p, m, True, False, 4), 0)
        self.assertEqual(engine._lmr_reduction(9, 15, p, m, False, True, 4), 0)
        bucket = engine._killer_bucket(p, 4)
        engine._killer_moves[bucket] = [engine._move_key(p, m)]
        self.assertEqual(engine._lmr_reduction(9, 15, p, m, False, False, 4), 0)
        engine._killer_moves.clear()
        engine._history[engine._heuristic_move_key(p, m)] = 300
        self.assertEqual(engine._lmr_reduction(9, 15, p, m, False, False, 4), 0)

    def test_tt_keeps_deeper_entry(self):
        engine._tt = OrderedDict()
        old_limit = engine._TT_MAX_SIZE
        engine._TT_MAX_SIZE = 10
        try:
            engine._store_tt_entry(101, 10, engine.TT_EXACT, 55, (0, 0, 1, 1), 2)
            engine._store_tt_entry(101, 3, engine.TT_UPPER, 12, (0, 0, 2, 2), 2)
            self.assertEqual(engine._tt[101][0], 10)
            self.assertEqual(engine._tt[101][3], (0, 0, 1, 1))
        finally:
            engine._TT_MAX_SIZE = old_limit

    def test_tt_evicts_least_recently_used_not_whole_table(self):
        engine._tt = OrderedDict()
        old_limit = engine._TT_MAX_SIZE
        engine._TT_MAX_SIZE = 2
        try:
            engine._store_tt_entry(1, 4, engine.TT_EXACT, 10, None, 0)
            engine._store_tt_entry(2, 4, engine.TT_EXACT, 20, None, 0)
            engine._tt.move_to_end(1)  # key 2 is now least recently used
            engine._store_tt_entry(3, 4, engine.TT_EXACT, 30, None, 0)
            self.assertEqual(list(engine._tt.keys()), [1, 3])
        finally:
            engine._TT_MAX_SIZE = old_limit
            engine._tt = OrderedDict()

    def test_root_tiebreak_disabled_preserves_classical_best_move(self):
        p, m = Right(), QuietMove()
        engine._last_root_evals = [(100, p, m), (99, Right(2, 2), QuietMove(3, 3))]
        engine._last_root_exact_evals = [(100, p, m), (99, Right(2, 2), QuietMove(3, 3))]
        engine._ENABLE_ROOT_RANDOM_TIEBREAK = False
        chosen = engine._apply_root_tiebreak(None, p, m, 1)
        self.assertIs(chosen[0], p)
        self.assertIs(chosen[1], m)
        self.assertFalse(engine._last_random_tiebreak)

    def test_optional_random_tiebreak_is_reproducible(self):
        p1, m1 = Right(0, 0, "white"), QuietMove(1, 1)
        p2, m2 = Right(2, 2, "white"), QuietMove(3, 3)
        engine._last_root_evals = [(100, p1, m1), (98, p2, m2)]
        engine._last_root_exact_evals = [(100, p1, m1), (98, p2, m2)]
        engine._ENABLE_ROOT_RANDOM_TIEBREAK = True
        board = SignatureBoard()
        first = engine._apply_root_tiebreak(board, p1, m1, 7)
        self.assertTrue(engine._last_random_tiebreak)
        second = engine._apply_root_tiebreak(board, p1, m1, 7)
        self.assertIs(first[0], second[0])
        self.assertIs(first[1], second[1])
        engine._ENABLE_ROOT_RANDOM_TIEBREAK = False

    def test_evaluator_is_unchanged_from_v71(self):
        if not V71_PATH.exists():
            self.skipTest("v7.1 source not present beside this test")

        def function_body(path: Path, name: str):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            body = list(node.body)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]
            return ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False)

        self.assertEqual(function_body(ENGINE_PATH, "evaluate_for_white"),
                         function_body(V71_PATH, "evaluate_for_white"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
