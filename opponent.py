import time
import random
from extension.board_utils import list_legal_moves_for

# ---------------------------------------------------------------------------
# Compatibility helper — works on Python 3.9 through 3.13+
# piece.name is broken in Python 3.13 due to @classmethod @property removal.
# ---------------------------------------------------------------------------
def _piece_name(piece):
    """Return the piece's name as a lower-case string, compatible with Python 3.9+."""
    return type(piece).__name__.lower()

# ---------------------------------------------------------------------------
# A moderately strong opponent for testing the agent.
# Uses a simpler evaluation + shallow alpha-beta.
# ---------------------------------------------------------------------------

PIECE_VALUES = {
    "pawn":   100,
    "knight": 320,
    "bishop": 330,
    "right":  600,
    "queen":  900,
    "king":   20000,
}


def _eval_simple(board, my_name):
    """Simple material + central control evaluation."""
    score = 0
    for piece in board.get_pieces():
        val = PIECE_VALUES.get(_piece_name(piece), 0)
        # Small centre bonus
        cx = abs(piece.position.x - 2)
        cy = abs(piece.position.y - 2)
        pos_bonus = (4 - cx - cy) * 3
        if piece.player.name == "white":
            score += val + pos_bonus
        else:
            score -= val + pos_bonus
    return score if my_name == "white" else -score


def _minimax(board, depth, alpha, beta, is_max, my_name, deadline):
    if time.perf_counter() >= deadline:
        raise TimeoutError

    from extension.board_rules import get_result
    res = get_result(board)
    if res:
        r = res.lower()
        if "draw" in r:
            return 0
        if my_name in r and "loses" in r:
            return -99999
        return 99999

    if depth <= 0:
        return _eval_simple(board, my_name)

    current = board.current_player
    moves = list_legal_moves_for(board, current)
    if not moves:
        return -99999 if is_max else 99999

    # Simple capture-first ordering
    def order_key(pm):
        caps = getattr(pm[1], "captures", set())
        return -len(caps)
    moves.sort(key=order_key)

    if is_max:
        best = -float('inf')
        for piece, move in moves:
            child = board.clone()
            try:
                cp = None
                for p in child.get_player_pieces(piece.player):
                    if type(p) is type(piece) and p.position == piece.position:
                        cp = p
                        break
                if not cp:
                    continue
                cm = None
                for m in cp.get_move_options():
                    if m.position == move.position:
                        cm = m
                        break
                if not cm:
                    continue
                cp.move(cm)
            except Exception:
                continue
            val = _minimax(child, depth - 1, alpha, beta, False, my_name, deadline)
            best = max(best, val)
            alpha = max(alpha, val)
            if alpha >= beta:
                break
        return best
    else:
        best = float('inf')
        for piece, move in moves:
            child = board.clone()
            try:
                cp = None
                for p in child.get_player_pieces(piece.player):
                    if type(p) is type(piece) and p.position == piece.position:
                        cp = p
                        break
                if not cp:
                    continue
                cm = None
                for m in cp.get_move_options():
                    if m.position == move.position:
                        cm = m
                        break
                if not cm:
                    continue
                cp.move(cm)
            except Exception:
                continue
            val = _minimax(child, depth - 1, alpha, beta, True, my_name, deadline)
            best = min(best, val)
            beta = min(beta, val)
            if alpha >= beta:
                break
        return best


def opponent(board, player, var):
    """
    A moderately strong opponent using alpha-beta to depth 3.
    Good enough to test against, but not as sophisticated as the main agent.
    """
    ply = var[0]
    time_budget = var[1]
    deadline = time.perf_counter() + time_budget - 1.0
    my_name = player.name

    moves = list_legal_moves_for(board, player)
    if not moves:
        return None, None
    if len(moves) == 1:
        return moves[0]

    best_piece, best_move = moves[0]
    best_score = -float('inf')

    for depth in range(1, 4):  # Search depth 1-3
        try:
            for piece, move in moves:
                child = board.clone()
                try:
                    cp = None
                    for p in child.get_player_pieces(piece.player):
                        if type(p) is type(piece) and p.position == piece.position:
                            cp = p
                            break
                    if not cp:
                        continue
                    cm = None
                    for m in cp.get_move_options():
                        if m.position == move.position:
                            cm = m
                            break
                    if not cm:
                        continue
                    cp.move(cm)
                except Exception:
                    continue
                val = _minimax(child, depth - 1, -float('inf'), float('inf'),
                               False, my_name, deadline)
                if val > best_score:
                    best_score = val
                    best_piece = piece
                    best_move = move
        except TimeoutError:
            break

    return best_piece, best_move
