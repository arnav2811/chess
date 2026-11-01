import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Fast, framework-independent test of v7.5's actual retrograde probe path."""
from types import SimpleNamespace
import endgame_tablebase as tb
import agent_v75_endgame_depth as agent

assert tb.is_tablebase_loaded(), "65-configuration tablebase did not load"
assert len(tb._ENDGAME_TB) == 65, f"Expected 65 configurations, got {len(tb._ENDGAME_TB)}"
assert agent._TABLEBASE_READY, "Agent did not detect the loaded tablebase"

# Pick a real decisive K+Q table entry, then pass a minimal board object through
# the same helper used by _negamax and _quiescence.
key = ((2, 0),)  # one White Queen, according to the generated type map
entries = tb._ENDGAME_TB[key]
found = None
for wk in range(25):
    for bk in range(25):
        if bk == wk:
            continue
        for qsq in range(25):
            if qsq in (wk, bk):
                continue
            idx = wk * 1250 + bk * 50 + qsq * 2  # White to move
            if idx < len(entries) and entries[idx] in (tb._TB_WIN, tb._TB_LOSS):
                found = (wk, bk, qsq, entries[idx])
                break
        if found:
            break
    if found:
        break
assert found is not None, "No decisive K+Q table entry available for test"

wk, bk, qsq, outcome = found
class King: pass
class Queen: pass
white, black = SimpleNamespace(name="white"), SimpleNamespace(name="black")
def make_piece(cls, owner, square):
    p = cls()
    p.player = owner
    p.position = SimpleNamespace(x=square % 5, y=square // 5)
    return p
pieces = [make_piece(King, white, wk), make_piece(King, black, bk), make_piece(Queen, white, qsq)]
board = SimpleNamespace(get_pieces=lambda: pieces, current_player=white)
score = agent._tablebase_score(board, colour=1, ply_from_root=0)
expected = 95000 if outcome == tb._TB_WIN else -95000
assert score == expected, (found, score, expected)
print(f"PASS: {len(tb._ENDGAME_TB)} configurations loaded; decisive K+Q probe returned {score}.")
