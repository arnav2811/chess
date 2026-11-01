"""Targeted v7.7 regressions for the two observed v7.6 failure patterns.

These tests use controlled board/move stubs for the search-policy decision
logic. They do not replace a live ChessMaker replay of historical Matches 8/9/12.
"""
from types import SimpleNamespace
import time
import agent_v77_final as agent

# 1) A high-material non-king move must no longer bypass the one-reply
# terminal-loss verifier. The selected move is deliberately unsafe, while a
# near-alternative is safe. The prior v7.6 early return would keep the unsafe move.
class Pawn: pass
white = SimpleNamespace(name="white")
black = SimpleNamespace(name="black")
selected_piece = Pawn(); selected_piece.player = black
selected_piece.position = SimpleNamespace(x=0, y=0)
selected_move = SimpleNamespace(position=SimpleNamespace(x=0, y=1), captures=set())
alt_piece = Pawn(); alt_piece.player = black
alt_piece.position = SimpleNamespace(x=1, y=0)
alt_move = SimpleNamespace(position=SimpleNamespace(x=1, y=1), captures=set())

board = SimpleNamespace(get_pieces=lambda: [object() for _ in range(15)])
player = black
legal_moves = [(selected_piece, selected_move), (alt_piece, alt_move)]
orig = {
    "_material_blunder_guard": agent._material_blunder_guard,
    "_make_move_on_clone": agent._make_move_on_clone,
    "_opponent_has_immediate_terminal_win": agent._opponent_has_immediate_terminal_win,
    "_normalised_root_entropy": agent._normalised_root_entropy,
    "_order_moves": agent._order_moves,
    "_last_root_evals": agent._last_root_evals,
}
try:
    agent._material_blunder_guard = lambda b, p, sp, sm, d: (sp, sm)
    agent._make_move_on_clone = lambda b, p, m: SimpleNamespace(tag=("selected" if p is selected_piece else "alternative"))
    calls = []
    def fake_terminal_probe(child, player_name, deadline):
        calls.append(child.tag)
        return child.tag == "selected"
    agent._opponent_has_immediate_terminal_win = fake_terminal_probe
    agent._normalised_root_entropy = lambda _evals: 0.0
    agent._order_moves = lambda moves, *_a, **_k: list(moves)
    agent._last_root_evals = [(100, selected_piece, selected_move), (70, alt_piece, alt_move)]
    agent._last_stalemate_guard_replacements = 0
    result = agent._entropy_guided_anti_loss(
        board, player, selected_piece, selected_move, legal_moves,
        time.perf_counter() + 2.0,
    )
    assert result == (alt_piece, alt_move), result
    assert calls == ["selected", "alternative"], calls
    assert agent._last_stalemate_guard_replacements == 1
    # Exercise the actual one-reply detector: after the opponent's reply,
    # the current side has no legal moves, so the candidate must be rejected.
    child_board = SimpleNamespace(current_player=black)
    enemy_piece = SimpleNamespace()
    enemy_move = SimpleNamespace()
    after_reply = SimpleNamespace(current_player=white)
    original_legal = agent.list_legal_moves_for
    original_terminal = agent._check_terminal
    original_probe = agent._opponent_has_immediate_terminal_win
    try:
        agent._opponent_has_immediate_terminal_win = orig["_opponent_has_immediate_terminal_win"]
        agent._make_move_on_clone = lambda b, p, m: after_reply
        agent.list_legal_moves_for = lambda b, side: ([(enemy_piece, enemy_move)]
                                                       if b is child_board else [])
        agent._check_terminal = lambda b, ply: (False, 0)
        agent._last_stalemate_guard_calls = 0
        agent._last_stalemate_guard_threats = 0
        agent._last_stalemate_guard_inconclusive = 0
        assert agent._opponent_has_immediate_terminal_win(
            child_board, "white", time.perf_counter() + 2.0) is True
        assert agent._last_stalemate_guard_calls == 1
        assert agent._last_stalemate_guard_threats == 1
    finally:
        agent.list_legal_moves_for = original_legal
        agent._check_terminal = original_terminal
        agent._opponent_has_immediate_terminal_win = original_probe
finally:
    agent._material_blunder_guard = orig["_material_blunder_guard"]
    agent._make_move_on_clone = orig["_make_move_on_clone"]
    agent._opponent_has_immediate_terminal_win = orig["_opponent_has_immediate_terminal_win"]
    agent._normalised_root_entropy = orig["_normalised_root_entropy"]
    agent._order_moves = orig["_order_moves"]
    agent._last_root_evals = orig["_last_root_evals"]

# 2) Among exact equal-WDL root children, choose the less-repeated one.
class Queen: pass
moves=[]
for i in range(2):
    p=Queen(); p.player=white; p.position=SimpleNamespace(x=i, y=0)
    m=SimpleNamespace(position=SimpleNamespace(x=i, y=1), captures=set())
    moves.append((p,m))
root=SimpleNamespace(current_player=white)
orig2={name:getattr(agent,name) for name in (
    "_tablebase_score", "_order_moves", "_make_move_on_clone",
    "_check_terminal", "_board_signature", "_position_history")}
try:
    agent._tablebase_score=lambda b,c,p: 0
    agent._order_moves=lambda ms,*a: list(ms)
    agent._make_move_on_clone=lambda b,p,m: SimpleNamespace(
        index=p.position.x, current_player=black)
    agent._check_terminal=lambda child,ply: (False,0)
    agent._board_signature=lambda child: f"child-{child.index}"
    agent._position_history={"child-0": 3, "child-1": 0}
    agent._last_tb_root_solved=False
    agent._last_tb_repeat_avoided=False
    chosen=agent._solve_root_from_tablebase(root,moves,1,time.perf_counter()+2)
    assert chosen == moves[1], chosen
    assert agent._last_tb_root_solved
    assert agent._last_tb_repeat_avoided

    # Repetition history must never overrule a better exact WDL result.
    def tb_with_win(b,c,p):
        if b is root: return 95000
        return -95000 if b.index == 0 else 0
    agent._tablebase_score=tb_with_win
    agent._position_history={"child-0": 99, "child-1": 0}
    agent._last_tb_root_solved=False
    chosen=agent._solve_root_from_tablebase(root,moves,1,time.perf_counter()+2)
    assert chosen == moves[0], chosen
finally:
    for name,value in orig2.items(): setattr(agent,name,value)

print("PASS: high-material non-king move receives terminal-loss verification")
print("PASS: unsafe selected move is replaced by a verified safe alternative")
print("PASS: equal-WDL tablebase moves prefer less-repeated child positions")
print("PASS: repetition tie-break never overrides a superior exact WDL result")
