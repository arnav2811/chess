"""Offline regression tests for the v7.4 Tactical Guard.

ChessMaker is stubbed. These tests exercise the guard's material accounting,
promotion-threat detection, and conservative root-alternative policy; they do
not replace live ChessMaker validation or gameplay testing.
"""
from __future__ import annotations
import importlib.util
import ast
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V73_PATH = ROOT / "agent_v73_emperor.py"
PKG = types.ModuleType("extension")
PKG.__path__ = []
BU = types.ModuleType("extension.board_utils")
BU.list_legal_moves_for = lambda board, player: []
sys.modules["extension"] = PKG
sys.modules["extension.board_utils"] = BU
spec = importlib.util.spec_from_file_location(
    "agent_v74_tactical_guard", ROOT / "agent_v74_tactical_guard.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class Pos:
    def __init__(self, x, y):
        self.x, self.y = x, y

    def __hash__(self):
        return hash((self.x, self.y))

    def __eq__(self, other):
        return getattr(other, "x", None) == self.x and getattr(other, "y", None) == self.y


class Player:
    def __init__(self, name):
        self.name = name


class Piece:
    def __init__(self, name, side, x=0, y=0):
        self.player = Player(side)
        self.position = Pos(x, y)
        self.__class__ = type(name.title(), (), {})
        self.player = Player(side)
        self.position = Pos(x, y)


class Move:
    def __init__(self, x, y, captures=()):
        self.position = Pos(x, y)
        self.captures = set(captures)


class Square:
    def __init__(self, piece=None):
        self.piece = piece


class Board:
    def __init__(self, turn, pieces):
        self.current_player = Player(turn)
        self.pieces = list(pieces)
        self.squares = {(p.position.x, p.position.y): Square(p) for p in pieces}

    def __getitem__(self, pos):
        return self.squares.get((pos.x, pos.y), Square())


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.old_moves = engine.list_legal_moves_for
        self.old_clone = engine._make_move_on_clone
        self.old_status = engine._tactical_guard_status
        self.move_map = {}
        self.clone_map = {}
        engine.list_legal_moves_for = lambda board, player: self.move_map.get(id(board), [])
        engine._make_move_on_clone = lambda board, piece, move: self.clone_map.get(
            (id(board), id(piece), id(move)))
        engine._last_root_exact_evals = []
        engine._last_material_guard_triggered = False
        engine._last_material_guard_loss = 0
        engine._last_material_guard_replacement = False
        engine._last_promotion_guard_triggered = False
        engine._last_promotion_guard_replacement = False

    def tearDown(self):
        engine.list_legal_moves_for = self.old_moves
        engine._make_move_on_clone = self.old_clone
        engine._tactical_guard_status = self.old_status

    def wire_exchange(self, attacker_name="Bishop", reply_name="King",
                      reply_captures=(), enemy_reply_captures=()):
        own_major = Piece("Right", "white", 3, 2)
        attacker = Piece(attacker_name, "black", 1, 4)
        our_king = Piece("King", "white", 0, 4)
        enemy_king = Piece("King", "black", 0, 0)
        child = Board("black", [own_major, attacker, our_king, enemy_king])
        enemy_capture = Move(3, 2, captures=[Pos(3, 2)])
        after_capture = Board("white", [attacker, our_king, enemy_king])
        reply_piece = (Piece(reply_name, "white", 0, 4)
                       if reply_name != "King" else our_king)
        reply_move = Move(1, 4, captures=[Pos(1, 4)] if reply_captures else [])
        if reply_captures:
            # The reply captures the enemy attacker at (1,4).
            reply_move.captures = {Pos(1, 4)}
        reply_after = Board("black", [reply_piece, enemy_king])
        enemy_reply_piece = enemy_king
        enemy_reply = Move(0, 1, captures=enemy_reply_captures)
        self.move_map[id(child)] = [(attacker, enemy_capture)]
        self.move_map[id(after_capture)] = [(reply_piece, reply_move)]
        self.move_map[id(reply_after)] = [(enemy_reply_piece, enemy_reply)]
        self.clone_map[(id(child), id(attacker), id(enemy_capture))] = after_capture
        self.clone_map[(id(after_capture), id(reply_piece), id(reply_move))] = reply_after
        return child, attacker, enemy_capture, after_capture, reply_piece, reply_move, reply_after

    def test_search_defaults_remain_deterministic_and_bounded(self):
        self.assertFalse(engine._ENABLE_ROOT_PUCT)
        self.assertFalse(engine._ENABLE_CHECK_EXTENSION)
        self.assertFalse(engine._ENABLE_ROOT_RANDOM_TIEBREAK)
        self.assertEqual(engine._MATERIAL_GUARD_MAX_SCORE_LOSS_CP, 150)
        self.assertEqual(engine._MATERIAL_GUARD_MAX_ALTERNATIVES, 4)

    def test_evaluator_is_unchanged_from_frozen_v73(self):
        if not V73_PATH.exists():
            self.skipTest("frozen v7.3 source is not beside this test")

        def body(path):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            node = next(n for n in tree.body
                        if isinstance(n, ast.FunctionDef) and n.name == "evaluate_for_white")
            body_nodes = list(node.body)
            if (body_nodes and isinstance(body_nodes[0], ast.Expr)
                    and isinstance(body_nodes[0].value, ast.Constant)
                    and isinstance(body_nodes[0].value.value, str)):
                body_nodes = body_nodes[1:]
            return ast.dump(ast.Module(body=body_nodes, type_ignores=[]),
                            include_attributes=False)

        self.assertEqual(body(V73_PATH), body(ROOT / "agent_v74_tactical_guard.py"))

    def test_unrecapturable_right_loss_is_detected(self):
        child, *_ = self.wire_exchange()
        unsafe, loss = engine._opponent_has_unrecapturable_major_capture(
            child, "white", 10**9)
        self.assertTrue(unsafe)
        self.assertEqual(loss, 700)

    def test_recapturing_attacking_queen_offsets_right_loss(self):
        child, *_ = self.wire_exchange(attacker_name="Queen", reply_captures=True)
        unsafe, loss = engine._opponent_has_unrecapturable_major_capture(
            child, "white", 10**9)
        self.assertFalse(unsafe)
        self.assertEqual(loss, 0)

    def test_recapturing_bishop_does_not_make_right_loss_harmless(self):
        child, *_ = self.wire_exchange(attacker_name="Bishop", reply_captures=True)
        unsafe, loss = engine._opponent_has_unrecapturable_major_capture(
            child, "white", 10**9)
        self.assertTrue(unsafe)
        self.assertEqual(loss, 370)

    def test_exposed_recapturing_queen_is_charged_back(self):
        child, attacker, enemy_capture, after_capture, *_ = self.wire_exchange(
            attacker_name="Bishop", reply_name="Queen", reply_captures=True,
            enemy_reply_captures=[Pos(1, 4)])
        # The opponent's reply captures the queen that took the bishop.
        unsafe, loss = engine._opponent_has_unrecapturable_major_capture(
            child, "white", 10**9)
        self.assertTrue(unsafe)
        self.assertGreaterEqual(loss, 280)

    def test_unanswerable_immediate_promotion_is_detected(self):
        white_pawn = Piece("Pawn_Q", "white", 4, 1)
        black_king = Piece("King", "black", 0, 4)
        child = Board("white", [white_pawn, black_king])
        promotion = Move(4, 0)
        promoted_queen = Piece("Queen", "white", 4, 0)
        promoted_board = Board("black", [promoted_queen, black_king])
        self.move_map[id(child)] = [(white_pawn, promotion)]
        self.move_map[id(promoted_board)] = [(black_king, Move(0, 3))]
        self.clone_map[(id(child), id(white_pawn), id(promotion))] = promoted_board
        self.assertTrue(engine._opponent_has_immediate_promotion(
            child, "black", 10**9))

    def test_immediate_promotion_that_can_be_captured_is_not_emergency(self):
        white_pawn = Piece("Pawn_Q", "white", 4, 1)
        black_right = Piece("Right", "black", 3, 2)
        child = Board("white", [white_pawn, black_right])
        promotion = Move(4, 0)
        promoted_queen = Piece("Queen", "white", 4, 0)
        promoted_board = Board("black", [promoted_queen, black_right])
        capture_queen = Move(4, 0, captures=[Pos(4, 0)])
        self.move_map[id(child)] = [(white_pawn, promotion)]
        self.move_map[id(promoted_board)] = [(black_right, capture_queen)]
        self.clone_map[(id(child), id(white_pawn), id(promotion))] = promoted_board
        self.assertFalse(engine._opponent_has_immediate_promotion(
            child, "black", 10**9))

    def test_pawn_move_not_to_last_rank_is_not_immediate_promotion(self):
        white_pawn = Piece("Pawn_Q", "white", 4, 2)
        child = Board("white", [white_pawn])
        self.move_map[id(child)] = [(white_pawn, Move(4, 1))]
        self.assertFalse(engine._opponent_has_immediate_promotion(
            child, "black", 10**9))

    def test_guard_switches_to_safe_exact_alternative_within_150cp(self):
        selected_piece, selected_move = Piece("Right", "black"), Move(3, 2)
        alt_piece, alt_move = Piece("King", "black"), Move(1, 0)
        board = object()
        unsafe_child, safe_child = object(), object()
        old_clone = engine._make_move_on_clone
        old_status = engine._tactical_guard_status
        try:
            engine._make_move_on_clone = lambda b, p, m: (
                unsafe_child if m is selected_move else safe_child)
            engine._tactical_guard_status = lambda child, side, deadline: (
                (700, False) if child is unsafe_child else (0, False))
            engine._last_root_exact_evals = [
                (100, selected_piece, selected_move),
                (40, alt_piece, alt_move),
            ]
            chosen = engine._material_blunder_guard(
                board, Player("black"), selected_piece, selected_move, 10**9)
            self.assertIs(chosen[0], alt_piece)
            self.assertIs(chosen[1], alt_move)
            self.assertTrue(engine._last_material_guard_replacement)
        finally:
            engine._make_move_on_clone = old_clone
            engine._tactical_guard_status = old_status

    def test_guard_rejects_alternative_more_than_150cp_worse(self):
        selected_piece, selected_move = Piece("Right", "black"), Move(3, 2)
        alt_piece, alt_move = Piece("King", "black"), Move(1, 0)
        board = object()
        unsafe_child, safe_child = object(), object()
        old_clone = engine._make_move_on_clone
        old_status = engine._tactical_guard_status
        try:
            engine._make_move_on_clone = lambda b, p, m: (
                unsafe_child if m is selected_move else safe_child)
            engine._tactical_guard_status = lambda child, side, deadline: (
                (700, False) if child is unsafe_child else (0, False))
            engine._last_root_exact_evals = [
                (100, selected_piece, selected_move),
                (-60, alt_piece, alt_move),
            ]
            chosen = engine._material_blunder_guard(
                board, Player("black"), selected_piece, selected_move, 10**9)
            self.assertIs(chosen[0], selected_piece)
            self.assertIs(chosen[1], selected_move)
            self.assertFalse(engine._last_material_guard_replacement)
        finally:
            engine._make_move_on_clone = old_clone
            engine._tactical_guard_status = old_status

    def test_guard_will_not_use_alternative_when_selected_score_is_not_exact(self):
        selected_piece, selected_move = Piece("Right", "black"), Move(3, 2)
        alt_piece, alt_move = Piece("King", "black"), Move(1, 0)
        board = object()
        old_clone = engine._make_move_on_clone
        old_status = engine._tactical_guard_status
        try:
            engine._make_move_on_clone = lambda b, p, m: object()
            engine._tactical_guard_status = lambda child, side, deadline: (700, False)
            engine._last_root_exact_evals = [(50, alt_piece, alt_move)]
            chosen = engine._material_blunder_guard(
                board, Player("black"), selected_piece, selected_move, 10**9)
            self.assertIs(chosen[0], selected_piece)
            self.assertIs(chosen[1], selected_move)
        finally:
            engine._make_move_on_clone = old_clone
            engine._tactical_guard_status = old_status


if __name__ == "__main__":
    unittest.main(verbosity=2)
