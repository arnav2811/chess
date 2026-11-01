"""
endgame_tablebase.py — O(1) Perfect Endgame Solver for 5×5 Chess Fragments
===========================================================================
COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces.

Wraps the pre-computed retrograde data for supported positions with 3–4 pieces.
The embedded data contains 65 material-configuration keys; it does not claim
coverage of every theoretically possible <=4-piece material combination.

Returns exact theoretical outcomes from the side-to-move perspective:
  - WIN:  +95,000 - ply_from_root
  - LOSS: -95,000 + ply_from_root
  - DRAW: exactly 0 (the retrograde result is never altered by heuristic contempt)
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


def probe_endgame_tb(board, _pn_func, ply_from_root=0, mat_diff=0, pieces=None):
    """Probe the exact 5x5 retrograde WDL table.

    Returns (hit, score_for_side_to_move). The embedded table is the authority:
    WIN -> +95000-ply, LOSS -> -95000+ply, DRAW -> exactly 0.

    ``mat_diff`` remains in the signature for compatibility with earlier
    callers, but it deliberately does not alter a solved WDL result. A draw
    contempt gradient can contradict the retrograde result and break negamax
    symmetry, so anti-draw preferences belong outside this exact solver.

    ``pieces`` allows the search engine to pass a pre-fetched piece list and
    avoid a second board scan/allocation.
    """
    if not TABLEBASE_AVAILABLE:
        return False, 0

    if pieces is None:
        try:
            pieces = list(board.get_pieces())
        except Exception:
            return False, 0
    else:
        pieces = list(pieces)

    n = len(pieces)
    if n < 2 or n > 4:
        return False, 0
    if n == 2:
        if all(_pn_func(piece) == "king" for piece in pieces):
            return True, 0
        return False, 0

    wk = bk = -1
    extra = []
    for p in pieces:
        nm = _pn_func(p)
        sq = p.position.y * 5 + p.position.x
        if nm == "king":
            if p.player.name == "white":
                if wk >= 0:
                    return False, 0
                wk = sq
            else:
                if bk >= 0:
                    return False, 0
                bk = sq
        else:
            pt = _TB_TYPE_MAP.get(nm)
            if pt is None:
                return False, 0
            pc = 0 if p.player.name == "white" else 1
            extra.append((pt, pc, sq))

    if wk < 0 or bk < 0 or len(extra) not in (1, 2):
        return False, 0

    extra.sort()
    material_key = tuple((t, c) for t, c, _ in extra)
    table = _ENDGAME_TB.get(material_key)
    if table is None:
        return False, 0

    stm = 0 if board.current_player.name == "white" else 1
    if len(extra) == 1:
        idx = wk * 1250 + bk * 50 + extra[0][2] * 2 + stm
    else:
        idx = (wk * 31250 + bk * 1250 + extra[0][2] * 50
               + extra[1][2] * 2 + stm)

    if idx < 0 or idx >= len(table):
        return False, 0

    result = table[idx]
    if result == _TB_WIN:
        return True, 95000 - int(ply_from_root)
    if result == _TB_LOSS:
        return True, -95000 + int(ply_from_root)
    if result == _TB_DRAW:
        return True, 0
    return False, 0
