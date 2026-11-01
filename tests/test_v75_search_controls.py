import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Framework-independent regressions for v7.5 deadline/history/LMR controls."""
import time
from types import SimpleNamespace
import agent_v75_endgame_depth as agent

# 1) History survives between searches but is explicitly decayed and bounded.
agent._history = {("white", "queen", 0, 0, 1, 1): 1000,
                  ("black", "right", 4, 4, 3, 3): 10}
agent._age_history(decay=0.78, floor=12, max_entries=5000)
assert agent._history[("white", "queen", 0, 0, 1, 1)] == 780
assert ("black", "right", 4, 4, 3, 3) not in agent._history

# 2) New 2-ply LMR threshold is active but tactical moves remain unreduced.
class Queen:
    pass
piece = Queen()
piece.player = SimpleNamespace(name="white")
piece.position = SimpleNamespace(x=0, y=0)
move = SimpleNamespace(position=SimpleNamespace(x=1, y=1), captures=set())
agent._history = {}
agent._killer_moves = {}
assert agent._lmr_reduction(8, 10, piece, move, False, False, 2) == 2
assert agent._lmr_reduction(8, 10, piece, move, True, False, 2) == 0

# 3) Expired root budget returns the legal fallback without entering the tree.
white = SimpleNamespace(name="white")
black = SimpleNamespace(name="black")
board = SimpleNamespace(players=[white, black])
move2 = SimpleNamespace(position=SimpleNamespace(x=2, y=2), captures=set())
piece2 = Queen()
piece2.player = white
piece2.position = SimpleNamespace(x=2, y=3)
root_moves = [(piece, move), (piece2, move2)]
retained_key = ("white", "queen", 0, 0, 1, 1)
agent._history = {retained_key: 780}
original = agent.list_legal_moves_for
try:
    agent.list_legal_moves_for = lambda _board, _player: root_moves
    selected = agent._iterative_deepening(board, "white", time.perf_counter() - 1.0)
    assert selected == root_moves[0], selected
finally:
    agent.list_legal_moves_for = original
assert agent._history.get(retained_key) == 780, "History was unexpectedly wiped between searches"

print("PASS: history persistence/aging, bounded LMR schedule, and root deadline fallback")
