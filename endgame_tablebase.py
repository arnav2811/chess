"""
endgame_tablebase.py — O(1) Perfect Endgame Solver for 5×5 Chess Fragments
===========================================================================
COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces.

Wraps pre-computed retrograde tablebase for all positions with <= 4 pieces
(65 material configurations, covering K+Q, K+Right, K+Bishop, K+Knight, K+Pawn
and all 4-piece combinations).

Returns exact theoretical outcomes:
  - WIN:  +95,000 - ply_from_root (prefers faster mates)
  - LOSS: -95,000 + ply_from_root (delays loss longest)
  - DRAW: Asymmetric contempt-adjusted:
          * If side to move has material advantage (>40 cp): -2,500 cp
            (avoids settling for draws when winning)
          * If side to move is equal (-40 to 40 cp): -500 cp
          * If side to move is behind (<-40 cp): +1,500 cp
            (actively seeks draw when losing)
"""

import sys

try:
    from endgame_tb_snippet import _ENDGAME_TB, _TB_WIN, _TB_LOSS, _TB_DRAW, _TB_TYPE_MAP
    TABLEBASE_AVAILABLE = True
except Exception as e:
    _ENDGAME_TB = {}
    _TB_WIN = 1; _TB_LOSS = 2; _TB_DRAW = 3
    _TB_TYPE_MAP = {"queen": 2, "right": 3, "knight": 4, "bishop": 5, "pawn": 6}
    TABLEBASE_AVAILABLE = False


def is_tablebase_loaded():
    """Returns True if the 65-configuration tablebase is loaded in memory."""
    return TABLEBASE_AVAILABLE and len(_ENDGAME_TB) > 0


def probe_endgame_tb(board, _pn_func, ply_from_root=0, mat_diff=0):
    """
    Probe the 5×5 endgame tablebase for the current board state.

    Parameters
    ----------
    board : Board
        The current game board.
    _pn_func : callable
        Function returning lowercase piece name (e.g. 'queen', 'king').
    ply_from_root : int
        Distance from search root (used for mate-distance scoring).
    mat_diff : int
        Material difference for the side to move (positive = we are ahead).

    Returns
    -------
    tuple[bool, int]
        (hit, score_for_side_to_move)
    """
    if not TABLEBASE_AVAILABLE:
        return False, 0

    # Count total pieces on board — fast cutoff if > 4 pieces
    pcs = []
    for p in board.get_pieces():
        pcs.append(p)
        if len(pcs) > 4:
            return False, 0

    n = len(pcs)
    if n < 2:
        return False, 0
    if n == 2:
        # King vs King is an automatic draw
        if mat_diff > 40:
            return True, -80
        elif mat_diff < -40:
            return True, 80
        return True, -30

    wk = bk = -1
    extra = []
    for p in pcs:
        nm = _pn_func(p)
        sq = p.position.y * 5 + p.position.x
        if nm == "king":
            if p.player.name == "white":
                wk = sq
            else:
                bk = sq
        else:
            pt = _TB_TYPE_MAP.get(nm, 0)
            pc = 0 if p.player.name == "white" else 1
            extra.append((pt, pc, sq))

    if wk < 0 or bk < 0:
        return False, 0

    extra.sort()
    mk = tuple((t, c) for t, c, s in extra)
    if mk not in _ENDGAME_TB:
        return False, 0

    tbl = _ENDGAME_TB[mk]
    stm = 0 if board.current_player.name == "white" else 1
    ne = len(extra)

    if ne == 1:
        idx = wk * 1250 + bk * 50 + extra[0][2] * 2 + stm
    elif ne == 2:
        idx = wk * 31250 + bk * 1250 + extra[0][2] * 50 + extra[1][2] * 2 + stm
    else:
        return False, 0

    if idx >= len(tbl):
        return False, 0

    r = tbl[idx]
    if r == _TB_WIN:
        return True, 95000 - ply_from_root
    if r == _TB_LOSS:
        return True, -95000 + ply_from_root
    if r == _TB_DRAW:
        # Under 5x5 coursework rules, stalemate is a LOSS for the immobilized player.
        # A position that is a theoretical draw in 8x8 is frequently a forced win
        # on 5x5 by suffocating the enemy King.
        # When ahead or equal, heavily punish settling for a draw (-2500 cp) and add
        # progressive King-cornering bonuses so the search drives the enemy King into stalemate.
        if mat_diff > 40:
            score = -2500
        elif mat_diff < -40:
            score = 1500
        else:
            score = -800

        # Anti-stalemate constriction gradient in 5x5 endgames:
        opp_col = "black" if board.current_player.name == "white" else "white"
        opp_k = bk if opp_col == "black" else wk
        if opp_k >= 0:
            okx, oky = opp_k % 5, opp_k // 5
            escapes = 0
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    nx, ny = okx + dx, oky + dy
                    if 0 <= nx < 5 and 0 <= ny < 5:
                        sq_p = board._squares[ny][nx].piece
                        if sq_p is None or sq_p.player.name != opp_col:
                            escapes += 1
            if mat_diff >= 0:
                score += (4 - escapes) * 60
                if escapes <= 1:
                    score += 400
        return True, score

    return False, 0
