"""Self-contained structural tests for v7.1; no ChessMaker install required.

These tests validate the PUCT control flow with a tiny fake game tree. They do
NOT validate ChessMaker integration or playing strength; those need the real
coursework runtime and tournament runner.
"""
from __future__ import annotations

import importlib.util
import math
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

AGENT_PATH = Path(__file__).with_name("agent_v71_adaptive_tactical_hybrid.py")


def load_agent():
    extension = types.ModuleType("extension")
    board_utils = types.ModuleType("extension.board_utils")
    board_utils.list_legal_moves_for = lambda board, player: []
    extension.board_utils = board_utils
    sys.modules.setdefault("extension", extension)
    sys.modules["extension.board_utils"] = board_utils
    spec = importlib.util.spec_from_file_location("agent_v71_under_test", AGENT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class Position:
    def __init__(self, x, y):
        self.x, self.y = x, y


class Player:
    def __init__(self, name):
        self.name = name


class Move:
    def __init__(self, x, y, target_state):
        self.position = Position(x, y)
        self.target_state = target_state
        self.captures = set()


class Piece:
    def __init__(self, player, x, y):
        self.player = player
        self.position = Position(x, y)


class FakeBoard:
    def __init__(self, state, side):
        self.state = state
        self.current_player = Player(side)
        self.players = [Player("white"), Player("black")]

    def get_pieces(self):
        return []


class V71Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load_agent()

    def test_softmax_is_normalised_and_stable(self):
        m = self.agent
        result = m._puct_softmax([(1000.0, "a"), (999.0, "b"), (-1000.0, "c")])
        self.assertAlmostEqual(sum(p for p, _ in result), 1.0, places=10)
        self.assertGreater(result[0][0], result[1][0])
        self.assertGreater(result[1][0], result[2][0])

    def test_root_entropy_behaves_as_uncertainty_signal(self):
        m = self.agent
        move_a = (Piece(Player("white"), 0, 0), Move(0, 1, "A"))
        move_b = (Piece(Player("white"), 1, 0), Move(1, 1, "B"))
        sharp = [(0, *move_a), (-1200, *move_b)]
        ambiguous = [(0, *move_a), (-5, *move_b)]
        self.assertLess(m._normalised_root_entropy(sharp),
                        m._normalised_root_entropy(ambiguous))

    def test_puct_returns_one_of_legal_root_moves_and_does_not_mutate_root(self):
        m = self.agent
        root = FakeBoard("root", "white")
        white = Player("white")
        root_moves = [
            (Piece(white, 0, 0), Move(0, 1, "A")),
            (Piece(white, 1, 0), Move(1, 1, "B")),
            (Piece(white, 2, 0), Move(2, 1, "C")),
        ]
        black_moves = {
            "A": [(Piece(Player("black"), 0, 4), Move(0, 3, "A1")),
                  (Piece(Player("black"), 1, 4), Move(1, 3, "A2"))],
            "B": [(Piece(Player("black"), 0, 4), Move(0, 3, "B1")),
                  (Piece(Player("black"), 1, 4), Move(1, 3, "B2"))],
            "C": [(Piece(Player("black"), 0, 4), Move(0, 3, "C1")),
                  (Piece(Player("black"), 1, 4), Move(1, 3, "C2"))],
        }
        # Continue the tree to depth three; leaves still have a legal move so
        # the leaf evaluator is exercised rather than the no-legal-move rule.
        transitions = dict(black_moves)
        for state in ("A1", "A2", "B1", "B2", "C1", "C2"):
            transitions[state] = [
                (Piece(Player("white"), 2, 2), Move(2, 3, state + "L"))
            ]
        for state in list(transitions):
            for _, mv in transitions[state]:
                transitions[mv.target_state] = [
                    (Piece(Player("black"), 4, 4), Move(4, 3, mv.target_state + "X"))
                ]

        def legal(board, player):
            if board.state == "root":
                return root_moves
            return transitions.get(board.state, [])

        def apply(board, piece, move):
            side = "black" if board.current_player.name == "white" else "white"
            return FakeBoard(move.target_state, side)

        def terminal(board, ply):
            return False, 0

        values = {"A1L": 150, "A2L": -60, "B1L": 110, "B2L": 80,
                  "C1L": 90, "C2L": 70}

        def eval_white(board):
            # At depth three, state has suffix L. Use a small preference signal.
            return values.get(board.state, 0)

        # Ensure all candidate scores are close enough to activate the probe.
        m._last_root_evals = [
            (0, *root_moves[0]), (-20, *root_moves[1]), (-40, *root_moves[2])
        ]
        original_state = root.state
        with patch.object(m, "list_legal_moves_for", side_effect=legal), \
             patch.object(m, "_make_move_on_clone", side_effect=apply), \
             patch.object(m, "_check_terminal", side_effect=terminal), \
             patch.object(m, "evaluate_for_white", side_effect=eval_white), \
             patch.object(m, "_move_might_give_check", return_value=False), \
             patch.object(m, "_PUCT_MAX_SIMULATIONS", 12), \
             patch.object(m, "_PUCT_MAX_DEPTH", 3):
            chosen_piece, chosen_move = m._puct_refine_root(
                root, white, root_moves[0][0], root_moves[0][1],
                deadline=__import__("time").perf_counter() + 2.0, budget_s=0.15)

        self.assertIn((m._move_key(chosen_piece, chosen_move)),
                      {m._move_key(p, mv) for p, mv in root_moves})
        self.assertEqual(root.state, original_state)
        self.assertGreater(m._last_puct_stats["simulations"], 0)
        self.assertLessEqual(m._last_puct_stats["elapsed_s"], 0.25)


    def test_policy_prior_changes_risk_appetite_by_score_state(self):
        m = self.agent
        attacker = Piece(Player("white"), 0, 0)
        move = Move(1, 1, "after_capture")
        move.captures = {Position(1, 1)}
        victim = Piece(Player("black"), 1, 1)

        class Square:
            def __init__(self, piece):
                self.piece = piece

        class CaptureBoard(FakeBoard):
            def __getitem__(self, position):
                return Square(victim)

        board = CaptureBoard("root", "white")
        with patch.object(m, "_piece_name", side_effect=lambda p: "right" if p is attacker else "pawn"), \
             patch.object(m, "_move_might_give_check", return_value=False):
            convert = m._puct_move_logit(board, attacker, move,
                                         root_score=250, best_root_score=250,
                                         policy_mode="convert")
            complicate = m._puct_move_logit(board, attacker, move,
                                            root_score=-300, best_root_score=-300,
                                            policy_mode="complicate")
        self.assertGreater(complicate, convert)

    def test_no_legal_move_leaf_is_a_loss(self):
        m = self.agent
        board = FakeBoard("terminal", "black")
        with patch.object(m, "_check_terminal", return_value=(False, 0)), \
             patch.object(m, "list_legal_moves_for", return_value=[]):
            self.assertEqual(m._puct_static_value(board), -1.0)

    def test_puct_skips_decisive_root(self):
        m = self.agent
        root = FakeBoard("root", "white")
        white = Player("white")
        a = (Piece(white, 0, 0), Move(0, 1, "A"))
        b = (Piece(white, 1, 0), Move(1, 1, "B"))
        m._last_root_evals = [(95000, *a), (100, *b)]
        chosen = m._puct_refine_root(root, white, *a, deadline=10**20, budget_s=0.1)
        self.assertEqual(chosen, a)
        self.assertFalse(m._last_puct_stats["used"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
