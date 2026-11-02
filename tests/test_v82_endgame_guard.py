"""Focused regression checks for the v8.2 endgame safety candidate."""

import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import agent_v82_candidate as agent

assert agent._piece_count(
    SimpleNamespace(get_pieces=lambda: (item for item in (1, 2, 3)))
) == 3


class Node:
    def __init__(self, name, side, moves=()):
        self.name = name
        self.current_player = SimpleNamespace(name=side)
        self.moves = list(moves)
        self._pieces = []

    def get_pieces(self):
        return self._pieces


def edge(source_side, child):
    piece = SimpleNamespace(
        player=SimpleNamespace(name=source_side),
        position=SimpleNamespace(x=0, y=0),
    )
    move = SimpleNamespace(
        position=SimpleNamespace(x=1, y=1),
        captures=set(),
        child=child,
    )
    return piece, move


def run_guard(root):
    original_legal = agent.list_legal_moves_for
    original_clone = agent._make_move_on_clone
    original_terminal = agent._check_terminal
    try:
        agent.list_legal_moves_for = lambda board, _player: board.moves
        agent._make_move_on_clone = lambda _board, _piece, move: move.child
        agent._check_terminal = lambda _board, _ply: (False, 0)
        return agent._opponent_can_force_stalemate_in_two_replies(
            root, "white", time.perf_counter() + 1.0
        )
    finally:
        agent.list_legal_moves_for = original_legal
        agent._make_move_on_clone = original_clone
        agent._check_terminal = original_terminal


def make_position(white_has_escape):
    final_a = Node("final-a", "white")
    final_b = Node("final-b", "white", [edge("white", Node("escape", "black"))]
                   if white_has_escape else [])
    after_our_a = Node("after-our-a", "black", [edge("black", final_a)])
    after_our_b = Node("after-our-b", "black", [edge("black", final_b)])
    after_enemy = Node(
        "after-enemy",
        "white",
        [edge("white", after_our_a), edge("white", after_our_b)],
    )
    return Node("after-our-move", "black", [edge("black", after_enemy)])


assert run_guard(make_position(False)) is True
assert run_guard(make_position(True)) is False
assert agent._opponent_can_force_stalemate_in_two_replies(
    make_position(False), "white", time.perf_counter() - 1.0
) is None


def test_tb_draw_path_invokes_deep_guard():
    player = SimpleNamespace(name="white")
    selected_piece = SimpleNamespace(
        player=player, position=SimpleNamespace(x=0, y=0)
    )
    selected_move = SimpleNamespace(
        position=SimpleNamespace(x=1, y=1), captures=set()
    )
    alternate_piece = SimpleNamespace(
        player=player, position=SimpleNamespace(x=0, y=1)
    )
    alternate_move = SimpleNamespace(
        position=SimpleNamespace(x=1, y=2), captures=set()
    )
    board = SimpleNamespace()
    child = SimpleNamespace()
    original = {
        "material": agent._material_blunder_guard,
        "piece_count": agent._piece_count,
        "tb_solved": agent._last_tb_root_solved,
        "tb_score": agent._tablebase_score,
        "clone": agent._make_move_on_clone,
        "terminal": agent._opponent_has_immediate_terminal_win,
        "stalemate": agent._we_are_immediately_stalemated,
        "deep": agent._opponent_can_force_stalemate_in_two_replies,
        "order": agent._order_moves,
        "entropy": agent._normalised_root_entropy,
        "root_evals": agent._last_root_evals,
    }
    deep_calls = []
    try:
        agent._material_blunder_guard = lambda *_args: (selected_piece, selected_move)
        agent._piece_count = lambda _board: 4
        agent._last_tb_root_solved = True
        agent._tablebase_score = lambda *_args: 0
        agent._make_move_on_clone = lambda *_args: child
        agent._opponent_has_immediate_terminal_win = lambda *_args: False
        agent._we_are_immediately_stalemated = lambda *_args: False

        def deep_guard(*_args):
            deep_calls.append(True)
            return len(deep_calls) == 1

        agent._opponent_can_force_stalemate_in_two_replies = deep_guard
        agent._order_moves = lambda moves, *_args: moves
        agent._normalised_root_entropy = lambda *_args: 0.0
        agent._last_root_evals = []
        result = agent._entropy_guided_anti_loss(
            board,
            player,
            selected_piece,
            selected_move,
            [(selected_piece, selected_move), (alternate_piece, alternate_move)],
            time.perf_counter() + 1.0,
        )
        assert result == (alternate_piece, alternate_move)
        assert len(deep_calls) == 2
    finally:
        agent._material_blunder_guard = original["material"]
        agent._piece_count = original["piece_count"]
        agent._last_tb_root_solved = original["tb_solved"]
        agent._tablebase_score = original["tb_score"]
        agent._make_move_on_clone = original["clone"]
        agent._opponent_has_immediate_terminal_win = original["terminal"]
        agent._we_are_immediately_stalemated = original["stalemate"]
        agent._opponent_can_force_stalemate_in_two_replies = original["deep"]
        agent._order_moves = original["order"]
        agent._normalised_root_entropy = original["entropy"]
        agent._last_root_evals = original["root_evals"]

print("PASS: v8.2 two-reply endgame stalemate guard forcing semantics")
