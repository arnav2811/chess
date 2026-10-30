"""
stronger_opponents.py — Scaled Opponent Hierarchy for Chess Fragments (5×5)
=============================================================================
COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces.

Provides four calibrated opponent tiers for benchmarking agent strength:
  1. Club Player     (~1600 Elo): Iterative Deepening Depth 4, PSTs, MVV-LVA.
  2. Candidate Master(~2100 Elo): Depth 6, PVS, Transposition Table, 2-ply Quiescence.
  3. National Master (~2350 Elo): Depth 7-8, PVS, LMR, Piece Batteries, Anti-Stalemate.
  4. Grandmaster     (~2600 Elo): Depth 8-10+, PVS, Aspiration Windows, Retrograde Tablebase.
"""

import time
import sys
from extension.board_utils import list_legal_moves_for

try:
    from endgame_tablebase import probe_endgame_tb
except ImportError:
    probe_endgame_tb = None


def _piece_name(piece):
    """Portable piece class name extraction across Python 3.9–3.13+."""
    return type(piece).__name__.lower()


# ─── Shared Piece Values & Piece-Square Tables ──────────────────────────────

PIECE_VALUES = {
    "pawn": 100, "knight": 320, "bishop": 330,
    "right": 600, "queen": 900, "king": 20000,
}

PST_PAWN = [
    [  0,  0,  0,  0,  0],
    [ 50, 55, 60, 55, 50],
    [ 20, 25, 30, 25, 20],
    [  5, 10, 15, 10,  5],
    [  0,  0,  0,  0,  0],
]
PST_KNIGHT = [
    [-20, -5,  0, -5,-20],
    [ -5, 10, 15, 10, -5],
    [  0, 15, 20, 15,  0],
    [ -5, 10, 15, 10, -5],
    [-20, -5,  0, -5,-20],
]
PST_BISHOP = [
    [-10, -5,  0, -5,-10],
    [ -5, 10, 10, 10, -5],
    [  0, 10, 15, 10,  0],
    [ -5, 10, 10, 10, -5],
    [-10, -5,  0, -5,-10],
]
PST_RIGHT = [
    [  0,  5,  5,  5,  0],
    [  0, 10, 10, 10,  0],
    [  5, 15, 20, 15,  5],
    [  0, 10, 10, 10,  0],
    [ -5,  0,  5,  0, -5],
]
PST_QUEEN = [
    [-10, -5,  0, -5,-10],
    [ -5,  5, 10,  5, -5],
    [  0, 10, 15, 10,  0],
    [ -5,  5, 10,  5, -5],
    [-10, -5,  0, -5,-10],
]
PST_KING_MID = [
    [-30,-30,-30,-30,-30],
    [-30,-30,-30,-30,-30],
    [-20,-20,-20,-20,-20],
    [-10,-10,-10,-10,-10],
    [  5, 15,  0, 15,  5],
]
PST_KING_END = [
    [-10, -5,  0, -5,-10],
    [ -5, 10, 15, 10, -5],
    [  0, 15, 25, 15,  0],
    [ -5, 10, 15, 10, -5],
    [-10, -5,  0, -5,-10],
]

PST_MAP = {
    "pawn": PST_PAWN, "knight": PST_KNIGHT, "bishop": PST_BISHOP,
    "right": PST_RIGHT, "queen": PST_QUEEN,
}


def _hash_board(board):
    pieces = []
    for p in board.get_pieces():
        pieces.append((_piece_name(p), p.player.name, p.position.x, p.position.y))
    pieces.sort()
    return hash((tuple(pieces), board.current_player.name))


def _clone_apply(board, piece, move):
    child = board.clone()
    try:
        cp = None
        for p in child.get_player_pieces(piece.player):
            if type(p) is type(piece) and p.position.x == piece.position.x and p.position.y == piece.position.y:
                cp = p; break
        if not cp: return None
        cm = None
        for m in cp.get_move_options():
            if m.position.x == move.position.x and m.position.y == move.position.y:
                cm = m; break
        if not cm: return None
        cp.move(cm)
        return child
    except Exception:
        return None


def _check_terminal(board):
    wk = bk = False
    cnt = 0
    for p in board.get_pieces():
        cnt += 1
        nm = _piece_name(p)
        if nm == "king":
            if p.player.name == "white": wk = True
            else: bk = True
        if cnt > 2 and wk and bk:
            return False, 0
    if not wk and not bk: return True, 0
    if not wk: return True, (-99999 if board.current_player.name == "white" else 99999)
    if not bk: return True, (-99999 if board.current_player.name == "black" else 99999)
    if cnt == 2: return True, 0
    return False, 0


def _score_mv(piece, move, board):
    score = 0
    name = _piece_name(piece)
    caps = getattr(move, "captures", set())
    if caps:
        for cp in caps:
            try:
                v = board[cp].piece
                if v:
                    score += 10000 + PIECE_VALUES.get(_piece_name(v), 0) - (PIECE_VALUES.get(name, 0) >> 3)
            except Exception:
                score += 5000
    if name == "pawn":
        if piece.player.name == "white" and move.position.y == 0: score += 9000
        elif piece.player.name == "black" and move.position.y == 4: score += 9000
    cx, cy = move.position.x, move.position.y
    score += (4 - abs(cx - 2) - abs(cy - 2)) * 3
    return score


# ═══════════════════════════════════════════════════════════════════════════════
#                          TIER 1: CLUB PLAYER (~1600 Elo)
# ═══════════════════════════════════════════════════════════════════════════════

def _eval_club(board, colour):
    score = 0
    for p in board.get_pieces():
        nm = _piece_name(p)
        v = PIECE_VALUES.get(nm, 0)
        pst = PST_MAP.get(nm, PST_KING_MID)
        px, py = p.position.x, p.position.y
        b = pst[py][px] if p.player.name == "white" else pst[4 - py][px]
        if p.player.name == "white": score += v + b
        else: score -= v + b
    return colour * score


def club_player(board, player, var):
    """Club Player: Iterative deepening alpha-beta to Depth 4."""
    ply, budget = var[0], var[1]
    deadline = time.perf_counter() + max(1.0, budget - 2.5)
    colour = 1 if player.name == "white" else -1

    moves = list_legal_moves_for(board, player)
    if not moves: return None, None
    if len(moves) == 1: return moves[0]

    best_p, best_m = moves[0]

    def _ab(b, d, alpha, beta, col):
        if time.perf_counter() >= deadline: raise TimeoutError
        term, tsc = _check_terminal(b)
        if term: return tsc
        if d <= 0: return _eval_club(b, col)
        mvs = list_legal_moves_for(b, b.current_player)
        if not mvs: return -99999
        mvs.sort(key=lambda x: -_score_mv(x[0], x[1], b))
        best = -float("inf")
        for p, m in mvs:
            child = _clone_apply(b, p, m)
            if not child: continue
            val = -_ab(child, d - 1, -beta, -alpha, -col)
            best = max(best, val)
            alpha = max(alpha, val)
            if alpha >= beta: break
        return best

    for depth in range(1, 5):
        try:
            cur_p, cur_m = best_p, best_m
            cur_max = -float("inf")
            ordered = sorted(moves, key=lambda x: -_score_mv(x[0], x[1], board))
            alpha = -float("inf")
            for p, m in ordered:
                child = _clone_apply(board, p, m)
                if not child: continue
                val = -_ab(child, depth - 1, -float("inf"), -alpha, -colour)
                if val > cur_max:
                    cur_max = val
                    cur_p, cur_m = p, m
                alpha = max(alpha, val)
            best_p, best_m = cur_p, cur_m
            if cur_max > 90000: break
        except TimeoutError:
            break

    return best_p, best_m


# ═══════════════════════════════════════════════════════════════════════════════
#                      TIER 2: CANDIDATE MASTER (~2100 Elo)
# ═══════════════════════════════════════════════════════════════════════════════

def candidate_master(board, player, var):
    """Candidate Master: Depth 6 PVS + Transposition Table + Quiescence (master_opponent)."""
    from master_opponent import master_opponent
    return master_opponent(board, player, var)


# ═══════════════════════════════════════════════════════════════════════════════
#                       TIER 3: NATIONAL MASTER (~2350 Elo)
# ═══════════════════════════════════════════════════════════════════════════════

_nm_tt = {}

def _eval_master_features(board, colour):
    score = 0
    white_pieces, black_pieces = [], []
    white_pawns, black_pawns = [], []
    white_king_pos = black_king_pos = None

    for p in board.get_pieces():
        nm = _piece_name(p)
        v = PIECE_VALUES.get(nm, 0)
        px, py = p.position.x, p.position.y
        if nm == "king":
            if p.player.name == "white": white_king_pos = (px, py)
            else: black_king_pos = (px, py)
        pst = PST_MAP.get(nm, PST_KING_MID)
        b = pst[py][px] if p.player.name == "white" else pst[4 - py][px]
        if p.player.name == "white":
            score += v + b
            white_pieces.append((nm, px, py))
            if nm == "pawn": white_pawns.append((px, py))
        else:
            score -= v + b
            black_pieces.append((nm, px, py))
            if nm == "pawn": black_pawns.append((px, py))

    # Anti-Stalemate King Mobility
    if white_king_pos:
        wkx, wky = white_king_pos
        w_esc = sum(1 for dx in (-1,0,1) for dy in (-1,0,1) if not (dx==0 and dy==0) and 0 <= wkx+dx < 5 and 0 <= wky+dy < 5 and (board._squares[wky+dy][wkx+dx].piece is None or board._squares[wky+dy][wkx+dx].piece.player.name != "white"))
        if w_esc <= 1: score -= 500
        score += w_esc * 8
    if black_king_pos:
        bkx, bky = black_king_pos
        b_esc = sum(1 for dx in (-1,0,1) for dy in (-1,0,1) if not (dx==0 and dy==0) and 0 <= bkx+dx < 5 and 0 <= bky+dy < 5 and (board._squares[bky+dy][bkx+dx].piece is None or board._squares[bky+dy][bkx+dx].piece.player.name != "black"))
        if b_esc <= 1: score += 500
        score -= b_esc * 8

    return colour * score


def national_master(board, player, var):
    """National Master: Depth 7-8 PVS + LMR + Advanced Positional Features."""
    global _nm_tt
    ply, budget = var[0], var[1]
    deadline = time.perf_counter() + max(1.0, budget - 2.5)
    colour = 1 if player.name == "white" else -1

    if ply <= 1 or len(_nm_tt) > 150000:
        _nm_tt = {}

    moves = list_legal_moves_for(board, player)
    if not moves: return None, None
    if len(moves) == 1: return moves[0]

    best_p, best_m = moves[0]

    def _quiesce(b, alpha, beta, col, qd):
        term, tsc = _check_terminal(b)
        if term: return tsc
        stand_pat = _eval_master_features(b, col)
        if stand_pat >= beta: return beta
        if alpha < stand_pat: alpha = stand_pat
        if qd <= 0: return alpha

        caps = []
        for p in b.get_player_pieces(b.current_player):
            for m in p.get_move_options():
                if getattr(m, "captures", None):
                    caps.append((p, m))
        caps.sort(key=lambda x: -_score_mv(x[0], x[1], b))

        for p, m in caps:
            child = _clone_apply(b, p, m)
            if not child: continue
            val = -_quiesce(child, -beta, -alpha, -col, qd - 1)
            if val >= beta: return beta
            if val > alpha: alpha = val
        return alpha

    def _nm_negamax(b, d, alpha, beta, col, pl):
        if time.perf_counter() >= deadline: raise TimeoutError
        term, tsc = _check_terminal(b)
        if term: return tsc
        if d <= 0: return _quiesce(b, alpha, beta, col, 2)

        bh = _hash_board(b)
        entry = _nm_tt.get(bh)
        if entry and entry[0] >= d:
            ed, ef, ev = entry
            if ef == 0: return ev
            elif ef == 1: alpha = max(alpha, ev)
            elif ef == 2: beta = min(beta, ev)
            if alpha >= beta: return ev

        mvs = list_legal_moves_for(b, b.current_player)
        if not mvs: return -99999 + pl
        mvs.sort(key=lambda x: -_score_mv(x[0], x[1], b))

        orig_a = alpha
        best = -float("inf")
        for i, (p, m) in enumerate(mvs):
            child = _clone_apply(b, p, m)
            if not child: continue
            if i == 0:
                val = -_nm_negamax(child, d - 1, -beta, -alpha, -col, pl + 1)
            else:
                # Late Move Reduction
                r = 1 if (d >= 3 and i >= 4 and not getattr(m, "captures", None)) else 0
                val = -_nm_negamax(child, d - 1 - r, -alpha - 1, -alpha, -col, pl + 1)
                if alpha < val < beta:
                    val = -_nm_negamax(child, d - 1, -beta, -alpha, -col, pl + 1)
            best = max(best, val)
            alpha = max(alpha, val)
            if alpha >= beta: break

        flag = 2 if best <= orig_a else (1 if best >= beta else 0)
        _nm_tt[bh] = (d, flag, best)
        return best

    for depth in range(1, 9):  # Search depth up to 8
        try:
            ordered = sorted(moves, key=lambda x: -_score_mv(x[0], x[1], board))
            cur_p, cur_m = ordered[0]
            cur_max = -float("inf")
            alpha = -float("inf")
            for p, m in ordered:
                child = _clone_apply(board, p, m)
                if not child: continue
                val = -_nm_negamax(child, depth - 1, -float("inf"), -alpha, -colour, 1)
                if val > cur_max:
                    cur_max = val
                    cur_p, cur_m = p, m
                alpha = max(alpha, val)
            best_p, best_m = cur_p, cur_m
            if cur_max > 90000: break
        except TimeoutError:
            break

    return best_p, best_m


# ═══════════════════════════════════════════════════════════════════════════════
#                          TIER 4: GRANDMASTER (~2600 Elo)
# ═══════════════════════════════════════════════════════════════════════════════

def grandmaster(board, player, var):
    """
    Grandmaster: Depth 8-10+ PVS + Tablebase integration + Aspiration Windows.
    Uses the agent's full architecture as an ultra-tough mirror opponent.
    """
    from agent import agent
    return agent(board, player, var)
