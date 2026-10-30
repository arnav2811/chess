import time
import random
from extension.board_utils import list_legal_moves_for

# ---------------------------------------------------------------------------
# strong_opponent.py — Negamax alpha-beta depth 5 + TT + MVV-LVA + PSTs
# Designed to be a tough local test target for agent.py
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
PST_GENERIC = [
    [-10, -5,  0, -5,-10],
    [ -5,  5, 10,  5, -5],
    [  0, 10, 15, 10,  0],
    [ -5,  5, 10,  5, -5],
    [-10, -5,  0, -5,-10],
]
PST_MAP = {"pawn": PST_PAWN, "knight": PST_KNIGHT}

_stt = {}
_STT_MAX = 150000

def _hash_b(board):
    pieces = []
    for p in board.get_pieces():
        pieces.append((_piece_name(p), p.player.name, p.position.x, p.position.y))
    pieces.sort()
    return hash((tuple(pieces), board.current_player.name))

def _eval(board, colour):
    score = 0
    non_king = 0
    for piece in board.get_pieces():
        name = _piece_name(piece)
        val = PIECE_VALUES.get(name, 0)
        px, py = piece.position.x, piece.position.y
        if name != "king":
            non_king += val
        pst = PST_MAP.get(name, PST_GENERIC)
        if piece.player.name == "white":
            bonus = pst[py][px]
            score += val + bonus
        else:
            bonus = pst[4-py][px]
            score -= val + bonus
    return colour * score

def _term(board):
    wk = bk = False
    cnt = 0
    for p in board.get_pieces():
        cnt += 1
        if _piece_name(p) == "king":
            if p.player.name == "white": wk = True
            else: bk = True
        if cnt > 2 and wk and bk:
            return False, 0
    if not wk and not bk: return True, 0
    if not wk:
        return True, (-99999 if board.current_player.name=="white" else 99999)
    if not bk:
        return True, (-99999 if board.current_player.name=="black" else 99999)
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
    score += (4 - abs(cx-2) - abs(cy-2)) * 3
    return score

def _apply(board, piece, move):
    child = board.clone()
    try:
        cp = None
        for p in child.get_player_pieces(piece.player):
            if type(p) is type(piece) and p.position == piece.position:
                cp = p; break
        if not cp: return None
        cm = None
        for m in cp.get_move_options():
            if m.position == move.position:
                cm = m; break
        if not cm: return None
        cp.move(cm)
        return child
    except Exception:
        return None

_deadline = 0.0
_nodes = 0

def _negamax(board, depth, alpha, beta, colour, ply):
    global _nodes, _deadline, _stt
    _nodes += 1
    if _nodes & 31 == 0 and time.perf_counter() >= _deadline:
        raise TimeoutError

    term, tscore = _term(board)
    if term: return tscore

    if depth <= 0:
        return _eval(board, colour)

    bh = _hash_b(board)
    entry = _stt.get(bh)
    if entry and entry[0] >= depth:
        d, flag, val = entry
        if flag == 0: return val
        elif flag == 1: alpha = max(alpha, val)
        elif flag == 2: beta = min(beta, val)
        if alpha >= beta: return val

    moves = list_legal_moves_for(board, board.current_player)
    if not moves: return -99999 + ply

    moves.sort(key=lambda pm: -_score_mv(pm[0], pm[1], board))

    best = -float("inf")
    orig_alpha = alpha

    for piece, move in moves:
        child = _apply(board, piece, move)
        if child is None: continue
        val = -_negamax(child, depth-1, -beta, -alpha, -colour, ply+1)
        if val > best: best = val
        alpha = max(alpha, val)
        if alpha >= beta: break

    flag = 2 if best <= orig_alpha else (1 if best >= beta else 0)
    if len(_stt) < _STT_MAX:
        _stt[bh] = (depth, flag, best)
    return best

def strong_opponent(board, player, var):
    """
    Strong test opponent: iterative deepening negamax alpha-beta to depth 5.
    Uses PSTs, MVV-LVA, transposition table. Much stronger than depth-3 opponent.
    """
    global _deadline, _stt, _nodes
    ply = var[0]
    budget = var[1]
    _deadline = time.perf_counter() + budget - 2.0
    if ply <= 1 or len(_stt) > _STT_MAX * 0.9:
        _stt = {}

    my_name = player.name
    colour = 1 if my_name == "white" else -1

    moves = list_legal_moves_for(board, player)
    if not moves: return None, None
    if len(moves) == 1: return moves[0]

    best_piece, best_move = moves[0]

    for depth in range(1, 6):   # iterative deepening 1..5
        _nodes = 0
        try:
            ordered = sorted(moves, key=lambda pm: -_score_mv(pm[0], pm[1], board))
            cur_best_score = -float("inf")
            cur_piece, cur_move = ordered[0]
            alpha = -float("inf")
            for piece, move in ordered:
                child = _apply(board, piece, move)
                if child is None: continue
                val = -_negamax(child, depth-1, -float("inf"), -alpha, -colour, 1)
                if val > cur_best_score:
                    cur_best_score = val
                    cur_piece, cur_move = piece, move
                alpha = max(alpha, val)
            best_piece, best_move = cur_piece, cur_move
            if cur_best_score > 90000: break
        except TimeoutError:
            break

    return best_piece, best_move
