import time
import random
from extension.board_utils import list_legal_moves_for

# ---------------------------------------------------------------------------
# master_opponent.py — Depth-6 Negamax + PVS + LMR + TT + Killers + History
#                      + King Tropism + Quiescence (2-ply captures)
# The HARDEST local opponent. Stronger than strong_opponent.py (depth-5).
# ---------------------------------------------------------------------------

def _piece_name(piece):
    return type(piece).__name__.lower()

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
    [-10,  0,  5,  0,-10],
    [  0, 10, 15, 10,  0],
    [  5, 15, 20, 15,  5],
    [  0, 10, 15, 10,  0],
    [-10,  0,  5,  0,-10],
]
PST_MAP = {
    "pawn": PST_PAWN, "knight": PST_KNIGHT, "bishop": PST_BISHOP,
    "right": PST_RIGHT, "queen": PST_QUEEN,
}

# Pawn advance bonuses
_PAWN_ADV_W = [0, 60, 30, 10, 0]
_PAWN_ADV_B = [0, 10, 30, 60, 0]

# TT
_mtt = {}
_MTT_MAX = 250000
TT_EXACT, TT_LOWER, TT_UPPER = 0, 1, 2

# Killer moves + history
_m_killers = {}
_m_history = {}

_m_deadline = 0.0
_m_nodes = 0


def _hash_b(board):
    pieces = []
    for p in board.get_pieces():
        pieces.append((_piece_name(p), p.player.name, p.position.x, p.position.y))
    pieces.sort()
    return hash((tuple(pieces), board.current_player.name))


def _eval(board, colour):
    """Full evaluation: material + PST + king tropism + pawn advance + tempo."""
    score = 0
    non_king = 0
    wk_pos = bk_pos = None
    w_pieces = []
    b_pieces = []
    w_pawns = []
    b_pawns = []

    for piece in board.get_pieces():
        name = _piece_name(piece)
        px, py = piece.position.x, piece.position.y
        val = PIECE_VALUES.get(name, 0)
        if name != "king":
            non_king += val

        if name == "king":
            if piece.player.name == "white":
                wk_pos = (px, py)
            else:
                bk_pos = (px, py)
            continue

        pst = PST_MAP.get(name)
        bonus = 0
        if pst:
            bonus = pst[py][px] if piece.player.name == "white" else pst[4-py][px]

        if piece.player.name == "white":
            score += val + bonus
            w_pieces.append((name, px, py))
            if name == "pawn":
                w_pawns.append((px, py))
        else:
            score -= val + bonus
            b_pieces.append((name, px, py))
            if name == "pawn":
                b_pawns.append((px, py))

    # King PST
    is_end = non_king < 1200
    kpst = PST_KING_END if is_end else PST_KING_MID
    if wk_pos:
        score += kpst[wk_pos[1]][wk_pos[0]]
    if bk_pos:
        score -= kpst[4 - bk_pos[1]][bk_pos[0]]

    # King tropism
    t_heavy = 10 if is_end else 8
    t_minor = 6 if is_end else 5
    if bk_pos:
        bkx, bky = bk_pos
        for name, px, py in w_pieces:
            d = abs(px - bkx) + abs(py - bky)
            if name in ("queen", "right"):
                score += max(0, 4 - d) * t_heavy
            elif name in ("knight", "bishop"):
                score += max(0, 4 - d) * t_minor
    if wk_pos:
        wkx, wky = wk_pos
        for name, px, py in b_pieces:
            d = abs(px - wkx) + abs(py - wky)
            if name in ("queen", "right"):
                score -= max(0, 4 - d) * t_heavy
            elif name in ("knight", "bishop"):
                score -= max(0, 4 - d) * t_minor

    # Pawn advance
    for px, py in w_pawns:
        score += _PAWN_ADV_W[py]
    for px, py in b_pawns:
        score -= _PAWN_ADV_B[py]

    # Connected pawns
    for i, (px, py) in enumerate(w_pawns):
        for j in range(i+1, len(w_pawns)):
            ox, oy = w_pawns[j]
            if abs(px-ox) == 1 and abs(py-oy) <= 1:
                score += 12
    for i, (px, py) in enumerate(b_pawns):
        for j in range(i+1, len(b_pawns)):
            ox, oy = b_pawns[j]
            if abs(px-ox) == 1 and abs(py-oy) <= 1:
                score -= 12

    # Mobility proxy
    score += (len(w_pieces) - len(b_pieces)) * 15

    # Tempo
    if board.current_player.name == "white":
        score += 10
    else:
        score -= 10

    return colour * score


def _term(board):
    wk = bk = False
    cnt = 0
    for p in board.get_pieces():
        cnt += 1
        if _piece_name(p) == "king":
            if p.player.name == "white":
                wk = True
            else:
                bk = True
        if cnt > 2 and wk and bk:
            return False, 0
    if not wk and not bk:
        return True, 0
    if not wk:
        return True, (-99999 if board.current_player.name == "white" else 99999)
    if not bk:
        return True, (-99999 if board.current_player.name == "black" else 99999)
    if cnt == 2:
        return True, 0
    return False, 0


def _mk(piece, move):
    return (piece.position.x, piece.position.y, move.position.x, move.position.y)


def _score_mv(piece, move, board, depth):
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
        if piece.player.name == "white" and move.position.y == 0:
            score += 9000
        elif piece.player.name == "black" and move.position.y == 4:
            score += 9000
    if not caps:
        k = _mk(piece, move)
        killers = _m_killers.get(depth, [])
        if k in killers:
            score += 8000
    score += _m_history.get(_mk(piece, move), 0)
    cx, cy = move.position.x, move.position.y
    score += (4 - abs(cx-2) - abs(cy-2)) * 3
    return score


def _order(moves, board, depth, tt_best=None):
    scored = []
    for i, (piece, move) in enumerate(moves):
        s = _score_mv(piece, move, board, depth)
        if tt_best is not None and _mk(piece, move) == tt_best:
            s += 100000
        scored.append((s, i, piece, move))
    scored.sort(key=lambda x: -x[0])
    return [(p, m) for (_, _, p, m) in scored]


def _apply(board, piece, move):
    child = board.clone()
    try:
        cp = None
        for p in child.get_player_pieces(piece.player):
            if type(p) is type(piece) and p.position == piece.position:
                cp = p
                break
        if not cp:
            return None
        cm = None
        for m in cp.get_move_options():
            if m.position == move.position:
                cm = m
                break
        if not cm:
            return None
        cp.move(cm)
        return child
    except Exception:
        return None


def _quiesce(board, alpha, beta, colour, qd):
    """Capture-only quiescence search, max 2 plies."""
    global _m_nodes, _m_deadline
    _m_nodes += 1
    if _m_nodes & 31 == 0 and time.perf_counter() >= _m_deadline:
        raise TimeoutError

    t, ts = _term(board)
    if t:
        return ts

    sp = colour * _eval(board, 1)  # stand-pat with colour=1 then multiply
    # Actually _eval already does colour multiplication, so:
    sp = _eval(board, colour)
    if sp >= beta:
        return sp
    if sp > alpha:
        alpha = sp
    if qd <= 0:
        return sp

    moves = list_legal_moves_for(board, board.current_player)
    if not moves:
        return -99999

    caps = []
    for piece, move in moves:
        c = getattr(move, "captures", set())
        if c:
            cs = 0
            for cp in c:
                try:
                    v = board[cp].piece
                    if v:
                        cs += PIECE_VALUES.get(_piece_name(v), 0)
                except Exception:
                    cs += 200
            caps.append((cs, piece, move))
        elif _piece_name(piece) == "pawn":
            if (piece.player.name == "white" and move.position.y == 0) or \
               (piece.player.name == "black" and move.position.y == 4):
                caps.append((9000, piece, move))

    if not caps:
        return sp
    caps.sort(key=lambda x: -x[0])

    for _, piece, move in caps:
        child = _apply(board, piece, move)
        if child is None:
            continue
        val = -_quiesce(child, -beta, -alpha, -colour, qd - 1)
        if val > alpha:
            alpha = val
        if alpha >= beta:
            break
    return alpha


def _negamax(board, depth, alpha, beta, colour, ply):
    global _m_nodes, _m_deadline, _mtt
    _m_nodes += 1
    if _m_nodes & 31 == 0 and time.perf_counter() >= _m_deadline:
        raise TimeoutError

    t, ts = _term(board)
    if t:
        return ts

    if depth <= 0:
        return _quiesce(board, alpha, beta, colour, 2)

    bh = _hash_b(board)
    entry = _mtt.get(bh)
    tt_best = None
    if entry is not None:
        ed, ef, ev, em = entry
        if ed >= depth:
            if ef == TT_EXACT:
                return ev
            elif ef == TT_LOWER:
                alpha = max(alpha, ev)
            elif ef == TT_UPPER:
                beta = min(beta, ev)
            if alpha >= beta:
                return ev
        tt_best = em

    # Reverse futility pruning (static eval already above beta by margin)
    if depth <= 3 and abs(beta) < 90000:
        rfp_margin = 120 * depth
        se = _eval(board, colour)
        if se - rfp_margin >= beta:
            return se

    moves = list_legal_moves_for(board, board.current_player)
    if not moves:
        return -99999 + ply

    ordered = _order(moves, board, ply, tt_best)

    # Futility pruning flag
    futile = False
    if depth == 1 and abs(alpha) < 90000:
        se = _eval(board, colour)
        if se + 200 <= alpha:
            futile = True

    best = -float("inf")
    best_mk = None
    orig_alpha = alpha
    ms = 0

    for piece, move in ordered:
        caps = getattr(move, "captures", set())
        is_tac = bool(caps) or (_piece_name(piece) == "pawn" and
            ((piece.player.name == "white" and move.position.y <= 1) or
             (piece.player.name == "black" and move.position.y >= 3)))

        if futile and ms > 0 and not is_tac:
            continue

        child = _apply(board, piece, move)
        if child is None:
            continue

        # LMR
        reduction = 0
        if ms >= 3 and depth >= 3 and not is_tac and ply >= 2:
            reduction = 1
            if ms >= 6:
                reduction = 2

        # PVS
        if ms == 0:
            val = -_negamax(child, depth-1-reduction, -beta, -alpha, -colour, ply+1)
        else:
            val = -_negamax(child, depth-1-reduction, -alpha-1, -alpha, -colour, ply+1)
            if alpha < val < beta:
                val = -_negamax(child, depth-1, -beta, -alpha, -colour, ply+1)
            elif reduction > 0 and val > alpha:
                val = -_negamax(child, depth-1, -beta, -alpha, -colour, ply+1)

        ms += 1
        if val > best:
            best = val
            best_mk = _mk(piece, move)
        alpha = max(alpha, val)
        if alpha >= beta:
            if not caps:
                k = _mk(piece, move)
                if ply not in _m_killers:
                    _m_killers[ply] = []
                kl = _m_killers[ply]
                if k not in kl:
                    kl.insert(0, k)
                    if len(kl) > 2:
                        kl.pop()
                _m_history[k] = _m_history.get(k, 0) + depth * depth
            break

    flag = TT_UPPER if best <= orig_alpha else (TT_LOWER if best >= beta else TT_EXACT)
    if len(_mtt) < _MTT_MAX:
        _mtt[bh] = (depth, flag, best, best_mk)
    return best


def master_opponent(board, player, var):
    """
    Master opponent: iterative deepening negamax to depth 7 with PVS + LMR +
    TT + killer moves + history + king tropism + quiescence + futility + RFP.
    Significantly stronger than strong_opponent.py.
    """
    global _m_deadline, _mtt, _m_nodes, _m_killers, _m_history
    ply = var[0]
    budget = var[1]
    _m_deadline = time.perf_counter() + budget - 1.5
    if ply <= 1 or len(_mtt) > _MTT_MAX * 0.9:
        _mtt = {}
    _m_killers = {}
    _m_history = {}

    colour = 1 if player.name == "white" else -1
    moves = list_legal_moves_for(board, player)
    if not moves:
        return None, None
    if len(moves) == 1:
        return moves[0]

    best_piece, best_move = moves[0]
    prev_score = 0

    for depth in range(1, 8):  # iterative deepening 1..7
        _m_nodes = 0
        try:
            ordered = _order(moves, board, 0, None)
            cur_best = -float("inf")
            cur_p, cur_m = ordered[0]

            # Aspiration windows at depth >= 3
            if depth >= 3:
                a = prev_score - 100
                b = prev_score + 100
            else:
                a = -float("inf")
                b = float("inf")

            while True:
                cur_best = -float("inf")
                cur_p, cur_m = ordered[0]
                ms = 0
                alpha_r = a

                for piece, move in ordered:
                    child = _apply(board, piece, move)
                    if child is None:
                        continue
                    if ms == 0:
                        val = -_negamax(child, depth-1, -b, -alpha_r, -colour, 1)
                    else:
                        val = -_negamax(child, depth-1, -alpha_r-1, -alpha_r, -colour, 1)
                        if alpha_r < val < b:
                            val = -_negamax(child, depth-1, -b, -alpha_r, -colour, 1)
                    if val > cur_best:
                        cur_best = val
                        cur_p, cur_m = piece, move
                    alpha_r = max(alpha_r, val)
                    ms += 1

                if depth < 3:
                    break
                delta = 100
                if cur_best <= prev_score - delta:
                    delta = min(delta * 4, 2000)
                    a = prev_score - delta
                elif cur_best >= prev_score + delta:
                    delta = min(delta * 4, 2000)
                    b = prev_score + delta
                else:
                    break

            best_piece, best_move = cur_p, cur_m
            prev_score = cur_best
            if cur_best > 90000:
                break
        except TimeoutError:
            break

    return best_piece, best_move
