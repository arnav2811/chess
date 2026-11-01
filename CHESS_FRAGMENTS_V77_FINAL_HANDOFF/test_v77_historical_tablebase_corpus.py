"""Regression-test exact v7.7 tablebase scores on real states from the 600-game log.

No ChessMaker installation is required: the test uses lightweight board/piece
objects but exercises the production tablebase adapter and agent probe helper.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import endgame_tablebase_v77 as tb
import agent_v77_final as agent

CORPUS = Path(__file__).with_name("V77_historical_tablebase_regression_600run.jsonl")

assert tb.is_tablebase_loaded(), "Embedded tablebase failed to load"
assert len(tb._ENDGAME_TB) == 65, f"Expected 65 material configurations, got {len(tb._ENDGAME_TB)}"
assert agent._TABLEBASE_READY, "Agent does not see the tablebase"
assert CORPUS.exists(), f"Missing historical corpus: {CORPUS}"

CLASSES = {
    "king": type("King", (), {}),
    "queen": type("Queen", (), {}),
    "right": type("Right", (), {}),
    "bishop": type("Bishop", (), {}),
    "knight": type("Knight", (), {}),
    "pawn": type("Pawn_Q", (), {}),  # production _piece_name normalises Pawn_Q
}


def make_board(record):
    white = SimpleNamespace(name="white")
    black = SimpleNamespace(name="black")
    pieces = []
    squares = [[SimpleNamespace(piece=None) for _ in range(5)] for _ in range(5)]
    for item in record["pieces"]:
        piece = CLASSES[item["piece"]]()
        piece.player = white if item["side"] == "white" else black
        piece.position = SimpleNamespace(x=item["x"], y=item["y"])
        squares[item["y"]][item["x"]].piece = piece
        pieces.append(piece)
    stm = white if record["side_to_move"] == "white" else black
    return SimpleNamespace(
        get_pieces=lambda: pieces,
        current_player=stm,
        _squares=squares,
    ), pieces


score_expected = {
    "WIN": lambda ply: 95000 - ply,
    "LOSS": lambda ply: -95000 + ply,
    "DRAW": lambda ply: 0,
}

agent._last_tb_probes = agent._last_tb_hits = 0
agent._last_tb_wins = agent._last_tb_losses = agent._last_tb_draws = 0
counts = {"WIN": 0, "LOSS": 0, "DRAW": 0}
for line_no, line in enumerate(CORPUS.read_text(encoding="utf-8").splitlines(), start=1):
    record = json.loads(line)
    board, pieces = make_board(record)
    expected = record["expected"]
    counts[expected] += 1

    # Adapter must preserve the retrograde result even with extreme contempt
    # values passed by a legacy caller.
    hit_direct, direct = tb.probe_endgame_tb(
        board, agent._piece_name, ply_from_root=7,
        mat_diff=(9000 if record["side_to_move"] == "white" else -9000),
        pieces=pieces,
    )
    assert hit_direct, f"Adapter miss at corpus line {line_no}: {record}"
    assert direct == score_expected[expected](7), (
        f"Adapter score mismatch at line {line_no}: {expected} -> {direct}"
    )

    # Exercise the exact helper called from Negamax and quiescence.
    colour = 1 if record["side_to_move"] == "white" else -1
    actual = agent._tablebase_score(board, colour, 7)
    assert actual == score_expected[expected](7), (
        f"Agent score mismatch at line {line_no}: {expected} -> {actual}"
    )

assert sum(counts.values()) == 555, counts
assert agent._last_tb_hits == 555, agent._last_tb_hits
assert agent._last_tb_wins == 240, agent._last_tb_wins
assert agent._last_tb_losses == 227, agent._last_tb_losses
assert agent._last_tb_draws == 88, agent._last_tb_draws

# Perspective mismatch must fall back instead of inverting an exact WDL score.
first_record = json.loads(CORPUS.read_text(encoding="utf-8").splitlines()[0])
first_board, _ = make_board(first_record)
wrong_colour = -1 if first_record["side_to_move"] == "white" else 1
assert agent._tablebase_score(first_board, wrong_colour, 0) is None

# A standalone K-v-K call is also exact zero.
white = SimpleNamespace(name="white")
black = SimpleNamespace(name="black")
class King: pass
k1, k2 = King(), King()
k1.player, k2.player = white, black
k1.position = SimpleNamespace(x=0, y=0)
k2.position = SimpleNamespace(x=4, y=4)
empty_board = SimpleNamespace(get_pieces=lambda: [k1, k2], current_player=white)
assert tb.probe_endgame_tb(empty_board, agent._piece_name, mat_diff=99999) == (True, 0)

print("PASS: 65 tablebase configurations loaded")
print("PASS: 555 unique historical 3-/4-piece states match exact WDL")
print("PASS: 240 WIN, 227 LOSS, 88 DRAW scores verified")
print("PASS: extreme legacy material contempt cannot alter exact DRAW=0")
print("PASS: agent Negamax/quiescence probe helper records all 555 hits")
