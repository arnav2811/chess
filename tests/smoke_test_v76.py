import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Smoke-test v7.6 import, tablebase loading, and one legal agent decision."""
from itertools import cycle
from chessmaker.chess.base import Player, Board, Square
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right import Right
from extension.piece_pawn import Pawn_Q
from agent_v76_exact_tablebase import agent, _TABLEBASE_READY, _move_stats_log

white, black = Player("white"), Player("black")
squares = [
    [Square(Knight(black)), Square(Queen(black)), Square(King(black)), Square(Bishop(black)), Square(Right(black))],
    [Square(Pawn_Q(black)) for _ in range(5)],
    [Square() for _ in range(5)],
    [Square(Pawn_Q(white)) for _ in range(5)],
    [Square(Right(white)), Square(Bishop(white)), Square(King(white)), Square(Queen(white)), Square(Knight(white))],
]
board = Board(squares=squares, players=[white, black], turn_iterator=cycle([white, black]))
move = agent(board, white, [1, 12.0])
assert isinstance(move, tuple) and len(move) == 2 and all(x is not None for x in move), move
assert _move_stats_log, "No instrumentation record emitted"
record = _move_stats_log[-1]
assert record["tablebase_ready"] == _TABLEBASE_READY
print({"tablebase_ready": _TABLEBASE_READY, "move": (type(move[0]).__name__, move[0].position.x, move[0].position.y, move[1].position.x, move[1].position.y), "depth": record["depth"], "nodes": record["nodes"], "time_s": record["time_s"], "tb_probes": record["tablebase_probes"], "tb_hits": record["tablebase_hits"]})
