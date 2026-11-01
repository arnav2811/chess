import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
"""Framework-independent regression tests for the final v7.6 candidate."""
import time
from types import SimpleNamespace
import agent_v76_exact_tablebase as agent

# History remains aged and bounded across the same game.
agent._history = {
    ("white", "queen", 0, 0, 1, 1): 1000,
    ("black", "right", 4, 4, 3, 3): 10,
}
agent._age_history(decay=0.78, floor=12, max_entries=5000)
assert agent._history[("white", "queen", 0, 0, 1, 1)] == 780
assert ("black", "right", 4, 4, 3, 3) not in agent._history

# v7.4's conservative 2-ply LMR trigger is restored; forcing moves stay full depth.
class Queen: pass
piece = Queen()
piece.player = SimpleNamespace(name="white")
piece.position = SimpleNamespace(x=0, y=0)
move = SimpleNamespace(position=SimpleNamespace(x=1, y=1), captures=set())
agent._history = {}
agent._killer_moves = {}
assert agent._lmr_reduction(8, 10, piece, move, False, False, 2) == 1
assert agent._lmr_reduction(8, 11, piece, move, False, False, 2) == 2
assert agent._lmr_reduction(8, 11, piece, move, True, False, 2) == 0
assert agent._lmr_reduction(8, 11, piece, move, False, True, 2) == 0
agent._history[agent._heuristic_move_key(piece, move)] = 300
assert agent._lmr_reduction(8, 11, piece, move, False, False, 2) == 0

# Frontier futility is restricted to crowded positions, avoiding low-mobility
# stalemate nets where a quiet move may be an immediate win.
assert agent._frontier_futility_allowed(1, False, -100, 8)
assert not agent._frontier_futility_allowed(1, False, -100, 5)
assert not agent._frontier_futility_allowed(1, True, -100, 8)
assert not agent._frontier_futility_allowed(2, False, -100, 8)
assert not agent._frontier_futility_allowed(1, False, 95000, 8)

# Transposition key is order-independent and side-to-move sensitive.
class King: pass
class Pawn: pass
white, black = SimpleNamespace(name="white"), SimpleNamespace(name="black")
def make_piece(cls, owner, x, y):
    p=cls(); p.player=owner; p.position=SimpleNamespace(x=x,y=y); return p
pieces=[make_piece(King,white,0,0),make_piece(King,black,4,4),make_piece(Pawn,white,1,2)]
board=SimpleNamespace(get_pieces=lambda: pieces,current_player=white)
h1=agent._hash_board(board)
board.get_pieces=lambda: list(reversed(pieces))
assert agent._hash_board(board)==h1
board.current_player=black
assert agent._hash_board(board)!=h1

# Direct root tablebase selector chooses the WDL-best child and refuses partial
# information. Use monkeypatched children so the test does not require ChessMaker.
root_moves=[]
for i in range(3):
    p=Queen();p.player=white;p.position=SimpleNamespace(x=i,y=0)
    m=SimpleNamespace(position=SimpleNamespace(x=i,y=1),captures=set())
    root_moves.append((p,m))
root=SimpleNamespace(current_player=white)
children=[]
orig={name:getattr(agent,name) for name in (
    "_tablebase_score","_order_moves","_make_move_on_clone","_check_terminal")}
try:
    def fake_child(_board,piece,_move):
        child=SimpleNamespace(index=piece.position.x,current_player=black)
        children.append(child); return child
    def fake_tb(board,_colour,_ply):
        if board is root: return 95000
        return {0:-95000,1:0,2:95000}[board.index]
    agent._tablebase_score=fake_tb
    agent._order_moves=lambda moves,*args: list(moves)
    agent._make_move_on_clone=fake_child
    agent._check_terminal=lambda child,_ply: (False,0)
    agent._last_tb_root_solved=False
    chosen=agent._solve_root_from_tablebase(root,root_moves,1,time.perf_counter()+2)
    assert chosen==root_moves[0], chosen  # child 0 is LOSS for Black: WIN for White
    assert agent._last_tb_root_solved

    agent._last_tb_root_solved=False
    def unsupported_tb(board,_colour,_ply):
        if board is root:return 0
        return None if board.index==2 else {0:-95000,1:0}[board.index]
    agent._tablebase_score=unsupported_tb
    assert agent._solve_root_from_tablebase(root,root_moves,1,time.perf_counter()+2) is None
    assert not agent._last_tb_root_solved
finally:
    for name,value in orig.items():setattr(agent,name,value)

# Expired root deadline must still return a legal fallback.
black = SimpleNamespace(name="black")
board=SimpleNamespace(players=[white,black])
move2=SimpleNamespace(position=SimpleNamespace(x=2,y=2),captures=set())
piece2=Queen();piece2.player=white;piece2.position=SimpleNamespace(x=2,y=3)
root_moves2=[(piece,move),(piece2,move2)]
retained_key=("white","queen",0,0,1,1)
agent._history={retained_key:780}
original=agent.list_legal_moves_for
try:
    agent.list_legal_moves_for=lambda _b,_p:root_moves2
    selected=agent._iterative_deepening(board,"white",time.perf_counter()-1.0)
    assert selected==root_moves2[0], selected
finally:
    agent.list_legal_moves_for=original
assert agent._history.get(retained_key)==780

print("PASS: history ageing; conservative LMR; low-mobility futility guard")
print("PASS: order-independent TT hash; exact root TB selection/fallback")
print("PASS: expired-root legal fallback")
