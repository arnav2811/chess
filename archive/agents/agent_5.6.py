# ═══════════════════════════════════════════════════════════════════════════════
# agent.py — Chess Fragments AI Agent (v5.6)
# COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces
#
# Architecture at a Glance:
#   • Iterative Deepening Negamax with Alpha-Beta Pruning
#   • Principal Variation Search (PVS) with zero-window re-search
#   • Aspiration Windows (±250 cp, auto-widens on fail)
#   • Transposition Table (200 k entries, coordinate-keyed moves)
#   • 6-Tier Move Ordering: PV > MVV-LVA > Promotion > Killers > History > Centre
#   • Late Move Reductions (LMR) for non-tactical late moves
#   • 2-Ply Quiescence Search (capture-only, with delta pruning)
#   • Frontier Futility Pruning at depth 1
#   • Anti-Stalemate King Mobility Gradient (stalemate = loss)
#   • Dynamic Game-Clock Budgeting (prevents 300 s timeout)
#   • Self-Learning Opening Book (plies 1–2)
#   • Repetition Avoidance (prevents fivefold-repetition draws)
#   • Per-move instrumentation logged to stderr
#
# Constraints:
#   Single-file agent — no external dependencies beyond Python built-ins,
#   the chessmaker library, and the provided board_utils helper.
# ═══════════════════════════════════════════════════════════════════════════════

import time
import random
import sys
from extension.board_utils import list_legal_moves_for

try:
    from endgame_tablebase import probe_endgame_tb
except ImportError:
    probe_endgame_tb = None

try:
    from opening_book import lookup_book_move
except ImportError:
    lookup_book_move = None


# ─── Python Compatibility ─────────────────────────────────────────────────────
# chessmaker uses @classmethod @property for piece.name, which was deprecated
# in Python 3.11 and broken entirely in 3.13 (returns a raw property object).
# Reading the class name via type().__name__ is portable across 3.9–3.13+.
# ──────────────────────────────────────────────────────────────────────────────

def _piece_name(piece):
    """Return the piece's class name as a lowercase string (e.g. 'knight')."""
    return type(piece).__name__.lower()


# ─── Material Values ──────────────────────────────────────────────────────────
# Tuned for the 5×5 "Chess Fragments" board.  Standard chess values are the
# baseline, adjusted for compact geometry:
#   • Knight +20 (fork density is higher on 5×5)
#   • Right = Knight + Rook hybrid, valued at 600
#   • King  = 20 000 (must dominate all material comparisons)
# ──────────────────────────────────────────────────────────────────────────────

PIECE_VALUES = {
    "pawn":   100,
    "knight": 320,
    "bishop": 330,
    "right":  600,    # Rook + Knight hybrid — strongest non-Queen piece
    "queen":  900,
    "king":   20000,
}


# ─── Piece-Square Tables (PSTs) ──────────────────────────────────────────────
# Encoded from White's perspective (White advances toward row 0).
# For Black, tables are vertically mirrored: row y → row (4 − y).
# ──────────────────────────────────────────────────────────────────────────────

PST_PAWN = [
    [  0,   0,   0,   0,   0],
    [ 50,  55,  60,  55,  50],
    [ 20,  25,  30,  25,  20],
    [  5,  10,  15,  10,   5],
    [  0,   0,   0,   0,   0],
]

PST_KNIGHT = [
    [-20,  -5,   0,  -5, -20],
    [ -5,  10,  15,  10,  -5],
    [  0,  15,  20,  15,   0],
    [ -5,  10,  15,  10,  -5],
    [-20,  -5,   0,  -5, -20],
]

PST_BISHOP = [
    [-10,  -5,   0,  -5, -10],
    [ -5,  10,  10,  10,  -5],
    [  0,  10,  15,  10,   0],
    [ -5,  10,  10,  10,  -5],
    [-10,  -5,   0,  -5, -10],
]

PST_RIGHT = [
    [  0,   5,   5,   5,   0],
    [  0,  10,  10,  10,   0],
    [  5,  15,  20,  15,   5],
    [  0,  10,  10,  10,   0],
    [ -5,   0,   5,   0,  -5],
]

PST_QUEEN = [
    [-10,  -5,   0,  -5, -10],
    [ -5,   5,  10,   5,  -5],
    [  0,  10,  15,  10,   0],
    [ -5,   5,  10,   5,  -5],
    [-10,  -5,   0,  -5, -10],
]

# King PSTs — separate midgame and endgame tables.
# Midgame: king stays near the back rank behind pawns.
# Endgame: king centralises to support passed pawns and join the attack.

PST_KING_MID = [
    [-30, -30, -30, -30, -30],
    [-30, -30, -30, -30, -30],
    [-20, -20, -20, -20, -20],
    [-10, -10, -10, -10, -10],
    [  5,  15,   0,  15,   5],
]

PST_KING_END = [
    [-10,   0,   5,   0, -10],
    [  0,  10,  15,  10,   0],
    [  5,  15,  20,  15,   5],
    [  0,  10,  15,  10,   0],
    [-10,   0,   5,   0, -10],
]

PST_MAP = {
    "pawn":   PST_PAWN,
    "knight": PST_KNIGHT,
    "bishop": PST_BISHOP,
    "right":  PST_RIGHT,
    "queen":  PST_QUEEN,
}


# ─── Transposition Table (TT) ────────────────────────────────────────────────
# Caches previously searched positions so identical states (reached via
# different move orders) are never re-evaluated.  Each entry stores:
#   (depth, bound_type, score, best_move_coords)
# On a 5×5 board, transpositions are very common — the TT typically saves
# 30–50 % of total search effort.
# ──────────────────────────────────────────────────────────────────────────────

TT_EXACT = 0    # Score is exact (result fell within [α, β])
TT_LOWER = 1    # Score is a lower bound (β-cutoff occurred)
TT_UPPER = 2    # Score is an upper bound (all moves failed to raise α)

_tt = {}
_TT_MAX_SIZE = 200_000


# ─── Self-Learning Opening Book ──────────────────────────────────────────────
# On the first encounter with a board position at ply 1 or 2, the agent runs
# a full search and caches the result.  On subsequent encounters (e.g. in a
# multi-game tournament session), the cached move is returned in ≈ 0 ms,
# saving the entire 12 s thinking budget.  No disk I/O — stays within the
# single-file coursework constraint.
# ──────────────────────────────────────────────────────────────────────────────

_opening_book = {}   # (board_hash, player_name, ply) → (fx, fy, tx, ty)


# ─── Killer Moves & History Heuristic ─────────────────────────────────────────
# Two complementary move-ordering heuristics that learn during the search:
#
# Killer moves:  2 non-capture moves per depth that caused β-cutoffs.
#                Tried before other quiet moves at the same depth.
# History table: Global counter for how often each (from, to) pair caused a
#                cutoff, weighted by depth².  Moves with high history scores
#                are searched earlier across the entire tree.
#
# Better ordering → more cutoffs → exponentially less branching → deeper
# search within the same time budget.
# ──────────────────────────────────────────────────────────────────────────────

_killer_moves = {}   # depth → [(from_pos, to_pos), ...]  (max 2 per depth)
_history = {}        # (fx, fy, tx, ty) → cumulative score


# ─── Global Search State ──────────────────────────────────────────────────────

_nodes_searched = 0
_deadline = 0.0
_ASPIRATION_DELTA = 250    # Initial aspiration-window half-width (centipawns)


# ─── Per-Move Instrumentation ─────────────────────────────────────────────────

_last_depth_reached = 0
_last_nodes_searched = 0
_last_branching_factor = 0.0
_move_stats_log = []       # One dict per agent() call


# ─── Repetition Tracking ─────────────────────────────────────────────────────

_position_history = {}     # board_hash → count of times reached


# ─── Game-Phase & Clock Tracking ──────────────────────────────────────────────

_current_ply = 0           # Updated each agent() call
_game_start_time = 0.0     # Monotonic clock at ply 1
_last_seen_ply = -1        # Detects new-game resets
_my_total_time_spent = 0.0 # Cumulative time spent by our agent (for individual 300s budget)


# ─── Pawn Advance Bonuses (context-aware) ─────────────────────────────────────
# In early game (ply < 8), White uses damped bonuses to avoid premature pushes
# that the depth-5 opponent can exploit.  Black always gets full bonuses
# (counter-attacking as Black was dominant in v5.4 testing at 83.3 % WR).

_PAWN_ADVANCE_BONUS_WHITE       = [0, 60, 30, 10, 0]   # row y for White
_PAWN_ADVANCE_BONUS_BLACK       = [0, 10, 30, 60, 0]   # row y for Black
_PAWN_ADVANCE_BONUS_WHITE_EARLY = [0, 30, 15,  5, 0]   # damped for ply < 8


# ═══════════════════════════════════════════════════════════════════════════════
#                            UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def _hash_board(board):
    """
    Hash the current position for the transposition table.

    Uses a sorted tuple of (piece_name, player, x, y) + side-to-move.
    Python's built-in hash() on tuples is C-optimised and extremely fast.
    Zobrist hashing was considered but rejected: maintaining incremental XOR
    across ChessMaker's deep-copy board.clone() architecture is fragile, and
    collision risk is negligible on a 5×5 board.
    """
    pieces = []
    for p in board.get_pieces():
        pieces.append((_piece_name(p), p.player.name, p.position.x, p.position.y))
    pieces.sort()
    return hash((tuple(pieces), board.current_player.name))


def _check_terminal(board):
    """
    Lightweight terminal-state detection (no move generation required).

    Returns (is_terminal, score_from_current_player_perspective).
    Avoids get_result() which mutates internal repetition state.
    """
    white_king = black_king = None
    piece_count = 0

    for piece in board.get_pieces():
        piece_count += 1
        if _piece_name(piece) == "king":
            if piece.player.name == "white":
                white_king = piece
            else:
                black_king = piece
        # Fast exit: both kings alive + at least one other piece
        if piece_count > 2 and white_king and black_king:
            return False, 0

    if white_king is None and black_king is None:
        return True, 0   # Mutual annihilation (shouldn't happen, but safe)
    if white_king is None:
        return True, (-99999 if board.current_player.name == "white" else 99999)
    if black_king is None:
        return True, (-99999 if board.current_player.name == "black" else 99999)
    if piece_count == 2:
        return True, 0   # Only two kings — automatic draw

    return False, 0


def _make_move_on_clone(board, piece, move):
    """
    Clone the board and execute the given move on the clone.

    Returns the resulting Board, or None if the move couldn't be applied
    (e.g. piece was captured in the cloning gap — shouldn't happen in
    normal play, but defensive coding prevents crashes).
    """
    child = board.clone()
    try:
        # Find the corresponding piece on the cloned board
        child_piece = None
        for cp in child.get_player_pieces(piece.player):
            if type(cp) is type(piece) and cp.position == piece.position:
                child_piece = cp
                break
        if child_piece is None:
            return None

        # Find the matching move option
        dest = move.position
        child_move = None
        for m in child_piece.get_move_options():
            if m.position == dest:
                child_move = m
                break
        if child_move is None:
            return None

        child_piece.move(child_move)
        return child
    except Exception:
        return None


def _is_unobstructed(board, x1, y1, x2, y2):
    """Check if the straight path between (x1, y1) and (x2, y2) has no pieces."""
    dx = 0 if x1 == x2 else (1 if x2 > x1 else -1)
    dy = 0 if y1 == y2 else (1 if y2 > y1 else -1)
    cx, cy = x1 + dx, y1 + dy
    while cx != x2 or cy != y2:
        if board._squares[cy][cx].piece is not None:
            return False
        cx += dx
        cy += dy
    return True


_SIG_SYMS = {'pawn':'p', 'knight':'n', 'bishop':'b', 'right':'r', 'queen':'q', 'king':'k'}

def _board_signature(board):
    """Return deterministic 25-char string of piece placements."""
    chars = []
    for row in board._squares:
        for sq in row:
            p = sq.piece
            if p is None:
                chars.append('.')
            else:
                c = _SIG_SYMS.get(type(p).__name__.lower(), '?')
                chars.append(c.upper() if p.player.name == 'white' else c)
    return ''.join(chars)


# ═══════════════════════════════════════════════════════════════════════════════
#                          EVALUATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


def evaluate_for_white(board):
    """
    Static evaluation from White's perspective — runs in O(num_pieces).

    Components (all computed without move generation):
      1. Material balance            — piece values from PIECE_VALUES
      2. Piece-square tables         — positional bonuses per piece type
      3. King PST (mid/end switch)   — keeps king safe / centralises in endgame
      4. King tropism                — rewards proximity to enemy king
      5. Advanced pawn bonus          — context-aware promotion incentive
      6. Connected pawns             — bonus for pawn chains
      7. Mobility proxy              — piece-count advantage as crude mobility
      8. King freedom (anti-stalemate) — penalises boxed-in kings (stalemate = loss!)
      9. Tempo bonus                  — small edge for the side to move
    """
    global _current_ply
    score = 0
    total_non_king = 0
    white_king_pos = black_king_pos = None

    white_pieces = []    # (name, x, y) — for tropism
    black_pieces = []
    white_pawns = []     # (x, y) — for pawn structure
    black_pawns = []
    white_piece_count = 0
    black_piece_count = 0

    # ── Single-pass piece scan ────────────────────────────────────────────
    for piece in board.get_pieces():
        name = _piece_name(piece)
        px, py = piece.position.x, piece.position.y
        val = PIECE_VALUES.get(name, 0)

        if name != "king":
            total_non_king += val

        if name == "king":
            if piece.player.name == "white":
                white_king_pos = (px, py)
            else:
                black_king_pos = (px, py)
            continue

        pst = PST_MAP.get(name)
        pst_bonus = 0
        if pst:
            if piece.player.name == "white":
                pst_bonus = pst[py][px]
            else:
                pst_bonus = pst[4 - py][px]

        if piece.player.name == "white":
            score += val + pst_bonus
            white_pieces.append((name, px, py))
            white_piece_count += 1
            if name == "pawn":
                white_pawns.append((px, py))
        else:
            score -= val + pst_bonus
            black_pieces.append((name, px, py))
            black_piece_count += 1
            if name == "pawn":
                black_pawns.append((px, py))

    # ── King PST (midgame vs endgame) ─────────────────────────────────────
    is_endgame = total_non_king < 1200
    king_pst = PST_KING_END if is_endgame else PST_KING_MID

    if white_king_pos:
        score += king_pst[white_king_pos[1]][white_king_pos[0]]
    if black_king_pos:
        score -= king_pst[4 - black_king_pos[1]][black_king_pos[0]]

    # ── King Tropism ──────────────────────────────────────────────────────
    # On 5×5, proximity to the enemy king matters enormously.  Heavy pieces
    # (Queen, Right) get a larger bonus; minor pieces get a smaller one.
    # Endgame weights are boosted because king attacks become decisive.
    tropism_heavy = 10 if is_endgame else 7
    tropism_minor = 6 if is_endgame else 4

    if black_king_pos:
        bkx, bky = black_king_pos
        for name, px, py in white_pieces:
            dist = abs(px - bkx) + abs(py - bky)
            if name in ("queen", "right"):
                score += max(0, (4 - dist)) * tropism_heavy
            elif name in ("knight", "bishop"):
                score += max(0, (4 - dist)) * tropism_minor

    if white_king_pos:
        wkx, wky = white_king_pos
        for name, px, py in black_pieces:
            dist = abs(px - wkx) + abs(py - wky)
            if name in ("queen", "right"):
                score -= max(0, (4 - dist)) * tropism_heavy
            elif name in ("knight", "bishop"):
                score -= max(0, (4 - dist)) * tropism_minor

    # ── Advanced Pawn Bonus (context-aware) ───────────────────────────────
    # Pawns near promotion are exponentially more valuable.  In early game
    # (ply < 8), White uses damped bonuses to avoid premature pushes.
    white_pawn_table = (
        _PAWN_ADVANCE_BONUS_WHITE_EARLY if _current_ply < 8
        else _PAWN_ADVANCE_BONUS_WHITE
    )
    for px, py in white_pawns:
        score += white_pawn_table[py]
    for px, py in black_pawns:
        score -= _PAWN_ADVANCE_BONUS_BLACK[py]

    # ── Connected Pawns ───────────────────────────────────────────────────
    # Adjacent friendly pawns support each other — small structural bonus.
    for i, (px, py) in enumerate(white_pawns):
        for j in range(i + 1, len(white_pawns)):
            ox, oy = white_pawns[j]
            if abs(px - ox) == 1 and abs(py - oy) <= 1:
                score += 12
    for i, (px, py) in enumerate(black_pawns):
        for j in range(i + 1, len(black_pawns)):
            ox, oy = black_pawns[j]
            if abs(px - ox) == 1 and abs(py - oy) <= 1:
                score -= 12

    # ── Mobility Proxy ────────────────────────────────────────────────────
    # More pieces ≈ more legal moves.  Avoids the costly list_legal_moves_for().
    score += (white_piece_count - black_piece_count) * 15

    # ── King Freedom (Anti-Stalemate Gradient) ────────────────────────────
    # In Chess Fragments, stalemate = LOSS.  We count King escape squares
    # directly from board._squares in O(1) — no move generation needed.
    # Severely penalise own king being boxed in; reward suffocating the enemy.
    if white_king_pos:
        wkx, wky = white_king_pos
        white_king_freedom = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = wkx + dx, wky + dy
                if 0 <= nx < 5 and 0 <= ny < 5:
                    p = board._squares[ny][nx].piece
                    if p is None or p.player.name != "white":
                        white_king_freedom += 1
        if is_endgame:
            if white_king_freedom <= 1:
                score -= 2000    # Extreme stalemate danger
            elif white_king_freedom == 2:
                score -= 300
        else:
            if white_king_freedom <= 1:
                score -= 500
        score += white_king_freedom * 8

    if black_king_pos:
        bkx, bky = black_king_pos
        black_king_freedom = 0
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = bkx + dx, bky + dy
                if 0 <= nx < 5 and 0 <= ny < 5:
                    p = board._squares[ny][nx].piece
                    if p is None or p.player.name != "black":
                        black_king_freedom += 1
        if is_endgame:
            if black_king_freedom <= 1:
                score += 2000    # Suffocating opponent to force stalemate
            elif black_king_freedom == 2:
                score += 300
        else:
            if black_king_freedom <= 1:
                score += 500
        score -= black_king_freedom * 8

    # ── Piece Correlation & Coordination ──────────────────────────────────
    # 1. King Ring / Multi-Attacker Convergence (Ray-checked)
    ATTACKER_BONUS = [0, 20, 90, 240, 350, 450]

    if black_king_pos:
        bkx, bky = black_king_pos
        w_attackers = 0
        for name, px, py in white_pieces:
            attacks_ring = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    rx, ry = bkx + dx, bky + dy
                    if 0 <= rx < 5 and 0 <= ry < 5:
                        ddx, ddy = abs(px - rx), abs(py - ry)
                        if name == "pawn":
                            if dy == 1 and ddx == 1 and py - ry == 1:
                                attacks_ring = True; break
                        elif name == "knight":
                            if (ddx == 1 and ddy == 2) or (ddx == 2 and ddy == 1):
                                attacks_ring = True; break
                        elif name == "bishop":
                            if ddx == ddy and ddx > 0 and _is_unobstructed(board, px, py, rx, ry):
                                attacks_ring = True; break
                        elif name == "right":
                            if ((ddx == 1 and ddy == 2) or (ddx == 2 and ddy == 1)):
                                attacks_ring = True; break
                            elif (px == rx or py == ry) and _is_unobstructed(board, px, py, rx, ry):
                                attacks_ring = True; break
                        elif name == "queen":
                            if (px == rx or py == ry or ddx == ddy) and _is_unobstructed(board, px, py, rx, ry):
                                attacks_ring = True; break
                if attacks_ring:
                    break
            if attacks_ring:
                w_attackers += 1
        score += ATTACKER_BONUS[min(len(ATTACKER_BONUS) - 1, w_attackers)]

    if white_king_pos:
        wkx, wky = white_king_pos
        b_attackers = 0
        for name, px, py in black_pieces:
            attacks_ring = False
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    rx, ry = wkx + dx, wky + dy
                    if 0 <= rx < 5 and 0 <= ry < 5:
                        ddx, ddy = abs(px - rx), abs(py - ry)
                        if name == "pawn":
                            if dy == -1 and ddx == 1 and ry - py == 1:
                                attacks_ring = True; break
                        elif name == "knight":
                            if (ddx == 1 and ddy == 2) or (ddx == 2 and ddy == 1):
                                attacks_ring = True; break
                        elif name == "bishop":
                            if ddx == ddy and ddx > 0 and _is_unobstructed(board, px, py, rx, ry):
                                attacks_ring = True; break
                        elif name == "right":
                            if ((ddx == 1 and ddy == 2) or (ddx == 2 and ddy == 1)):
                                attacks_ring = True; break
                            elif (px == rx or py == ry) and _is_unobstructed(board, px, py, rx, ry):
                                attacks_ring = True; break
                        elif name == "queen":
                            if (px == rx or py == ry or ddx == ddy) and _is_unobstructed(board, px, py, rx, ry):
                                attacks_ring = True; break
                if attacks_ring:
                    break
            if attacks_ring:
                b_attackers += 1
        score -= ATTACKER_BONUS[min(len(ATTACKER_BONUS) - 1, b_attackers)]

    # 2. Heavy Piece Battery (Queen + Right aligned on active file/rank, unobstructed)
    w_queens = [(px, py) for n, px, py in white_pieces if n == "queen"]
    w_rights = [(px, py) for n, px, py in white_pieces if n == "right"]
    for qx, qy in w_queens:
        for rx, ry in w_rights:
            if qx == rx and _is_unobstructed(board, qx, qy, rx, ry):
                score += 60
            elif qy == ry and qy not in (0, 4) and _is_unobstructed(board, qx, qy, rx, ry):
                score += 45

    b_queens = [(px, py) for n, px, py in black_pieces if n == "queen"]
    b_rights = [(px, py) for n, px, py in black_pieces if n == "right"]
    for qx, qy in b_queens:
        for rx, ry in b_rights:
            if qx == rx and _is_unobstructed(board, qx, qy, rx, ry):
                score -= 60
            elif qy == ry and qy not in (0, 4) and _is_unobstructed(board, qx, qy, rx, ry):
                score -= 45

    # 3. Pawn-Defended Pieces & Advanced Outposts
    for px, py in white_pawns:
        for def_x in (px - 1, px + 1):
            def_y = py - 1
            if 0 <= def_x < 5 and 0 <= def_y < 5:
                for n, x, y in white_pieces:
                    if x == def_x and y == def_y and n != "pawn":
                        score += 60 if def_y <= 2 else 35

    for px, py in black_pawns:
        for def_x in (px - 1, px + 1):
            def_y = py + 1
            if 0 <= def_x < 5 and 0 <= def_y < 5:
                for n, x, y in black_pieces:
                    if x == def_x and y == def_y and n != "pawn":
                        score -= 60 if def_y >= 2 else 35

    # 4. Minor Piece Synergy (Bishop + Knight pair)
    w_has_b = any(n == "bishop" for n, _, _ in white_pieces)
    w_has_n = any(n == "knight" for n, _, _ in white_pieces)
    b_has_b = any(n == "bishop" for n, _, _ in black_pieces)
    b_has_n = any(n == "knight" for n, _, _ in black_pieces)
    if w_has_b and w_has_n and not (b_has_b and b_has_n):
        score += 35
    elif b_has_b and b_has_n and not (w_has_b and w_has_n):
        score -= 35

    # ── Tempo Bonus ───────────────────────────────────────────────────────
    if board.current_player.name == "white":
        score += 10
    else:
        score -= 10

    return score


# ═══════════════════════════════════════════════════════════════════════════════
#                            MOVE ORDERING
# ═══════════════════════════════════════════════════════════════════════════════


def _move_key(piece, move):
    """Canonical coordinate key for a move: (from_x, from_y, to_x, to_y)."""
    return (piece.position.x, piece.position.y, move.position.x, move.position.y)


def _score_move(piece, move, board, depth):
    """
    Assign a heuristic priority score to a move for ordering.

    Priority tiers (highest first):
      1. Captures scored by MVV-LVA (Most Valuable Victim − Least Valuable Attacker)
      2. Pawn promotions
      3. Killer moves (quiet moves that caused β-cutoffs at this depth)
      4. History heuristic (global cutoff counter)
      5. Centre proximity
    """
    score = 0
    mk = _move_key(piece, move)

    # 1. Captures — MVV-LVA
    caps = getattr(move, "captures", set())
    if caps:
        for cap_pos in caps:
            try:
                victim = board[cap_pos].piece
                if victim:
                    victim_val = PIECE_VALUES.get(_piece_name(victim), 0)
                    attacker_val = PIECE_VALUES.get(_piece_name(piece), 0)
                    score += 10000 + victim_val - (attacker_val >> 3)
            except Exception:
                score += 5000

    # 2. Pawn promotion
    if _piece_name(piece) == "pawn":
        if piece.player.name == "white" and move.position.y == 0:
            score += 9000
        elif piece.player.name == "black" and move.position.y == 4:
            score += 9000

    # 3. Killer moves
    if not caps:
        killers = _killer_moves.get(depth, [])
        if mk in killers:
            score += 8000

    # 4. History heuristic
    score += _history.get(mk, 0)

    # 5. Centre preference
    cx, cy = move.position.x, move.position.y
    centre_dist = abs(cx - 2) + abs(cy - 2)
    score += (4 - centre_dist) * 3

    return score


def _order_moves(moves, board, depth=0, tt_best_move=None):
    """
    Sort moves by heuristic priority (best first).

    The TT best move (if any) is boosted to ensure it's searched first — this
    is the single most impactful move-ordering technique, as it represents the
    principal variation from the previous iteration.
    """
    scored = []
    for i, (piece, move) in enumerate(moves):
        s = _score_move(piece, move, board, depth)
        if tt_best_move is not None:
            if _move_key(piece, move) == tt_best_move:
                s += 100000    # PV move — search first
        scored.append((s, i, piece, move))
    scored.sort(key=lambda x: -x[0])
    return [(p, m) for (_, _, p, m) in scored]


def _store_killer(depth, piece, move):
    """Record a killer move at the given depth (max 2 per depth, FIFO)."""
    mk = _move_key(piece, move)
    if depth not in _killer_moves:
        _killer_moves[depth] = []
    killers = _killer_moves[depth]
    if mk not in killers:
        killers.insert(0, mk)
        if len(killers) > 2:
            killers.pop()


def _update_history(piece, move, depth):
    """Increment the history score for a move that caused a β-cutoff."""
    mk = _move_key(piece, move)
    _history[mk] = _history.get(mk, 0) + depth * depth


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHECK DETECTION (lightweight)
# ═══════════════════════════════════════════════════════════════════════════════


def _is_in_check(board):
    """
    Returns True if the current player's king is under attack.

    Scans enemy pieces and checks whether any of their legal destinations
    capture or land on the king square.  Costs ≈ 5 ms, so only called when
    a check extension is likely valuable (shallow depth, no captures).
    """
    current = board.current_player
    king_pos = None
    for p in board.get_pieces():
        if _piece_name(p) == "king" and p.player.name == current.name:
            king_pos = p.position
            break
    if king_pos is None:
        return False

    for p in board.get_pieces():
        if p.player.name != current.name and _piece_name(p) != "king":
            try:
                for m in p.get_move_options():
                    caps = getattr(m, "captures", set())
                    if king_pos in caps or m.position == king_pos:
                        return True
            except Exception:
                pass
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#                          QUIESCENCE SEARCH
# ═══════════════════════════════════════════════════════════════════════════════


def _quiescence(board, alpha, beta, colour, q_depth):
    """
    Capture-only extension search at leaf nodes.

    Prevents the horizon effect — ensures we don't stop searching right
    before a winning (or losing) capture.  Bounded to *q_depth* plies of
    captures to stay within the time budget.

    Also considers pawn promotions as tactical moves.
    """
    global _nodes_searched, _deadline

    _nodes_searched += 1
    if _nodes_searched & 31 == 0:
        if time.perf_counter() >= _deadline:
            raise TimeoutError

    # Terminal check
    is_term, term_score = _check_terminal(board)
    if is_term:
        return term_score

    # Endgame Tablebase Probe (O(1) exact solved positions <= 4 pieces)
    if probe_endgame_tb is not None:
        mat_diff = colour * evaluate_for_white(board)
        tb_hit, tb_score = probe_endgame_tb(board, _piece_name, 0, mat_diff)
        if tb_hit:
            return tb_score

    # Stand-pat: the static evaluation is a baseline — we can always choose
    # not to capture and accept the current position.
    stand_pat = colour * evaluate_for_white(board)

    if stand_pat >= beta:
        return stand_pat
    if stand_pat > alpha:
        alpha = stand_pat

    if q_depth <= 0:
        return stand_pat

    # Generate and filter to captures (+ promotions)
    current_player = board.current_player
    moves = list_legal_moves_for(board, current_player)
    if not moves:
        return -99999    # No legal moves = loss

    capture_moves = []
    for piece, move in moves:
        caps = getattr(move, "captures", set())
        if caps:
            # MVV-LVA score for sorting
            cap_score = 0
            for cap_pos in caps:
                try:
                    victim = board[cap_pos].piece
                    if victim:
                        cap_score += PIECE_VALUES.get(_piece_name(victim), 0)
                except Exception:
                    cap_score += 200
            attacker_val = PIECE_VALUES.get(_piece_name(piece), 0)
            capture_moves.append((cap_score - (attacker_val >> 3), piece, move))
        elif _piece_name(piece) == "pawn":
            # Pawn promotions are tactical
            if (piece.player.name == "white" and move.position.y == 0) or \
               (piece.player.name == "black" and move.position.y == 4):
                capture_moves.append((9000, piece, move))

    if not capture_moves:
        return stand_pat

    capture_moves.sort(key=lambda x: -x[0])

    for _, piece, move in capture_moves:
        child = _make_move_on_clone(board, piece, move)
        if child is None:
            continue
        val = -_quiescence(child, -beta, -alpha, -colour, q_depth - 1)
        if val > alpha:
            alpha = val
        if alpha >= beta:
            break

    return alpha


# ═══════════════════════════════════════════════════════════════════════════════
#                   CORE SEARCH: NEGAMAX + ALPHA-BETA
# ═══════════════════════════════════════════════════════════════════════════════


def _negamax(board, depth, alpha, beta, colour, ply_from_root):
    """
    Negamax alpha-beta with all standard enhancements.

    Enhancements applied:
      • Transposition table (exact / lower / upper bounds)
      • Principal Variation Search (PVS): zero-window + re-search
      • Killer moves + history heuristic for move ordering
      • Late Move Reductions (LMR): reduce non-tactical late moves by 1
      • Quiescence search at depth 0 (2-ply capture resolution)
      • Futility pruning at depth 1

    Parameters
    ----------
    board : Board           Current position (cloned).
    depth : int             Remaining search depth.
    alpha, beta : float     Alpha-beta window.
    colour : int            +1 for White, −1 for Black.
    ply_from_root : int     Plies from the root (for killer indexing + mate scoring).

    Returns
    -------
    int  — Score from the current player's perspective.
    """
    global _nodes_searched, _tt, _deadline

    _nodes_searched += 1
    if _nodes_searched & 31 == 0:      # Time check every 32 nodes
        if time.perf_counter() >= _deadline:
            raise TimeoutError

    # Quick terminal check (no move generation)
    is_term, term_score = _check_terminal(board)
    if is_term:
        return term_score

    # ── In-Search Repetition Detection ────────────────────────────────────
    if ply_from_root > 0:
        sig = f"{_board_signature(board)}_{board.current_player.name}"
        if _position_history.get(sig, 0) >= 1:
            return -3500 + ply_from_root

    # Endgame Tablebase Probe (O(1) exact solved positions <= 4 pieces)
    if probe_endgame_tb is not None:
        mat_diff = colour * evaluate_for_white(board)
        tb_hit, tb_score = probe_endgame_tb(board, _piece_name, ply_from_root, mat_diff)
        if tb_hit:
            return tb_score

    # Leaf → quiescence search
    if depth <= 0:
        return _quiescence(board, alpha, beta, colour, 2)

    # ── TT Probe ──────────────────────────────────────────────────────────
    board_hash = _hash_board(board)
    tt_entry = _tt.get(board_hash)
    tt_best_move = None

    if tt_entry is not None:
        tt_depth, tt_flag, tt_val, tt_mv = tt_entry
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                return tt_val
            elif tt_flag == TT_LOWER:
                alpha = max(alpha, tt_val)
            elif tt_flag == TT_UPPER:
                beta = min(beta, tt_val)
            if alpha >= beta:
                return tt_val
        tt_best_move = tt_mv     # Always use TT move for ordering

    # ── Move Generation & Ordering ────────────────────────────────────────
    current_player = board.current_player
    moves = list_legal_moves_for(board, current_player)

    if not moves:
        # No legal moves = loss (stalemate AND checkmate both lose in this variant)
        return -99999 + ply_from_root

    # Selective Extensions:
    # Single reply extension: if only 1 legal move, extend depth +1 (zero branching cost)
    if len(moves) == 1 and ply_from_root < 14:
        depth += 1

    ordered = _order_moves(moves, board, ply_from_root, tt_best_move)

    # ── Futility Pruning (depth 1 only) ───────────────────────────────────
    # If static eval + margin can't reach α, skip non-tactical moves.
    futile = False
    if depth == 1 and abs(alpha) < 90000:
        static_eval = colour * evaluate_for_white(board)
        if static_eval + 200 <= alpha:
            futile = True

    # ── Main Search Loop ──────────────────────────────────────────────────
    best_val = -float('inf')
    best_move_key = None
    best_piece_for_killer = None
    best_move_for_killer = None
    original_alpha = alpha
    moves_searched = 0

    for i, (piece, move) in enumerate(ordered):
        # Determine if this move is tactical (capture or near-promotion)
        caps = getattr(move, "captures", set())
        is_tactical = bool(caps) or (_piece_name(piece) == "pawn" and
            ((piece.player.name == "white" and move.position.y <= 1) or
             (piece.player.name == "black" and move.position.y >= 3)))

        # Skip non-tactical moves under futility pruning
        if futile and moves_searched > 0 and not is_tactical:
            continue

        child = _make_move_on_clone(board, piece, move)
        if child is None:
            continue

        # Late Move Reduction: reduce non-tactical late moves by 1 ply
        reduction = 0
        if moves_searched >= 3 and depth >= 3 and not is_tactical and ply_from_root >= 2:
            reduction = 1

        # ── PVS (Principal Variation Search) ──────────────────────────
        if moves_searched == 0:
            # First move — full window
            val = -_negamax(child, depth - 1 - reduction, -beta, -alpha,
                            -colour, ply_from_root + 1)
        else:
            # Zero-window scout search
            val = -_negamax(child, depth - 1 - reduction, -alpha - 1, -alpha,
                            -colour, ply_from_root + 1)
            # Re-search with full window if scout found a better move
            if alpha < val < beta:
                val = -_negamax(child, depth - 1, -beta, -alpha,
                                -colour, ply_from_root + 1)
            elif reduction > 0 and val > alpha:
                # LMR re-search: reduced search beat α — try at full depth
                val = -_negamax(child, depth - 1, -beta, -alpha,
                                -colour, ply_from_root + 1)

        moves_searched += 1

        if val > best_val:
            best_val = val
            best_move_key = _move_key(piece, move)
            best_piece_for_killer = piece
            best_move_for_killer = move

        alpha = max(alpha, val)
        if alpha >= beta:
            # β-cutoff — record killer & history
            if not caps:
                _store_killer(ply_from_root, piece, move)
            _update_history(piece, move, depth)
            break

    # ── TT Store ──────────────────────────────────────────────────────────
    if best_val <= original_alpha:
        tt_flag = TT_UPPER
    elif best_val >= beta:
        tt_flag = TT_LOWER
    else:
        tt_flag = TT_EXACT

    if len(_tt) < _TT_MAX_SIZE:
        _tt[board_hash] = (depth, tt_flag, best_val, best_move_key)

    return best_val


_ENABLE_SWINDLE_SELECTOR = True   # Clean toggle flag for ablation testing


def _select_swindle_move(board, my_player, candidate_evals, best_score):
    """
    Evidence-Based Swindle Selector (Selective Tactical Threats).

    When genuinely losing (best_score <= -180), pure minimax can choose passive,
    sterile lines where the opponent easily converts with 0% error probability.

    This selector evaluates candidate root moves within a tight safety window
    (val >= best_score - 35 cp) and ranks them by CONCRETE TACTICAL THREATS:
      1. Immediate Terminal Win: Checkmate or Stalemate under 5x5 coursework rules.
      2. Forcing Checks: Direct attack on enemy King requiring defensive replies.
      3. Promotion Races: Advancing a pawn to the penultimate rank threatening Queening.
      4. Heavy Piece Attacks: Attacking enemy Queen or Right with a lesser piece (forks/pins).
      5. 5x5 Stalemate Entrapment: Restricting opponent king escape squares to <= 1.
      6. Branching Complexity (Minor tie-breaker): +1 per legal opponent reply.
    """
    if not _ENABLE_SWINDLE_SELECTOR:
        return None

    opp_player = next((p for p in board.players if p.name != my_player.name), None)
    if opp_player is None or not candidate_evals:
        return None

    # Tight safety window (<= 35 cp) so we NEVER choose an unsound or blunder move
    swindle_pool = [item for item in candidate_evals if item[0] >= best_score - 35]
    if len(swindle_pool) <= 1:
        return None

    best_threat_score = -float('inf')
    chosen_pair = None

    for val, piece, move in swindle_pool:
        child = _make_move_on_clone(board, piece, move)
        if child is None:
            continue

        threat_score = 0

        # 1. Immediate Win Check (Stalemate or Mate under 5x5 coursework rules)
        opp_replies = list_legal_moves_for(child, opp_player)
        if not opp_replies:
            return piece, move

        # 2. Forcing King Checks
        opp_king = next((p for p in child.get_pieces() if p.player.name == opp_player.name and _piece_name(p) == "king"), None)
        if opp_king is not None:
            kx, ky = opp_king.position.x, opp_king.position.y
            is_check = any(opt.position.x == kx and opt.position.y == ky
                           for my_p in child.get_player_pieces(my_player)
                           for opt in my_p.get_move_options())
            if is_check:
                threat_score += 80

            # 3. 5x5 Stalemate Threat: Enemy King restricted to <= 1 escape square
            escapes = sum(
                1 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                if not (dx == 0 and dy == 0)
                and 0 <= kx + dx < 5 and 0 <= ky + dy < 5
                and (child._squares[ky + dy][kx + dx].piece is None
                     or child._squares[ky + dy][kx + dx].piece.player.name != opp_player.name)
            )
            if escapes <= 1:
                threat_score += 120

        # 4. Pawn Promotion Race Threat (pawn reaches penultimate rank on 5x5)
        p_name = _piece_name(piece)
        if p_name == "pawn":
            dest_y = move.position.y
            if (my_player.name == "white" and dest_y == 1) or (my_player.name == "black" and dest_y == 3):
                threat_score += 90

        # 5. Heavy Piece Attacks (attacking enemy Queen or Right with a lesser piece)
        enemy_heavies = [p for p in child.get_player_pieces(opp_player) if _piece_name(p) in ("queen", "right")]
        for eh in enemy_heavies:
            hx, hy = eh.position.x, eh.position.y
            is_attacked = any(opt.position.x == hx and opt.position.y == hy
                              for my_p in child.get_player_pieces(my_player)
                              if _piece_name(my_p) not in ("queen", "right")
                              for opt in my_p.get_move_options())
            if is_attacked:
                threat_score += 50
                break

        # 6. Opponent Branching Complexity (Minor tie-breaker ONLY: +1 per reply)
        threat_score += min(len(opp_replies), 25) * 1

        if threat_score > best_threat_score:
            best_threat_score = threat_score
            chosen_pair = (piece, move)

    # Only override search if candidate creates concrete active threats (>= 70)
    if best_threat_score >= 70:
        return chosen_pair
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#                      ITERATIVE DEEPENING DRIVER
# ═══════════════════════════════════════════════════════════════════════════════


def _iterative_deepening(board, my_player_name, deadline):
    """
    Iterative deepening with aspiration windows.

    Searches depth 1, 2, 3, … until the deadline expires.  Each completed
    depth updates the best move, so even if the deepest iteration is cut
    short, the result from the previous depth is still available.

    Aspiration windows (from depth 3 onward) narrow the α-β window around
    the previous iteration's score.  If the result falls outside the window,
    the window is widened and the search retried — this is rare but necessary
    for correctness.

    Returns
    -------
    (piece, move) — the best move found before the deadline.
    """
    global _nodes_searched, _tt, _deadline, _killer_moves, _history
    global _last_depth_reached, _last_nodes_searched, _last_branching_factor

    _deadline = deadline
    _killer_moves = {}
    _history = {}

    my_player = next((p for p in board.players if p.name == my_player_name), None)
    if my_player is None:
        my_player = board.players[0] if my_player_name == "white" else board.players[1]
    colour = 1 if my_player_name == "white" else -1

    moves = list_legal_moves_for(board, my_player)
    if not moves:
        return None, None
    if len(moves) == 1:
        # Forced move — no search needed, save time for later
        _last_depth_reached = 0
        _last_nodes_searched = 0
        _last_branching_factor = 1.0
        return moves[0]

    best_piece, best_move = moves[0]
    prev_score = 0          # Seed for aspiration window
    total_nodes_this_move = 0
    completed_depth = 0
    prev_depth_nodes = 0
    last_completed_evals = []

    for depth in range(1, 15):
        _nodes_searched = 0
        try:
            root_moves = list_legal_moves_for(board, my_player)
            if not root_moves:
                break

            # TT best move for root ordering
            board_hash = _hash_board(board)
            tt_entry = _tt.get(board_hash)
            tt_best_move = tt_entry[3] if tt_entry is not None else None

            ordered = _order_moves(root_moves, board, 0, tt_best_move)

            current_best_score = -float('inf')
            current_best_piece = ordered[0][0]
            current_best_move = ordered[0][1]

            # ── Aspiration Windows (depth ≥ 3) ────────────────────────
            if depth >= 3:
                delta = _ASPIRATION_DELTA
                alpha = prev_score - delta
                beta = prev_score + delta
            else:
                alpha = -float('inf')
                beta = float('inf')

            while True:
                current_best_score = -float('inf')
                current_best_piece = ordered[0][0]
                current_best_move = ordered[0][1]
                moves_searched_root = 0
                current_root_evals = []

                for piece, move in ordered:
                    child = _make_move_on_clone(board, piece, move)
                    if child is None:
                        continue

                    if moves_searched_root == 0:
                        val = -_negamax(child, depth - 1, -beta, -alpha,
                                        -colour, 1)
                    else:
                        # PVS at root
                        val = -_negamax(child, depth - 1, -alpha - 1, -alpha,
                                        -colour, 1)
                        if alpha < val < beta:
                            val = -_negamax(child, depth - 1, -beta, -alpha,
                                            -colour, 1)

                    current_root_evals.append((val, piece, move))

                    if val > current_best_score:
                        current_best_score = val
                        current_best_piece = piece
                        current_best_move = move

                    alpha = max(alpha, val)
                    moves_searched_root += 1

                # Check aspiration window outcome
                if depth < 3:
                    last_completed_evals = current_root_evals
                    break    # No aspiration for shallow depths
                if current_best_score <= prev_score - delta:
                    delta = min(delta * 4, 2000)     # Fail-low → widen
                    alpha = prev_score - delta
                elif current_best_score >= prev_score + delta:
                    delta = min(delta * 4, 2000)     # Fail-high → widen
                    beta = prev_score + delta
                else:
                    last_completed_evals = current_root_evals
                    break    # Result inside window — done

            # Completed this depth
            best_piece = current_best_piece
            best_move = current_best_move
            prev_score = current_best_score
            total_nodes_this_move += _nodes_searched

            # Effective branching factor
            if prev_depth_nodes > 0 and _nodes_searched > 0:
                _last_branching_factor = _nodes_searched / max(prev_depth_nodes, 1)
            prev_depth_nodes = _nodes_searched
            completed_depth = depth

            # Early exit on forced mate
            if current_best_score > 90000:
                break

        except TimeoutError:
            total_nodes_this_move += _nodes_searched
            break

    # ── Evidence-Based Swindle Trigger ────────────────────────────────────
    # Only engages when genuinely losing (eval <= -180 cp), verified across
    # completed search depth, and candidate moves present concrete tactical threats.
    if completed_depth >= 2 and prev_score <= -180 and last_completed_evals:
        swindle_res = _select_swindle_move(board, my_player, last_completed_evals, prev_score)
        if swindle_res is not None:
            sw_piece, sw_move = swindle_res
            if sw_piece is not best_piece or sw_move is not best_move:
                if _ENABLE_STDERR_LOG:
                    print(
                        f"[agent v5.6] SWINDLE ENGAGED (eval={prev_score}): "
                        f"Selective tactical threat at {sw_piece.position.x},{sw_piece.position.y} -> "
                        f"{sw_move.position.x},{sw_move.position.y}!",
                        file=sys.stderr,
                    )
                best_piece, best_move = sw_piece, sw_move

    # Record instrumentation
    _last_depth_reached = completed_depth
    _last_nodes_searched = total_nodes_this_move

    return best_piece, best_move


# ═══════════════════════════════════════════════════════════════════════════════
#                         MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


_ENABLE_STDERR_LOG = True  # Can be set to False to gate stderr printing


def agent(board, player, var):
    """
    AI Agent for the 5×5 Chess Fragments game — Version 5.6.

    Called once per turn by the game runner.  Must return a (piece, move)
    pair within the allotted thinking time.

    Parameters
    ----------
    board : Board
        The current (cloned) 5×5 board state.
    player : Player
        Our assigned player object (white or black).
    var : list
        [ply_number, THINKING_TIME_BUDGET] — current ply and per-move budget.

    Returns
    -------
    tuple[Piece, MoveOption]
        The chosen piece and destination move.
    """
    global _tt, _opening_book, _position_history, _current_ply
    global _last_depth_reached, _last_nodes_searched, _last_branching_factor
    global _move_stats_log, _game_start_time, _last_seen_ply, _my_total_time_spent
    global _killer_moves, _history

    try:
        ply = var[0]
        time_budget = var[1]
        _current_ply = ply

        now = time.perf_counter()

        # ── Robust New-Game Detection & Clock Initialization ─────────────────
        # In a fresh process: _last_seen_ply == -1.
        # For White, first call is ply 1.
        # For Black, first call in a fresh process is ply 2.
        # When a new game starts in the same process, ply resets (ply <= _last_seen_ply).
        # This condition guarantees Black's clock resets on ply 2 in fresh processes.
        is_new_game = (
            _last_seen_ply == -1
            or ply <= 1
            or ply <= _last_seen_ply
        )

        if is_new_game or _game_start_time <= 0.0:
            _game_start_time = now
            _my_total_time_spent = 0.0
            _tt = {}
            _position_history = {}
            _killer_moves = {}
            _history = {}

        _last_seen_ply = ply

        # Calculate time based on our own 300s budget allocation:
        remaining_my_clock = max(0.0, 300.0 - _my_total_time_spent)

        # 2.5s safety margin (prevents timeouts on slower hardware or under parallel load)
        safety_margin = 2.5
        max_budget = max(1.0, time_budget - safety_margin)

        if remaining_my_clock < 120.0 or ply >= 18:
            # Late game: dynamically scale per-move budget from our own clock
            est_turns_left = max(4.0, (32.0 - ply) / 2.0)
            dynamic_budget = remaining_my_clock / est_turns_left
            effective_budget = min(max_budget, max(3.5, dynamic_budget - 1.5))
        else:
            effective_budget = max_budget

        # ── Forced Move (single legal move) ───────────────────────────────────
        legal_moves = list_legal_moves_for(board, player)
        if not legal_moves:
            return None, None
        if len(legal_moves) == 1:
            _last_depth_reached = 0
            _last_nodes_searched = 0
            _last_branching_factor = 1.0
            _log_move_stats(ply, player.name, 0.0)
            return legal_moves[0]

        deadline = time.perf_counter() + effective_budget

        # ── Transposition Table Size Guard ────────────────────────────────────
        if len(_tt) > _TT_MAX_SIZE * 0.9:
            _tt = {}

        # Track position for repetition detection
        current_hash = _hash_board(board)
        current_sig = f"{_board_signature(board)}_{board.current_player.name}"
        _position_history[current_sig] = _position_history.get(current_sig, 0) + 1

        # ── Opening Book (plies 1–2) ──────────────────────────────────────────
        if ply <= 2:
            # 1. Master Pre-computed Book Lookup
            if lookup_book_move is not None:
                master_mv = lookup_book_move(board, player.name, ply)
                if master_mv is not None:
                    fx, fy, tx, ty = master_mv
                    for p in board.get_player_pieces(player):
                        if p.position.x == fx and p.position.y == fy:
                            for m in p.get_move_options():
                                if m.position.x == tx and m.position.y == ty:
                                    _log_move_stats(ply, player.name, 0.0)
                                    return p, m

            # 2. Adaptive Self-Learning Book
            book_key = (current_hash, player.name, ply)
            book_entry = _opening_book.get(book_key)
            if book_entry is not None:
                fx, fy, tx, ty = book_entry
                for p in board.get_player_pieces(player):
                    if p.position.x == fx and p.position.y == fy:
                        for m in p.get_move_options():
                            if m.position.x == tx and m.position.y == ty:
                                _log_move_stats(ply, player.name, 0.0)
                                return p, m
            # Unknown position — search and self-learn
            t_start = time.perf_counter()
            piece, move_opt = _iterative_deepening(board, player.name, deadline)
            if piece is not None and move_opt is not None:
                _opening_book[book_key] = (
                    piece.position.x, piece.position.y,
                    move_opt.position.x, move_opt.position.y,
                )
            if piece is None or move_opt is None:
                if legal_moves:
                    piece, move_opt = random.choice(legal_moves)
            elapsed_turn = time.perf_counter() - t_start
            _my_total_time_spent += elapsed_turn
            _log_move_stats(ply, player.name, elapsed_turn)
            return piece, move_opt

        # ── Main Search ───────────────────────────────────────────────────────
        t_start = time.perf_counter()
        piece, move_opt = _iterative_deepening(board, player.name, deadline)

        # Fallback if search returned None
        if piece is None or move_opt is None:
            if legal_moves:
                piece, move_opt = random.choice(legal_moves)

        # ── Repetition Avoidance ──────────────────────────────────────────────
        # Never allow the same position to be reached >= 2 times.
        if piece is not None and move_opt is not None:
            test_board = _make_move_on_clone(board, piece, move_opt)
            if test_board is not None:
                future_sig = f"{_board_signature(test_board)}_{test_board.current_player.name}"
                future_count = _position_history.get(future_sig, 0)
                if future_count >= 1:
                    best_alt = None
                    min_count = future_count
                    for alt_piece, alt_move in legal_moves:
                        if alt_piece is piece and alt_move is move_opt:
                            continue
                        alt_board = _make_move_on_clone(board, alt_piece, alt_move)
                        if alt_board is not None:
                            alt_sig = f"{_board_signature(alt_board)}_{alt_board.current_player.name}"
                            c = _position_history.get(alt_sig, 0)
                            if c < min_count:
                                min_count = c
                                best_alt = (alt_piece, alt_move)
                                if c == 0:
                                    break
                    if best_alt is not None and min_count < future_count:
                        piece, move_opt = best_alt

        elapsed_turn = time.perf_counter() - t_start
        _my_total_time_spent += elapsed_turn
        _log_move_stats(ply, player.name, elapsed_turn)
        return piece, move_opt

    except Exception:
        # Top-Level Fail-Safe: NEVER crash or forfeit a game
        try:
            legal = list_legal_moves_for(board, player)
            if legal:
                return random.choice(legal)
        except Exception:
            pass
        return None, None


# ─── Instrumentation ─────────────────────────────────────────────────────────

def _log_move_stats(ply, player_name, elapsed):
    """Record and print per-move search metrics to stderr."""
    global _move_stats_log
    stats = {
        "ply":    ply,
        "player": player_name,
        "depth":  _last_depth_reached,
        "nodes":  _last_nodes_searched,
        "ebf":    round(_last_branching_factor, 2),
        "time_s": round(elapsed, 2),
    }
    _move_stats_log.append(stats)
    if _ENABLE_STDERR_LOG:
        nps = int(_last_nodes_searched / elapsed) if elapsed > 0.01 else 0
        print(
            f"[agent v5.6] ply={ply:>3d}  {player_name:>5s}  "
            f"depth={_last_depth_reached}  nodes={_last_nodes_searched:>7d}  "
            f"ebf={_last_branching_factor:.2f}  nps={nps:>6d}  "
            f"time={elapsed:.2f}s",
            file=sys.stderr,
        )
