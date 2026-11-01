# ═══════════════════════════════════════════════════════════════════════════════
# agent_v75_endgame_depth.py — Chess Fragments AI Agent (v7.5 Endgame Depth candidate)
# COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces
#
# EXPERIMENTAL: v7.4 tactical guards plus integrated 65-configuration retrograde
# probing, tighter deadline enforcement, aged cross-turn history, and conservative
# late-move reduction tuning. v6.9/v7.3 remain frozen pending paired H2H tests.
#
# Architecture at a Glance:
#   • Iterative Deepening Negamax with Alpha-Beta Pruning
#   • Principal Variation Search (PVS) with zero-window re-search
#   • Aspiration Windows (±250 cp, auto-widens on fail)
#   • Transposition Table (200 k entries, coordinate-keyed moves)
#   • Tactical move ordering: PV > MVV-LVA > Promotion > Quiet Check > Killers > History
#   • Side- and piece-aware killer/history keys (no cross-colour heuristic aliasing)
#   • Late Move Reductions (LMR) for non-tactical late moves
#   • Quiescence Search (captures/promotions + bounded check evasions)
#   • Frontier Futility Pruning at depth 1
#   • Anti-Stalemate King Mobility Gradient (stalemate = loss)
#   • Promotion-race evaluation and safety-weighted piece mobility
#   • Turn-aware exchange liability and endgame mating drive
#   • Own-clock budgeting for the 300 s per-player limit
#   • Self-Learning Opening Book (plies 1–2)
#   • Repetition Avoidance (prevents fivefold-repetition draws)
#   • Check extensions disabled by default; existing low-mobility extensions retained
#   • Root PUCT/MCTS probe retained for experiments but disabled by default
#   • Dynamic 0/1/2-ply LMR with tactical, killer and history safeguards
#   • Aged cross-turn history ordering, reset only at new-game boundaries
#   • Root and node deadline checks with completed-iteration fallback
#   • Bounded LRU transposition table (no wholesale flush at 90% capacity)
#   • Directional aspiration-window widening
#   • Optional reproducible root tie-breaking (disabled by default)
#   • Tactical quiet-check quiescence alongside captures (strictly bounded)
#   • Deterministic fail-safe move selection
#   • Retrograde WDL probing at every covered ≤4-piece search node
#   • Per-move instrumentation logged to stderr
#
# Constraints:
#   Single-file agent — no external dependencies beyond Python built-ins,
#   the chessmaker library, and the provided board_utils helper.
# ═══════════════════════════════════════════════════════════════════════════════

import time
import sys
import math
import random
from collections import OrderedDict
from extension.board_utils import list_legal_moves_for

# The retrograde data is a companion module (≈4.7 MB source).  Keep the agent
# operational if a deployment omits it, but expose availability in diagnostics.
try:
    from endgame_tablebase import probe_endgame_tb as _probe_endgame_tb
    from endgame_tablebase import is_tablebase_loaded as _is_tablebase_loaded
    _TABLEBASE_READY = bool(_is_tablebase_loaded())
except Exception:
    _probe_endgame_tb = None
    _is_tablebase_loaded = None
    _TABLEBASE_READY = False


# ─── Python Compatibility ─────────────────────────────────────────────────────
# chessmaker uses @classmethod @property for piece.name, which was deprecated
# in Python 3.11 and broken entirely in 3.13 (returns a raw property object).
# Reading the class name via type().__name__ is portable across 3.9–3.13+.
# ──────────────────────────────────────────────────────────────────────────────

def _piece_name(piece):
    """Return a canonical piece name across built-in and custom piece classes.

    The supplied board uses the custom ``Pawn_Q`` type.  Without normalising
    that class name, its material/PST/promotion heuristics silently miss the
    pawn entry in the tables.
    """
    name = type(piece).__name__.lower()
    if name in {"pawn_q", "pawnq", "pawn-promotion", "promotingpawn"}:
        return "pawn"
    # Be tolerant of other custom pawn implementations, e.g. Pawn_Queen.
    if name.startswith("pawn_"):
        return "pawn"
    return name


# ─── Material Values ──────────────────────────────────────────────────────────
# Tuned for the 5×5 "Chess Fragments" board.  Standard chess values are the
# baseline, adjusted for compact geometry:
#   • Knight +20 (fork density is higher on 5×5)
#   • Right = Knight + Rook hybrid, valued at 700 on the compact board
#   • King  = 20 000 (must dominate all material comparisons)
# ──────────────────────────────────────────────────────────────────────────────

PIECE_VALUES = {
    "pawn":   100,
    "knight": 320,
    "bishop": 330,
    "right":  700,    # Rook + jumping Knight hybrid; especially powerful on 5×5
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
MATE_SCORE = 99_999
MATE_THRESHOLD = 90_000


def _score_to_tt(score, ply_from_root):
    """Normalize mate-distance scores before storing them in the TT."""
    if score > MATE_THRESHOLD:
        return score + ply_from_root
    if score < -MATE_THRESHOLD:
        return score - ply_from_root
    return score


def _score_from_tt(score, ply_from_root):
    """Restore a TT mate-distance score for the current search ply."""
    if score > MATE_THRESHOLD:
        return score - ply_from_root
    if score < -MATE_THRESHOLD:
        return score + ply_from_root
    return score

_tt = OrderedDict()
_TT_MAX_SIZE = 200_000


# ─── Self-Learning Opening Book ──────────────────────────────────────────────
# On the first encounter with a board position at ply 1 or 2, the agent runs
# a full search and caches the result.  On subsequent encounters (e.g. in a
# multi-game tournament session), the cached move is returned in ≈ 0 ms,
# saving the entire 12 s thinking budget.  No disk I/O — stays within the
# single-file coursework constraint.
# ──────────────────────────────────────────────────────────────────────────────

# ─── Verified static opening book (coordinate-keyed) ───────────────────────────
# v6.6 carried a self-learning in-memory cache but never consulted the supplied
# opening_book.py table. That left known black-side bait-pawn traps unprotected.
# Embed only the two defensive replies that correspond to the measured v6.6 losses. Do not override other openings.
_SELECTIVE_OPENING_RAW = {'nqkbrppppp....PPPPP.RBKQN_black_2': (3, 1, 3, 2), 'rbkqnpppppP.....PPPPNQKBR_black_2': (1, 1, 1, 2)}
_OPENING_SYMBOL_TO_NAME = {"p": "pawn", "n": "knight", "b": "bishop",
                          "r": "right", "q": "queen", "k": "king"}

def _decode_static_opening_key(raw_key):
    board_text, side_to_move, ply_text = raw_key.rsplit("_", 2)
    if len(board_text) != 25:
        return None
    pieces = []
    for i, ch in enumerate(board_text):
        if ch == ".":
            continue
        name = _OPENING_SYMBOL_TO_NAME.get(ch.lower())
        if name is None:
            return None
        pieces.append((name, "white" if ch.isupper() else "black", i % 5, i // 5))
    return (tuple(sorted(pieces)), side_to_move, int(ply_text))

_STATIC_OPENINGS = {
    decoded: move for raw, move in _SELECTIVE_OPENING_RAW.items()
    for decoded in (_decode_static_opening_key(raw),) if decoded is not None
}

def _opening_position_key(board, player_name, ply):
    pieces = tuple(sorted((_piece_name(p), p.player.name, p.position.x, p.position.y)
                          for p in board.get_pieces()))
    return (pieces, player_name, int(ply))

def _lookup_static_opening(board, player_name, ply):
    if ply not in (1, 2):
        return None
    return _STATIC_OPENINGS.get(_opening_position_key(board, player_name, ply))


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

_killer_moves = {}   # (side, piece_type, ply) → [coordinate move keys]
_history = {}        # (side, piece_type, from/to) → bounded cutoff score


# ─── Global Search State ──────────────────────────────────────────────────────

_nodes_searched = 0
_deadline = 0.0
_ASPIRATION_DELTA = 250    # Initial aspiration-window half-width (centipawns)

# PUCT remains available in the source for controlled research, but it is
# DISABLED in the v7.4 candidate. The 200-game v6.9-v7.1 comparison was run
# with PUCT off, and the earlier PUCT-on pilot did not justify its cost.
# Do not enable this in a promotion candidate without a separate ablation.
_ENABLE_ROOT_PUCT = False
_ENABLE_CHECK_EXTENSION = False  # Re-enable only in a measured ablation.
_ENABLE_QUIET_CHECK_ORDERING = True
_CHECK_EXTENSION_MAX_PLY = 10
# Controlled experiments: deterministic search is the default.
_ENABLE_ROOT_RANDOM_TIEBREAK = False
_ROOT_TIE_WINDOW_CP = 8
_ROOT_RANDOM_SEED = 730_073
# Search diagnostics reset once per move.
_last_tt_hits = 0
_last_tt_cutoffs = 0
_last_lmr_one_ply = 0
_last_lmr_two_ply = 0
_last_aspiration_fail_low = 0
_last_aspiration_fail_high = 0
_last_random_tiebreak = False
_PUCT_MAX_SIMULATIONS = 28
_PUCT_MAX_DEPTH = 4              # Includes the candidate root move.
_PUCT_MAX_CANDIDATES = 4
_PUCT_SCORE_WINDOW = 180          # Centipawns from the best completed root score.
_PUCT_MIN_ENTROPY = 0.38
_PUCT_C = 1.15
_PUCT_MAX_TIME = 0.18             # Hard wall-clock allowance per move.


# ─── Per-Move Instrumentation ─────────────────────────────────────────────────

_last_depth_reached = 0
_last_nodes_searched = 0
_last_branching_factor = 0.0
_last_iteration_trace = []
_last_aborted_depth = 0
_last_aborted_nodes = 0
_last_check_extensions = 0
_last_mobility_extensions = 0
_move_stats_log = []       # One dict per agent() call
_last_puct_stats = {"used": False, "simulations": 0, "elapsed_s": 0.0}
_last_material_guard_triggered = False
_last_material_guard_loss = 0
_last_material_guard_replacement = False
_last_promotion_guard_triggered = False
_last_promotion_guard_replacement = False
_last_tb_probes = 0
_last_tb_hits = 0
_last_tb_wins = 0
_last_tb_losses = 0
_last_tb_draws = 0


# ─── Repetition Tracking ─────────────────────────────────────────────────────

_position_history = {}     # board_hash → count of times reached


# ─── Game-Phase & Clock Tracking ──────────────────────────────────────────────

_game_start_time = 0.0     # Kept for diagnostics / reset detection
_last_seen_ply = -1        # Detects new-game resets
_own_clock_used = 0.0      # Seconds actually spent by this agent (not wall time)
_own_moves_seen = 0        # Number of this agent's completed turns in the current game


# ─── Pawn Advance Bonuses ─────────────────────────────────────────────────────
# Static and colour-symmetric: the same board position must evaluate the same
# way regardless of when it is reached, so transposition-table values stay valid.

_PAWN_ADVANCE_BONUS_WHITE = [0, 60, 30, 10, 0]   # row y for White
_PAWN_ADVANCE_BONUS_BLACK = [0, 10, 30, 60, 0]   # row y for Black


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


def _check_terminal(board, ply_from_root=0):
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
        score = (-MATE_SCORE + ply_from_root if board.current_player.name == "white"
                 else MATE_SCORE - ply_from_root)
        return True, score
    if black_king is None:
        score = (-MATE_SCORE + ply_from_root if board.current_player.name == "black"
                 else MATE_SCORE - ply_from_root)
        return True, score
    if piece_count == 2:
        return True, 0   # Only two kings — automatic draw

    return False, 0


_SIG_SYMS = {'pawn': 'p', 'knight': 'n', 'bishop': 'b', 'right': 'r', 'queen': 'q', 'king': 'k'}

def _board_signature(board):
    """Return a deterministic position signature, including side-to-move."""
    chars = []
    for row in board._squares:
        for sq in row:
            p = sq.piece
            if p is None:
                chars.append('.')
            else:
                c = _SIG_SYMS.get(_piece_name(p), '?')
                chars.append(c.upper() if p.player.name == 'white' else c)
    # Identical piece placements with different players to move are not the
    # same chess position for repetition purposes.
    side = 'w' if board.current_player.name == 'white' else 'b'
    return side + ''.join(chars)


def _make_move_on_clone(board, piece, move):
    """
    Clone the board and execute the given move on the clone.

    Returns the resulting Board, or None if the move couldn't be applied
    (e.g. piece was captured in the cloning gap — shouldn't happen in
    normal play, but defensive coding prevents crashes).
    """
    child = board.clone()
    try:
        # Fast path: ChessMaker's Board supports square lookup with a Position.
        # This avoids scanning every piece on every search edge. Keep the old
        # scan as a compatibility fallback for alternate Board implementations.
        child_piece = None
        try:
            square = child[piece.position]
            candidate = getattr(square, "piece", None)
            if (candidate is not None and type(candidate) is type(piece)
                    and candidate.player.name == piece.player.name):
                child_piece = candidate
        except Exception:
            child_piece = None
        if child_piece is None:
            for cp in child.get_player_pieces(piece.player):
                if (type(cp) is type(piece) and cp.position == piece.position
                        and cp.player.name == piece.player.name):
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


# ═══════════════════════════════════════════════════════════════════════════════
#                          EVALUATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


# Compact-board geometry used by the evaluator.  This is a *pseudo-attack* map:
# it intentionally records defended occupied squares too, and does not attempt
# to solve pins.  Search remains responsible for legality and tactical proof.
_EVAL_KNIGHT_STEPS = ((1, 2), (2, 1), (2, -1), (1, -2),
                      (-1, -2), (-2, -1), (-2, 1), (-1, 2))
_EVAL_ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
_EVAL_DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
_EVAL_KING_STEPS = _EVAL_ORTHOGONAL + _EVAL_DIAGONAL
_EVAL_PHASE_MAX = 18  # Starting set: 2 queens*4 + 2 Rights*3 + 4 minors*1


def _inside5(x, y):
    return 0 <= x < 5 and 0 <= y < 5


def _build_evaluation_maps(piece_rows, occupancy):
    """Build 5x5 attack maps and practical mobility estimates.

    Each piece contributes pseudo-attacks (including defended friendly squares),
    a cheapest-attacker value, ordinary reachable-square mobility, and a
    safety-weighted mobility estimate.  These maps intentionally do not replace
    legal move generation; search remains responsible for pins and legality.
    """
    attacks = {1: [[0] * 5 for _ in range(5)],
               -1: [[0] * 5 for _ in range(5)]}
    cheapest = {1: [[10**9] * 5 for _ in range(5)],
                -1: [[10**9] * 5 for _ in range(5)]}
    mobility = {1: 0, -1: 0}
    candidate_targets = {1: [], -1: []}

    def mark(side, attacker_value, x, y):
        attacks[side][y][x] += 1
        if attacker_value < cheapest[side][y][x]:
            cheapest[side][y][x] = attacker_value

    def record_target(side, x, y):
        candidate_targets[side].append((x, y))

    for name, x, y, side, value in piece_rows:
        if name == "pawn":
            dy = -1 if side == 1 else 1
            # A pawn attacks diagonally even when the square is empty.
            for dx in (-1, 1):
                nx, ny = x + dx, y + dy
                if _inside5(nx, ny):
                    mark(side, value, nx, ny)
                    target = occupancy[ny][nx]
                    if target is not None and target[3] != side:
                        mobility[side] += 1
                        record_target(side, nx, ny)
            ny = y + dy
            if _inside5(x, ny) and occupancy[ny][x] is None:
                mobility[side] += 1
                record_target(side, x, ny)
                start_rank = 3 if side == 1 else 1
                ny2 = y + 2 * dy
                if y == start_rank and _inside5(x, ny2) and occupancy[ny2][x] is None:
                    mobility[side] += 1
                    record_target(side, x, ny2)
            continue

        if name == "knight":
            directions = _EVAL_KNIGHT_STEPS
        elif name == "king":
            directions = _EVAL_KING_STEPS
        elif name == "bishop":
            directions = _EVAL_DIAGONAL
        elif name == "right":
            directions = _EVAL_ORTHOGONAL + _EVAL_KNIGHT_STEPS
        elif name == "queen":
            directions = _EVAL_ORTHOGONAL + _EVAL_DIAGONAL
        else:
            directions = ()

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            sliding = name in ("bishop", "right", "queen") and (dx, dy) not in _EVAL_KNIGHT_STEPS
            while _inside5(nx, ny):
                mark(side, value, nx, ny)
                target = occupancy[ny][nx]
                if target is None or target[3] != side:
                    mobility[side] += 1
                    record_target(side, nx, ny)
                if target is not None or not sliding:
                    break
                nx += dx
                ny += dy

    # Safe mobility matters especially on a 5x5 board: central activity can be
    # powerful, but moving a major piece onto a square attacked by a cheaper
    # enemy often creates immediate tactical trouble. Supported attacked squares
    # retain partial credit, since defended outposts and exchanges can be good.
    safe_mobility = {1: 0.0, -1: 0.0}
    for side in (1, -1):
        for x, y in candidate_targets[side]:
            enemy_pressure = attacks[-side][y][x]
            friendly_support = attacks[side][y][x]
            if enemy_pressure == 0:
                safe_mobility[side] += 1.0
            elif friendly_support >= enemy_pressure:
                safe_mobility[side] += 0.45
            elif friendly_support > 0:
                safe_mobility[side] += 0.20

    return attacks, cheapest, mobility, safe_mobility


def _mobility_crisis_penalty(move_count, is_side_to_move, phase):
    """Bounded penalty for a side with dangerously few pseudo-legal options.

    On this 5x5 variant, stalemate is a loss. Low mobility is therefore a more
    urgent strategic weakness than in ordinary chess. Exact terminal detection
    remains the search's responsibility; this smooth score penalises positions
    that are approaching a mobility collapse.
    """
    base = {0: 220, 1: 145, 2: 82, 3: 40, 4: 16}.get(move_count, 0)
    if base == 0:
        return 0
    if phase > 12:
        base = int(base * 0.70)
    if not is_side_to_move:
        base = int(base * 0.60)
    return base


def evaluate_for_white(board):
    """Evaluate a 5×5 Chess Fragments position from White's perspective.

    v7.2 deliberately retains the complete v7.1 evaluation weights and feature
    terms. The current evaluator is a strong handcrafted baseline, but its
    pseudo-attack and exchange-liability estimates are not yet empirically
    calibrated well enough to justify another unmeasured weight rewrite.

    The design borrows *principles*, not copied engine code: compact, tuned
    features; tapered king activity; attack/defence awareness; and explicit
    king-safety / winning-conversion terms.  It remains fast enough to call at
    search leaves under the coursework's 300-second per-player clock.

    Terms: material, piece-square placement, phase-aware king activity, pawn
    structure and promotion races, raw/safety-weighted mobility, central control,
    turn-aware tactical exposure, king danger, mating drive, and conversion.
    Search proves tactics and terminal wins; this function estimates nonterminal
    positions and deliberately never treats a draw as a win.
    """
    pieces = []
    occupancy = [[None] * 5 for _ in range(5)]
    white_king = black_king = None
    white_pawns = []
    black_pawns = []
    white_material = black_material = 0
    phase = 0
    score = 0

    phase_units = {"queen": 4, "right": 3, "rook": 3,
                   "bishop": 1, "knight": 1}

    # One board pass: make the evaluator independent of expensive clones and
    # collect the data used by all later terms.
    for piece in board.get_pieces():
        name = _piece_name(piece)
        x, y = piece.position.x, piece.position.y
        side = 1 if piece.player.name == "white" else -1
        value = PIECE_VALUES.get(name, 0)
        row = (name, x, y, side, value)
        pieces.append(row)
        occupancy[y][x] = row

        if name == "king":
            if side == 1:
                white_king = (x, y)
            else:
                black_king = (x, y)
            continue

        phase += phase_units.get(name, 0)
        if side == 1:
            white_material += value
        else:
            black_material += value

        pst = PST_MAP.get(name)
        pst_bonus = pst[y][x] if side == 1 and pst else (
            pst[4 - y][x] if side == -1 and pst else 0)
        score += side * (value + pst_bonus)

        if name == "pawn":
            (white_pawns if side == 1 else black_pawns).append((x, y))

    attacks, cheapest_attacker, mobility, safe_mobility = _build_evaluation_maps(pieces, occupancy)

    # ── Tapered king placement ─────────────────────────────────────────────
    # Start set has 18 phase units. As queens, Rights and minor pieces vanish,
    # the king gradually changes from cautious shelter-seeker to active fighter.
    phase = min(_EVAL_PHASE_MAX, phase)
    if white_king:
        x, y = white_king
        mid = PST_KING_MID[y][x]
        end = PST_KING_END[y][x]
        score += (mid * phase + end * (_EVAL_PHASE_MAX - phase)) // _EVAL_PHASE_MAX
    if black_king:
        x, y = black_king
        mid = PST_KING_MID[4 - y][x]
        end = PST_KING_END[4 - y][x]
        score -= (mid * phase + end * (_EVAL_PHASE_MAX - phase)) // _EVAL_PHASE_MAX

    # ── King tropism: bring attackers toward the opposing king ─────────────
    # Weight heavier pieces more than minors; the smaller board makes a one-
    # square reduction in distance strategically meaningful.
    heavy_tropism = 9 if phase <= 7 else 6
    minor_tropism = 5 if phase <= 7 else 3
    if black_king:
        kx, ky = black_king
        for name, x, y, side, _ in pieces:
            if side != 1 or name in ("pawn", "king"):
                continue
            distance = abs(x - kx) + abs(y - ky)
            weight = heavy_tropism if name in ("queen", "right") else minor_tropism
            score += max(0, 4 - distance) * weight
    if white_king:
        kx, ky = white_king
        for name, x, y, side, _ in pieces:
            if side != -1 or name in ("pawn", "king"):
                continue
            distance = abs(x - kx) + abs(y - ky)
            weight = heavy_tropism if name in ("queen", "right") else minor_tropism
            score -= max(0, 4 - distance) * weight

    # ── Pawn structure, passed pawns and promotion race ────────────────────
    # A passed pawn has no opposing pawn on its file or adjacent files ahead
    # of it. Promotion is disproportionately important on a five-rank board.
    for side, pawns, enemy_pawns in (
        (1, white_pawns, black_pawns), (-1, black_pawns, white_pawns)):
        file_count = [0] * 5
        for x, y in pawns:
            file_count[x] += 1
            progress = 4 - y if side == 1 else y
            score += side * (_PAWN_ADVANCE_BONUS_WHITE[y] if side == 1
                             else _PAWN_ADVANCE_BONUS_BLACK[y])

            adjacent_file_support = any(abs(ox - x) == 1 for ox, _ in pawns)
            if not adjacent_file_support:
                score -= side * 12  # isolated pawn

            blocked_files = False
            for ex, ey in enemy_pawns:
                if abs(ex - x) > 1:
                    continue
                if (side == 1 and ey < y) or (side == -1 and ey > y):
                    blocked_files = True
                    break
            if not blocked_files:
                score += side * (18 + 11 * progress)  # passed-pawn potential
                promotion_y = 0 if side == 1 else 4
                next_y = y + (-1 if side == 1 else 1)
                if next_y == promotion_y and occupancy[next_y][x] is None:
                    score += side * 28  # clear, immediate promotion lane

            # Promotion race: evaluate the actual forward corridor, not just
            # pawn rank. Empty lanes are valuable; a blocker or a controlled
            # promotion square reduces the threat. The opening double-step is
            # counted when the pawn is still on its initial rank.
            promotion_y = 0 if side == 1 else 4
            dy = -1 if side == 1 else 1
            squares_to_rank = abs(promotion_y - y)
            path_clear = True
            unsafe_path_squares = 0
            cy = y
            for _ in range(squares_to_rank):
                cy += dy
                if occupancy[cy][x] is not None:
                    path_clear = False
                    break
                if attacks[-side][cy][x] > attacks[side][cy][x]:
                    unsafe_path_squares += 1
            if path_clear and squares_to_rank > 0:
                start_rank = 3 if side == 1 else 1
                moves_to_promote = squares_to_rank
                if y == start_rank:
                    two_step_y = y + 2 * dy
                    if _inside5(x, two_step_y) and occupancy[y + dy][x] is None and occupancy[two_step_y][x] is None:
                        moves_to_promote -= 1
                race_bonus = {1: 145, 2: 76, 3: 32, 4: 10}.get(moves_to_promote, 0)
                promo_enemy = attacks[-side][promotion_y][x]
                promo_support = attacks[side][promotion_y][x]
                if promo_enemy > promo_support:
                    race_bonus = int(race_bonus * 0.55)
                if unsafe_path_squares:
                    race_bonus = int(race_bonus * max(0.45, 1.0 - 0.16 * unsafe_path_squares))
                enemy_king = black_king if side == 1 else white_king
                if enemy_king is not None:
                    king_distance = abs(enemy_king[0] - x) + abs(enemy_king[1] - promotion_y)
                    if king_distance <= moves_to_promote + 1:
                        race_bonus = int(race_bonus * 0.72)
                score += side * race_bonus

            next_y = y + (-1 if side == 1 else 1)
            if _inside5(x, next_y) and occupancy[next_y][x] is not None:
                score -= side * 8  # blocked pawn; modest penalty only

        for count in file_count:
            if count > 1:
                score -= side * 20 * (count - 1)  # doubled pawns

        for i, (x, y) in enumerate(pawns):
            for ox, oy in pawns[i + 1:]:
                if abs(ox - x) == 1 and abs(oy - y) <= 1:
                    score += side * 10  # connected/supporting pawn pair

    # ── Pseudo-mobility and central control ───────────────────────────────
    # Mobility is deliberately a modest term: these are pseudo-legal targets,
    # not a replacement for list_legal_moves_for() or search.
    score += int((mobility[1] - mobility[-1]) * 3)
    score += int((safe_mobility[1] - safe_mobility[-1]) * 2.5)

    # Nonlinear liberty pressure: on a compact board, being reduced to just a
    # few destinations often precedes a forced tactic or a stalemate loss.
    # Penalise the side that must move now more heavily.
    side_to_move = 1 if board.current_player.name == "white" else -1
    for side in (1, -1):
        liberty_penalty = _mobility_crisis_penalty(
            mobility[side], side == side_to_move, phase)
        score -= side * liberty_penalty

    white_centre = black_centre = 0
    for y in (1, 2, 3):
        for x in (1, 2, 3):
            white_centre += min(2, attacks[1][y][x])
            black_centre += min(2, attacks[-1][y][x])
    score += (white_centre - black_centre) * 3

    # ── Tactical exposure and exchange liability ───────────────────────────
    # Estimate whether a piece is actually vulnerable, using attacker/defender
    # counts and the cheapest enemy attacker. This is deliberately a bounded
    # static estimate, not a substitute for search or a full SEE algorithm.
    # A threat is discounted when the threatened side is to move and can answer.
    side_to_move = 1 if board.current_player.name == "white" else -1
    for name, x, y, side, value in pieces:
        if name == "king" or value <= 0:
            continue
        enemy = -side
        enemy_count = attacks[enemy][y][x]
        if enemy_count == 0:
            continue
        friendly_count = attacks[side][y][x]
        enemy_min = cheapest_attacker[enemy][y][x]
        attacker_surplus = enemy_count - friendly_count

        if attacker_surplus > 0:
            # A cheaper attacker with more attackers than defenders is a real
            # conversion threat. Major pieces deserve a larger penalty because
            # losing a Queen/Right often decides a 5x5 game.
            if enemy_min < value:
                fraction = 0.36 + 0.07 * min(2, attacker_surplus - 1)
            else:
                fraction = 0.22 + 0.05 * min(2, attacker_surplus - 1)
        else:
            # A defended piece is not automatically hanging; retain a smaller
            # risk premium for overloads and potentially unfavourable exchanges.
            fraction = 0.035 + (0.025 if enemy_min < value else 0.0)

        if name in ("queen", "right") and enemy_min < value and attacker_surplus > 0:
            fraction += 0.05
        if side_to_move == side:
            fraction *= 0.55  # the owner can still move or counterattack

        liability = min(int(value * 0.62), int(value * fraction))
        score -= side * liability

    # ── King safety and stalemate-resistance ───────────────────────────────
    def king_danger(king_pos, side):
        if king_pos is None:
            return 0
        kx, ky = king_pos
        enemy = -side
        checkers = attacks[enemy][ky][kx]
        zone_pressure = 0
        safe_escapes = 0
        friendly_pawn_shield = 0
        for dx, dy in _EVAL_KING_STEPS:
            nx, ny = kx + dx, ky + dy
            if not _inside5(nx, ny):
                continue
            target = occupancy[ny][nx]
            if target is not None and target[3] == side:
                continue
            zone_pressure += min(2, attacks[enemy][ny][nx])
            if attacks[enemy][ny][nx] == 0:
                safe_escapes += 1
            if target is None:
                # Nearby friendly pawn shelter helps particularly in the
                # middlegame; it is small on a board this cramped.
                for px, py in (white_pawns if side == 1 else black_pawns):
                    if max(abs(px - nx), abs(py - ny)) <= 1:
                        friendly_pawn_shield += 1
                        break
        # One open line on a 5x5 board can turn into a forcing attack quickly.
        # Exposed checks and the lack of safe exits need nonlinear penalties.
        danger = min(10, zone_pressure) * (10 if phase > 5 else 8)
        if checkers:
            danger += 135 + min(3, checkers - 1) * 32
        if safe_escapes == 0:
            danger += 78  # tactical cage; exact terminal loss is handled by search
        elif safe_escapes == 1:
            danger += 38
        elif safe_escapes == 2:
            danger += 14
        danger -= min(3, friendly_pawn_shield) * (8 if phase > 5 else 3)
        return max(0, danger)

    score -= king_danger(white_king, 1)
    score += king_danger(black_king, -1)

    # ── Endgame conversion: centralise our king and drive the enemy king ────
    # A winning king-plus-major-piece ending needs active king support and a
    # restricted enemy king. Only apply this when a meaningful material edge
    # and a queen/Right (or equivalent mating force) exist, avoiding aimless
    # king chasing in equal or minor-piece-only positions.
    material_diff = white_material - black_material
    for side, own_king, enemy_king, own_material, enemy_material in (
        (1, white_king, black_king, white_material, black_material),
        (-1, black_king, white_king, black_material, white_material),
    ):
        if own_king is None or enemy_king is None:
            continue
        has_major = any(p_side == side and name in ("queen", "right")
                        for name, _, _, p_side, _ in pieces)
        if phase <= 9 and own_material >= enemy_material + 250 and has_major:
            distance = abs(own_king[0] - enemy_king[0]) + abs(own_king[1] - enemy_king[1])
            king_support = max(0, 8 - distance) * 4
            edge_distance = min(enemy_king[0], 4 - enemy_king[0],
                                enemy_king[1], 4 - enemy_king[1])
            edge_pressure = (2 - edge_distance) * 10
            score += side * (king_support + edge_pressure)

    # ── Piece activity: supported central outposts ─────────────────────────
    for name, x, y, side, _ in pieces:
        if name not in ("knight", "bishop", "right") or not (1 <= x <= 3 and 1 <= y <= 3):
            continue
        pawn_row = y + 1 if side == 1 else y - 1
        friendly_pawns = white_pawns if side == 1 else black_pawns
        if any(abs(px - x) == 1 and py == pawn_row for px, py in friendly_pawns):
            score += side * 12

    # ── Winning conversion ─────────────────────────────────────────────────
    # In a material lead, simplify only modestly: as material disappears,
    # preserving the lead becomes more important. This nudges trades that keep
    # a real advantage without distorting forced wins or making random attacks.
    material_diff = white_material - black_material
    material_reduced = (_EVAL_PHASE_MAX - phase) / _EVAL_PHASE_MAX
    conversion = int(max(-85, min(85, material_diff * 0.07 * material_reduced)))
    score += conversion

    # Small side-to-move initiative bonus. Static evaluations are still
    # colour-symmetric; mate/stalemate results are determined by the search.
    score += 10 if board.current_player.name == "white" else -10
    return score


# ═══════════════════════════════════════════════════════════════════════════════
#                            MOVE ORDERING
# ═══════════════════════════════════════════════════════════════════════════════


def _move_key(piece, move):
    """Coordinate key retained for TT/PV matching and board-local move identity."""
    return (piece.position.x, piece.position.y, move.position.x, move.position.y)


def _heuristic_move_key(piece, move):
    """Side- and piece-aware key for history/killer learning.

    A coordinate-only history key aliases different actors and both colours.
    That is especially harmful in this compact variant, where the same source
    square coordinates recur frequently in sibling branches.
    """
    return (piece.player.name, _piece_name(piece), *_move_key(piece, move))


def _killer_bucket(piece, ply):
    return (piece.player.name, _piece_name(piece), int(ply))


def _score_move(piece, move, board, depth, check_data=None):
    """Return lexicographic move-ordering fields; never prunes or changes legality.

    Tiers are separate rather than additive, so a large history score cannot
    accidentally push a quiet move above a capture, promotion or likely check.
    Quiet-check detection is only a geometric prefilter: a false positive merely
    changes order, never legality or the returned score.
    """
    caps = getattr(move, "captures", set())
    mk = _move_key(piece, move)
    tier = 1
    tactical_score = 0

    # 1. Captures — MVV-LVA, preserving multiple-capture value where applicable.
    if caps:
        capture_score = 0
        for cap_pos in caps:
            try:
                victim = board[cap_pos].piece
                if victim:
                    victim_val = PIECE_VALUES.get(_piece_name(victim), 0)
                    attacker_val = PIECE_VALUES.get(_piece_name(piece), 0)
                    capture_score += 10000 + victim_val - (attacker_val >> 3)
            except Exception:
                capture_score += 5000
        tier, tactical_score = 6, capture_score

    # 2. Promotion (captures retain the higher capture tier).
    is_promotion = (_piece_name(piece) == "pawn" and
                    ((piece.player.name == "white" and move.position.y == 0) or
                     (piece.player.name == "black" and move.position.y == 4)))
    if is_promotion and tier < 5:
        tier, tactical_score = 5, 0

    # 3. Likely quiet checks; the prefilter only protects ordering priority.
    if (_ENABLE_QUIET_CHECK_ORDERING and not caps and check_data is not None):
        enemy_king = check_data[0]
        if _move_might_give_check(board, piece, move, check_data) and tier < 4:
            tier = 4
            tactical_score = _quiet_check_priority(piece, move, enemy_king)

    # 4. Side- and piece-scoped killers.
    if not caps and tier < 3 and mk in _killer_moves.get(_killer_bucket(piece, depth), ()):
        tier = 3
        tactical_score = 0

    # History is strictly a within-tier tiebreaker.
    history_score = _history.get(_heuristic_move_key(piece, move), 0)
    cx, cy = move.position.x, move.position.y
    centre_score = 4 - (abs(cx - 2) + abs(cy - 2))
    return tier, tactical_score, history_score, centre_score


def _order_moves(moves, board, depth=0, tt_best_move=None):
    """Order PV/TT first, then tactical and side-aware heuristic priorities."""
    check_data = _check_prefilter_data(board) if moves else None
    scored = []
    for i, (piece, move) in enumerate(moves):
        mk = _move_key(piece, move)
        pv_priority = 1 if tt_best_move is not None and mk == tt_best_move else 0
        score = _score_move(piece, move, board, depth, check_data)
        scored.append((pv_priority, *score, i, piece, move))
    scored.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], -item[4], item[5]))
    return [(piece, move) for (_, _, _, _, _, _, piece, move) in scored]


def _store_killer(ply, piece, move):
    """Record one of the two best quiet cutoffs for this side/type/ply bucket."""
    mk = _move_key(piece, move)
    bucket = _killer_bucket(piece, ply)
    killers = _killer_moves.setdefault(bucket, [])
    if mk not in killers:
        killers.insert(0, mk)
        if len(killers) > 2:
            killers.pop()


def _update_history(piece, move, depth):
    """Bounded, side- and piece-aware history reward for a beta-cutoff move."""
    key = _heuristic_move_key(piece, move)
    bonus = min(512, max(1, int(depth) * int(depth) * 4))
    _history[key] = min(6000, _history.get(key, 0) + bonus)


def _age_history(decay=0.78, floor=12, max_entries=5000):
    """Age history once per own turn; retain useful experience within a game.

    Scores are search-ordering hints, not evaluation terms. Decay prevents old
    cutoffs from dominating after the position changes; the cap bounds memory.
    Game-boundary reset remains in ``agent``.
    """
    global _history
    if not _history:
        return
    aged = {}
    for key, value in _history.items():
        score = int(value * decay)
        if score >= floor:
            aged[key] = score
    if len(aged) > max_entries:
        # Keep the strongest learned ordering hints deterministically.
        keep = sorted(aged.items(), key=lambda item: (-item[1], item[0]))[:max_entries]
        aged = dict(keep)
    _history = aged


# ─── Search-efficiency helpers ────────────────────────────────────────────────

def _lmr_reduction(depth, move_index, piece, move, is_tactical, in_check, ply):
    """Conservative dynamic LMR; returns 0, 1 or 2 plies.

    The first reduction threshold stays close to v7.2. A second ply is reserved
    for genuinely late quiet moves at substantial depth. Moves with strong
    history/killer evidence are protected from reduction.
    """
    if is_tactical or in_check or depth < 3 or ply < 2 or move_index < 3:
        return 0
    mk = _move_key(piece, move)
    if mk in _killer_moves.get(_killer_bucket(piece, ply), ()):
        return 0
    hist = _history.get(_heuristic_move_key(piece, move), 0)
    if hist >= 256:
        return 0
    if depth >= 8 and move_index >= 10 and hist < 96:
        return 2
    return 1


def _store_tt_entry(board_hash, depth, flag, score, best_move, ply_from_root):
    """Store with depth preference and LRU eviction instead of flushing the TT.

    Existing deeper entries are retained. At capacity, only the least-recently
    used entry is evicted, avoiding the wholesale 90%-full table reset in v7.2.
    """
    global _tt
    previous = _tt.get(board_hash)
    if previous is not None and previous[0] > depth:
        _tt.move_to_end(board_hash)
        return
    _tt[board_hash] = (
        depth, flag, _score_to_tt(score, ply_from_root), best_move
    )
    _tt.move_to_end(board_hash)
    while len(_tt) > _TT_MAX_SIZE:
        _tt.popitem(last=False)


def _apply_root_tiebreak(board, selected_piece, selected_move, ply_tag=0):
    """Optional reproducible choice among genuinely near-equal root moves.

    Disabled by default. Scores come only from the final completed root search;
    mate-range positions are excluded. This changes variety, not search depth.
    """
    global _last_random_tiebreak
    _last_random_tiebreak = False
    if not _ENABLE_ROOT_RANDOM_TIEBREAK or len(_last_root_exact_evals) < 2:
        return selected_piece, selected_move
    exact = sorted(_last_root_exact_evals, key=lambda row: -row[0])
    best_score = exact[0][0]
    if abs(best_score) >= MATE_THRESHOLD:
        return selected_piece, selected_move
    eligible = [row for row in exact
                if best_score - row[0] <= _ROOT_TIE_WINDOW_CP]
    if len(eligible) < 2:
        return selected_piece, selected_move
    # Stable FNV-1a seed: same position + seed yields the same choice.
    seed = _ROOT_RANDOM_SEED & 0xFFFFFFFF
    for ch in _board_signature(board):
        seed = ((seed ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    seed ^= int(ply_tag) & 0xFFFFFFFF
    chosen = random.Random(seed).choice(eligible)
    _last_random_tiebreak = True
    return chosen[1], chosen[2]


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHECK DETECTION (lightweight)
# ═══════════════════════════════════════════════════════════════════════════════


def _is_in_check(board):
    """Return whether the side to move's king is pseudo-attacked.

    Uses Chess Fragments geometry, including the Right's knight-jump ability
    and the king's adjacent attacks. Pins are not resolved here; a false
    positive only causes a small bounded quiescence extension, never a legal
    move or terminal result to be fabricated.
    """
    king_pos = None
    piece_rows = []
    occupancy = [[None] * 5 for _ in range(5)]
    for p in board.get_pieces():
        name = _piece_name(p)
        x, y = p.position.x, p.position.y
        side = 1 if p.player.name == "white" else -1
        value = PIECE_VALUES.get(name, 0)
        row = (name, x, y, side, value)
        piece_rows.append(row)
        occupancy[y][x] = row
        if name == "king" and p.player.name == board.current_player.name:
            king_pos = (x, y)
    if king_pos is None:
        return False
    attacks, _, _, _ = _build_evaluation_maps(piece_rows, occupancy)
    enemy = -1 if board.current_player.name == "white" else 1
    kx, ky = king_pos
    return attacks[enemy][ky][kx] > 0


def _check_prefilter_data(board, side_name=None):
    """Return enemy king square and occupied cells for a single node."""
    if side_name is None:
        side_name = board.current_player.name
    enemy_name = 'black' if side_name == 'white' else 'white'
    king = None
    occupied = set()
    for p in board.get_pieces():
        xy = (p.position.x, p.position.y)
        occupied.add(xy)
        if _piece_name(p) == 'king' and p.player.name == enemy_name:
            king = xy
    return king, occupied


def _move_might_give_check(board, piece, move, check_data=None):
    """Cheap direct-check prefilter; exact child-board check confirms candidates."""
    name = _piece_name(piece)
    tx, ty = move.position.x, move.position.y
    side = piece.player.name
    if check_data is None:
        check_data = _check_prefilter_data(board, side)
    king, occupied = check_data
    if king is None:
        return False
    kx, ky = king
    dx, dy = abs(kx - tx), abs(ky - ty)
    if name == 'pawn':
        forward = -1 if side == 'white' else 1
        return dx == 1 and ky - ty == forward
    if name == 'knight':
        return (dx, dy) in ((1, 2), (2, 1))
    if name == 'king':
        return max(dx, dy) == 1
    if name == 'bishop':
        aligned = dx == dy and dx > 0
    elif name == 'right':
        if (dx, dy) in ((1, 2), (2, 1)):
            return True
        aligned = (dx == 0 and dy > 0) or (dy == 0 and dx > 0)
    elif name == 'queen':
        aligned = ((dx == 0 and dy > 0) or (dy == 0 and dx > 0)
                   or (dx == dy and dx > 0))
    else:
        return False
    if not aligned:
        return False
    sx = 0 if kx == tx else (1 if kx > tx else -1)
    sy = 0 if ky == ty else (1 if ky > ty else -1)
    source = (piece.position.x, piece.position.y)
    x, y = tx + sx, ty + sy
    while (x, y) != (kx, ky):
        if (x, y) in occupied and (x, y) != source:
            return False
        x += sx
        y += sy
    return True


def _quiet_check_priority(piece, move, king):
    """Stable priority among a small number of likely quiet checking moves."""
    if king is None:
        return 0
    dist = abs(king[0] - move.position.x) + abs(king[1] - move.position.y)
    bonus = {'queen': 16, 'right': 14, 'knight': 12,
             'bishop': 10, 'pawn': 9, 'king': 0}.get(_piece_name(piece), 0)
    return bonus + (5 - min(5, dist)) * 10

# ═══════════════════════════════════════════════════════════════════════════════
#                          QUIESCENCE SEARCH
# ═══════════════════════════════════════════════════════════════════════════════


def _tablebase_score(board, colour, ply_from_root):
    """Return an exact retrograde score when this position is covered.

    The tablebase API scores from board.current_player's perspective.  The
    engine's ``colour`` uses the same convention (+1 White, -1 Black), so the
    returned score is already in the correct negamax frame.  Draw contempt is
    calculated from *material only*, not positional evaluation, avoiding a
    positional bonus incorrectly masquerading as a material advantage.
    """
    global _last_tb_probes, _last_tb_hits, _last_tb_wins, _last_tb_losses, _last_tb_draws
    if not _TABLEBASE_READY or _probe_endgame_tb is None:
        return None
    try:
        pieces = board.get_pieces()
        if len(pieces) > 4 or len(pieces) < 2:
            return None
        white_material = 0
        black_material = 0
        for piece in pieces:
            value = PIECE_VALUES.get(_piece_name(piece), 0)
            if piece.player.name == "white":
                white_material += value
            else:
                black_material += value
        white_balance = white_material - black_material
        side_balance = white_balance if board.current_player.name == "white" else -white_balance
        _last_tb_probes += 1
        hit, score = _probe_endgame_tb(
            board, _piece_name, ply_from_root=ply_from_root, mat_diff=side_balance
        )
        if not hit:
            return None
        _last_tb_hits += 1
        if score >= 90000:
            _last_tb_wins += 1
        elif score <= -90000:
            _last_tb_losses += 1
        else:
            _last_tb_draws += 1
        return int(score)
    except Exception:
        # A malformed/unsupported tablebase key must never forfeit a move.
        return None


def _quiescence(board, alpha, beta, colour, q_depth, ply_from_root=0, check_budget=2):
    """
    Capture-only extension search at leaf nodes.

    Prevents the horizon effect — ensures we don't stop searching right
    before a winning (or losing) capture.  Bounded to *q_depth* plies of
    captures to stay within the time budget.

    Also considers pawn promotions as tactical moves. If the side to move is
    in check, it searches legal evasions rather than illegally standing pat.
    A small check-extension budget bounds checking sequences.
    """
    global _nodes_searched, _deadline

    _nodes_searched += 1
    if (_nodes_searched & 7) == 0:
        if time.perf_counter() >= _deadline:
            raise TimeoutError

    # Terminal check
    is_term, term_score = _check_terminal(board, ply_from_root)
    if is_term:
        return term_score

    tb_score = _tablebase_score(board, colour, ply_from_root)
    if tb_score is not None:
        return tb_score

    current_player = board.current_player
    in_check = _is_in_check(board)

    # A checked side cannot stand pat: every legal evasion must be considered,
    # even at q_depth==0. This is particularly important on the 5x5 board,
    # where a single check can force mate or lose a high-value Right/Queen.
    if in_check:
        evasions = list_legal_moves_for(board, current_player)
        if time.perf_counter() >= _deadline:
            raise TimeoutError
        if not evasions:
            return -MATE_SCORE + ply_from_root

        # Bound checking sequences. At the cap, inspect every evasion and
        # reject immediate terminal losses, then use static evaluation.
        if check_budget <= 0:
            best_evasion = -float('inf')
            for piece, move in evasions:
                child = _make_move_on_clone(board, piece, move)
                if child is None:
                    continue
                is_term, child_score = _check_terminal(child, ply_from_root + 1)
                if is_term:
                    value = -child_score
                else:
                    child_moves = list_legal_moves_for(child, child.current_player)
                    if not child_moves:
                        value = MATE_SCORE - (ply_from_root + 1)
                    else:
                        value = colour * evaluate_for_white(child)
                if value > best_evasion:
                    best_evasion = value
            return best_evasion if best_evasion != -float('inf') else -MATE_SCORE + ply_from_root

        best_evasion = -float('inf')
        for piece, move in evasions:
            if time.perf_counter() >= _deadline:
                raise TimeoutError
            child = _make_move_on_clone(board, piece, move)
            if child is None:
                continue
            value = -_quiescence(child, -beta, -alpha, -colour,
                                 q_depth - 1, ply_from_root + 1,
                                 check_budget - 1)
            if value > best_evasion:
                best_evasion = value
            if value > alpha:
                alpha = value
            if alpha >= beta:
                break
        return best_evasion if best_evasion != -float('inf') else -MATE_SCORE + ply_from_root

    # Stand-pat is valid only when the side to move is not in check.
    stand_pat = colour * evaluate_for_white(board)
    moves = None

    # At the quiescence horizon, and before a stand-pat beta cutoff, explicitly
    # check terminal mobility so a stalemated side is never scored as healthy.
    if q_depth <= 0 or stand_pat >= beta:
        moves = list_legal_moves_for(board, current_player)
        if time.perf_counter() >= _deadline:
            raise TimeoutError
        if not moves:
            return -MATE_SCORE + ply_from_root
        if stand_pat >= beta:
            return stand_pat

    if stand_pat > alpha:
        alpha = stand_pat

    if q_depth <= 0:
        return stand_pat

    # Delta pruning: if even a queen-sized swing cannot reach alpha, skip the
    # remaining tactical move generation.  Alpha is unchanged when stand_pat
    # is below it, which is the only case in which this test can fire.
    if stand_pat < alpha - 950 and abs(alpha) < MATE_THRESHOLD:
        # Delta pruning may skip a stalemate if it returns before move generation.
        # Generate legal moves only on this pruning path, not on every q-node.
        probe_moves = list_legal_moves_for(board, current_player)
        if time.perf_counter() >= _deadline:
            raise TimeoutError
        if not probe_moves:
            return -MATE_SCORE + ply_from_root
        return alpha

    # Generate and filter to captures (+ promotions), reusing the mobility
    # check above if one was already needed.
    if moves is None:
        moves = list_legal_moves_for(board, current_player)
        if time.perf_counter() >= _deadline:
            raise TimeoutError
    if not moves:
        return -MATE_SCORE + ply_from_root

    capture_moves = []
    for piece, move in moves:
        if time.perf_counter() >= _deadline:
            raise TimeoutError
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

    capture_moves.sort(key=lambda x: -x[0])

    # Quiet checks are forcing moves too. The old implementation considered
    # them only when there were *no* captures, so a checking move could vanish
    # from the q-search simply because an unrelated capture was available.
    # Add at most one quiet check beside captures (two if the frontier is quiet),
    # only near the root of q-search and under the existing check budget.
    quiet_checks = []
    if q_depth > 0 and check_budget >= 2 and ply_from_root <= 6:
        check_data = _check_prefilter_data(board)
        enemy_king = check_data[0]
        for piece, move in moves:
            if getattr(move, "captures", set()):
                continue
            if _piece_name(piece) == "pawn" and (
                (piece.player.name == "white" and move.position.y == 0) or
                (piece.player.name == "black" and move.position.y == 4)
            ):
                continue
            if _move_might_give_check(board, piece, move, check_data):
                quiet_checks.append((
                    _quiet_check_priority(piece, move, enemy_king), piece, move))
        quiet_checks.sort(key=lambda item: -item[0])

    # Search captures first, then the strongest one quiet check. This avoids
    # broad branching while preserving the most forcing non-capture alternative.
    for _, piece, move in capture_moves:
        child = _make_move_on_clone(board, piece, move)
        if child is None:
            continue
        val = -_quiescence(child, -beta, -alpha, -colour, q_depth - 1,
                           ply_from_root + 1, check_budget)
        if val > alpha:
            alpha = val
        if alpha >= beta:
            return alpha

    quiet_limit = 1 if capture_moves else 2
    for _, piece, move in quiet_checks[:quiet_limit]:
        if time.perf_counter() >= _deadline:
            raise TimeoutError
        child = _make_move_on_clone(board, piece, move)
        if child is None or not _is_in_check(child):
            continue
        val = -_quiescence(child, -beta, -alpha, -colour, q_depth - 1,
                           ply_from_root + 1, check_budget - 1)
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
    global _last_tt_hits, _last_tt_cutoffs
    global _last_lmr_one_ply, _last_lmr_two_ply

    _nodes_searched += 1
    if (_nodes_searched & 7) == 0:     # Poll every 8 nodes; root also checks each child
        if time.perf_counter() >= _deadline:
            raise TimeoutError

    # Quick terminal check (no move generation)
    is_term, term_score = _check_terminal(board, ply_from_root)
    if is_term:
        return term_score

    # Probe before the horizon/TT path: covered 3–4-piece positions are solved
    # immediately by retrograde WDL, rather than spending clock on approximation.
    tb_score = _tablebase_score(board, colour, ply_from_root)
    if tb_score is not None:
        return tb_score

    # Leaf → quiescence search
    if depth <= 0:
        return _quiescence(board, alpha, beta, colour, 2, ply_from_root)

    # Keep the caller's window for safe TT bound classification.  TT probing
    # may narrow the live window, but those narrowed bounds must not be treated
    # as the original search window when storing the result.
    alpha_original = alpha
    beta_original = beta

    # ── TT Probe ──────────────────────────────────────────────────────────
    board_hash = _hash_board(board)
    tt_entry = _tt.get(board_hash)
    tt_best_move = None

    if tt_entry is not None:
        _last_tt_hits += 1
        _tt.move_to_end(board_hash)
        tt_depth, tt_flag, tt_val, tt_mv = tt_entry
        tt_val = _score_from_tt(tt_val, ply_from_root)
        if tt_depth >= depth:
            if tt_flag == TT_EXACT:
                _last_tt_cutoffs += 1
                return tt_val
            elif tt_flag == TT_LOWER:
                alpha = max(alpha, tt_val)
            elif tt_flag == TT_UPPER:
                beta = min(beta, tt_val)
            if alpha >= beta:
                _last_tt_cutoffs += 1
                return tt_val
        tt_best_move = tt_mv     # Always use TT move for ordering

    # ── Move Generation & Ordering ────────────────────────────────────────
    current_player = board.current_player
    moves = list_legal_moves_for(board, current_player)
    if time.perf_counter() >= _deadline:
        raise TimeoutError

    if not moves:
        # No legal moves = loss (stalemate AND checkmate both lose in this variant)
        return -MATE_SCORE + ply_from_root

    # ── Bounded selective extensions ───────────────────────────────────────
    # Check detection is pseudo-attack based (pins are not resolved). A false
    # positive can therefore cost a little search time, but it cannot remove a
    # legal move or fabricate a result. We use it ONLY to extend, never to prune.
    # Check at depth 1 as well as deeper nodes: a forcing check on the horizon
    # should not be evaluated as though the defender had no tactical reply.
    # Cap check extensions by absolute ply so checking sequences cannot keep
    # depth alive indefinitely. At most one extension is granted per node.
    global _last_check_extensions, _last_mobility_extensions
    check_probe = (depth >= 2 and ply_from_root <= _CHECK_EXTENSION_MAX_PLY) or depth == 1 or (depth >= 3 and ply_from_root >= 2)
    in_check = _is_in_check(board) if check_probe else False
    if (_ENABLE_CHECK_EXTENSION and in_check and depth >= 1
            and ply_from_root < _CHECK_EXTENSION_MAX_PLY):
        depth += 1
        _last_check_extensions += 1
    elif len(moves) == 1 and ply_from_root < 14:
        depth += 1
        _last_mobility_extensions += 1
    elif len(moves) == 2 and depth >= 3 and ply_from_root < 8:
        depth += 1
        _last_mobility_extensions += 1

    ordered = _order_moves(moves, board, ply_from_root, tt_best_move)
    # Precompute enemy king and occupancy where checking moves can be protected
    # from LMR/futility pruning. The prefilter is only a tactical ordering hint.
    check_data = (_check_prefilter_data(board)
                  if (depth == 1 or (depth >= 3 and ply_from_root >= 2)) else None)

    # ── Futility Pruning (depth 1 only) ───────────────────────────────────
    # If static eval + margin can't reach α, skip non-tactical moves.
    # Check status matters here: never prune a legal evasion just because a
    # static score is below alpha. The already-computed in_check is reused.
    futile = False
    if depth == 1 and not in_check and abs(alpha) < 90000:
        static_eval = colour * evaluate_for_white(board)
        if static_eval + 200 <= alpha:
            futile = True

    # ── Main Search Loop ──────────────────────────────────────────────────
    best_val = -float('inf')
    best_move_key = None
    best_piece_for_killer = None
    best_move_for_killer = None
    moves_searched = 0

    for i, (piece, move) in enumerate(ordered):
        if time.perf_counter() >= _deadline:
            raise TimeoutError
        # Determine if this move is tactical (capture or near-promotion)
        caps = getattr(move, "captures", set())
        is_tactical = (bool(caps) or (_piece_name(piece) == "pawn" and
            ((piece.player.name == "white" and move.position.y <= 1) or
             (piece.player.name == "black" and move.position.y >= 3))) or
            (check_data is not None and _move_might_give_check(board, piece, move, check_data)))

        # Skip non-tactical moves under futility pruning
        if futile and moves_searched > 0 and not is_tactical:
            continue

        child = _make_move_on_clone(board, piece, move)
        if time.perf_counter() >= _deadline:
            raise TimeoutError
        if child is None:
            continue

        # Dynamic, conservative LMR. The common case remains a one-ply
        # reduction; a second ply is reserved for very late quiet moves at depth
        # 8+, while forcing/tactical, checked, killer and strong-history moves
        # remain full depth.
        reduction = _lmr_reduction(
            depth, moves_searched, piece, move, is_tactical, in_check,
            ply_from_root,
        )
        if reduction == 1:
            _last_lmr_one_ply += 1
        elif reduction == 2:
            _last_lmr_two_ply += 1

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
    if best_val <= alpha_original:
        tt_flag = TT_UPPER
    elif best_val >= beta_original:
        tt_flag = TT_LOWER
    else:
        tt_flag = TT_EXACT

    _store_tt_entry(board_hash, depth, tt_flag, best_val, best_move_key,
                    ply_from_root)

    return best_val


# ═══════════════════════════════════════════════════════════════════════════════
#                      ITERATIVE DEEPENING DRIVER
# ═══════════════════════════════════════════════════════════════════════════════


_last_root_evals = []   # (bound/exact score, piece, move) for legacy safeguards
_last_root_exact_evals = []  # only fully resolved root scores, for safe random tie-breaking


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
    global _last_depth_reached, _last_nodes_searched, _last_branching_factor, _last_root_evals
    global _last_iteration_trace, _last_aborted_depth, _last_aborted_nodes
    global _last_check_extensions, _last_mobility_extensions
    global _last_root_exact_evals
    global _last_tt_hits, _last_tt_cutoffs, _last_lmr_one_ply, _last_lmr_two_ply
    global _last_aspiration_fail_low, _last_aspiration_fail_high

    _deadline = deadline
    _killer_moves = {}
    _last_root_evals = []
    _last_root_exact_evals = []
    _last_iteration_trace = []
    _last_aborted_depth = 0
    _last_aborted_nodes = 0
    _last_check_extensions = 0
    _last_mobility_extensions = 0
    _last_tt_hits = 0
    _last_tt_cutoffs = 0
    _last_lmr_one_ply = 0
    _last_lmr_two_ply = 0
    _last_aspiration_fail_low = 0
    _last_aspiration_fail_high = 0

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

    for depth in range(1, 50):
        depth_started = time.perf_counter()
        _nodes_searched = 0
        try:
            if time.perf_counter() >= deadline:
                raise TimeoutError
            root_moves = list_legal_moves_for(board, my_player)
            if time.perf_counter() >= deadline:
                raise TimeoutError
            if not root_moves:
                break

            # The root itself is searched by this driver rather than _negamax,
            # so it often has no TT entry. Carry the previous completed iteration's
            # principal-variation move forward when that happens.
            board_hash = _hash_board(board)
            tt_entry = _tt.get(board_hash)
            if tt_entry is not None:
                _tt.move_to_end(board_hash)
            tt_best_move = tt_entry[3] if tt_entry is not None else None
            if tt_best_move is None and best_piece is not None and best_move is not None:
                tt_best_move = _move_key(best_piece, best_move)

            ordered = _order_moves(root_moves, board, 0, tt_best_move)
            if time.perf_counter() >= deadline:
                raise TimeoutError

            current_best_score = -float('inf')
            current_best_piece = ordered[0][0]
            current_best_move = ordered[0][1]

            # ── Aspiration Windows (depth ≥ 3) ────────────────────────
            delta = _ASPIRATION_DELTA
            if depth >= 3:
                aspiration_alpha = prev_score - delta
                aspiration_beta = prev_score + delta
            else:
                aspiration_alpha = -float('inf')
                aspiration_beta = float('inf')

            while True:
                if time.perf_counter() >= deadline:
                    raise TimeoutError
                # Reset the live alpha/beta window on every retry. Only the
                # failed side is widened; the search's mutated alpha is never
                # carried into the next aspiration attempt.
                alpha, beta = aspiration_alpha, aspiration_beta
                window_alpha, window_beta = alpha, beta

                current_best_score = -float('inf')
                current_best_piece = ordered[0][0]
                current_best_move = ordered[0][1]
                moves_searched_root = 0

                depth_evals = []
                exact_depth_evals = []
                for piece, move in ordered:
                    if time.perf_counter() >= deadline:
                        raise TimeoutError
                    child = _make_move_on_clone(board, piece, move)
                    if time.perf_counter() >= deadline:
                        raise TimeoutError
                    if child is None:
                        continue

                    exact_score = False
                    if moves_searched_root == 0:
                        val = -_negamax(child, depth - 1, -beta, -alpha,
                                        -colour, 1)
                        exact_score = (depth < 3 or
                                       (window_alpha < val < window_beta))
                    else:
                        # PVS at root. A zero-window fail-low is only an upper
                        # bound, not an exact score; never use it for random ties.
                        val = -_negamax(child, depth - 1, -alpha - 1, -alpha,
                                        -colour, 1)
                        if alpha < val < beta:
                            val = -_negamax(child, depth - 1, -beta, -alpha,
                                            -colour, 1)
                            exact_score = True

                    depth_evals.append((val, piece, move))
                    if exact_score:
                        exact_depth_evals.append((val, piece, move))
                    if val > current_best_score:
                        current_best_score = val
                        current_best_piece = piece
                        current_best_move = move

                    alpha = max(alpha, val)
                    moves_searched_root += 1

                    # A root fail-high cannot be improved inside this window.
                    # Stop the scan and let aspiration logic widen and re-search.
                    if alpha >= beta:
                        break

                # Check aspiration window outcome
                if depth < 3:
                    break    # No aspiration for shallow depths
                if current_best_score <= window_alpha:
                    _last_aspiration_fail_low += 1
                    delta = min(delta * 4, 400_000)
                    aspiration_alpha = prev_score - delta  # widen low side only
                elif current_best_score >= window_beta:
                    _last_aspiration_fail_high += 1
                    delta = min(delta * 4, 400_000)
                    aspiration_beta = prev_score + delta   # widen high side only
                else:
                    break    # Result inside window — done

            # Completed this depth
            best_piece = current_best_piece
            best_move = current_best_move
            prev_score = current_best_score
            total_nodes_this_move += _nodes_searched
            if depth_evals:
                _last_root_evals = sorted(depth_evals, key=lambda x: -x[0])
                _last_root_exact_evals = sorted(exact_depth_evals, key=lambda x: -x[0])

            # Effective branching factor
            if prev_depth_nodes > 0 and _nodes_searched > 0:
                _last_branching_factor = _nodes_searched / max(prev_depth_nodes, 1)
            prev_depth_nodes = _nodes_searched
            completed_depth = depth
            _last_iteration_trace.append({
                "depth": depth,
                "nodes": _nodes_searched,
                "elapsed_s": round(max(0.0, time.perf_counter() - depth_started), 4),
                "score": int(current_best_score) if abs(current_best_score) < 1e12 else str(current_best_score),
                "root_moves": len(root_moves),
            })

            # Early exit on forced mate
            if current_best_score > 90000:
                break

        except TimeoutError:
            total_nodes_this_move += _nodes_searched
            _last_aborted_depth = depth
            _last_aborted_nodes = _nodes_searched
            break

    # Record instrumentation
    _last_depth_reached = completed_depth
    _last_nodes_searched = total_nodes_this_move
    best_piece, best_move = _apply_root_tiebreak(
        board, best_piece, best_move, len(_move_stats_log)
    )

    return best_piece, best_move


def _normalised_root_entropy(root_evals, temperature=180.0):
    """Shannon entropy of a softened root-score distribution, in [0, 1].

    The value is not an evaluation score. It estimates how ambiguous the root
    choice is: many similar moves yield high entropy; one clear move yields low.
    """
    scores = [float(item[0]) for item in root_evals if item and item[0] is not None]
    if len(scores) <= 1:
        return 0.0
    top = max(scores)
    weights = [math.exp(max(-40.0, (score - top) / temperature)) for score in scores]
    total = sum(weights)
    if total <= 0:
        return 0.0
    probs = [w / total for w in weights]
    entropy = -sum(p * math.log(p) for p in probs if p > 0)
    return max(0.0, min(1.0, entropy / math.log(len(probs))))


def _opponent_has_immediate_terminal_win(child_board, our_player_name, deadline):
    """Prove whether the opponent has a reply that wins immediately by terminality.

    In Chess Fragments, any position with no legal moves is a loss. Return None
    for an inconclusive check (deadline reached / malformed child), never treat
    an unverified move as proven safe.
    """
    try:
        if time.perf_counter() >= deadline:
            return None
        enemy_moves = list_legal_moves_for(child_board, child_board.current_player)
        if not enemy_moves:
            return False  # Our move already wins by immobilising the opponent.
        for enemy_piece, enemy_move in enemy_moves:
            if time.perf_counter() >= deadline:
                return None
            after = _make_move_on_clone(child_board, enemy_piece, enemy_move)
            if after is None:
                continue
            if after.current_player.name != our_player_name:
                return None
            terminal, score = _check_terminal(after, 2)
            if terminal:
                if score <= -MATE_THRESHOLD:
                    return True
                continue
            if not list_legal_moves_for(after, after.current_player):
                return True
        return False
    except Exception:
        return None



def _same_square(a, b):
    """Compare ChessMaker Position-like objects without relying on hashability."""
    try:
        return a.x == b.x and a.y == b.y
    except Exception:
        return a == b


_MATERIAL_GUARD_THRESHOLD_CP = 280
_MATERIAL_GUARD_MAX_SCORE_LOSS_CP = 150
_MATERIAL_GUARD_MAX_ALTERNATIVES = 4


def _captured_material_value(board, move, victim_side):
    """Return material value captured by move from victim_side on board."""
    total = 0
    for square_pos in (getattr(move, "captures", set()) or set()):
        try:
            victim = board[square_pos].piece
        except Exception:
            victim = None
        if victim is not None and victim.player.name == victim_side:
            total += PIECE_VALUES.get(_piece_name(victim), 0)
    return total


def _opponent_has_unrecapturable_major_capture(child_board, our_player_name, deadline,
                                               threshold_cp=_MATERIAL_GUARD_THRESHOLD_CP):
    """Detect a major-piece loss after one capture/reply/exchange verification.

    For each legal opponent capture of a major piece, examine our legal replies.
    A reply is credited for material it actually captures (including recapturing
    the attacker); if the opponent can immediately take the replying piece, that
    loss is charged back. A checking move by itself is NOT treated as proof that
    the material loss is harmless. This remains a bounded tactical alarm, not a
    general static-exchange evaluator.

    Returns (unsafe, estimated_net_loss_cp). None means the deadline/API made the
    result inconclusive.
    """
    try:
        if time.perf_counter() >= deadline:
            return None, 0
        enemy = child_board.current_player
        if enemy.name == our_player_name:
            return None, 0
        enemy_moves = list_legal_moves_for(child_board, enemy)
        for enemy_piece, enemy_move in enemy_moves:
            if time.perf_counter() >= deadline:
                return None, 0
            captured_value = _captured_material_value(
                child_board, enemy_move, our_player_name)
            if captured_value < threshold_cp:
                continue

            after_capture = _make_move_on_clone(child_board, enemy_piece, enemy_move)
            if after_capture is None or after_capture.current_player.name != our_player_name:
                return None, 0
            our_replies = list_legal_moves_for(after_capture, after_capture.current_player)
            if not our_replies:
                # No legal reply means the side to move loses in this variant.
                return True, MATE_SCORE

            best_reply_net_loss = float("inf")
            examined_reply = False
            for reply_piece, reply_move in our_replies:
                if time.perf_counter() >= deadline:
                    return None, 0
                recovered_value = _captured_material_value(
                    after_capture, reply_move, enemy.name)
                after_reply = _make_move_on_clone(after_capture, reply_piece, reply_move)
                if after_reply is None or after_reply.current_player.name != enemy.name:
                    continue
                examined_reply = True
                enemy_replies = list_legal_moves_for(after_reply, after_reply.current_player)
                if not enemy_replies:
                    # Our reply wins by leaving the opponent without a legal move.
                    best_reply_net_loss = -MATE_SCORE
                    break

                # If the opponent can immediately capture the piece that just
                # replied, charge its current value. Other tactical consequences
                # remain for the main search to judge.
                reply_square = getattr(reply_move, "position", None)
                reply_piece_after = None
                try:
                    reply_piece_after = after_reply[reply_square].piece
                except Exception:
                    pass
                exposed_reply_value = 0
                if reply_piece_after is not None and reply_piece_after.player.name == our_player_name:
                    for enemy_reply_piece, enemy_reply_move in enemy_replies:
                        caps = getattr(enemy_reply_move, "captures", set()) or set()
                        if reply_square is not None and any(
                            _same_square(pos, reply_square) for pos in caps
                        ):
                            exposed_reply_value = max(
                                exposed_reply_value,
                                PIECE_VALUES.get(_piece_name(reply_piece_after), 0),
                            )

                net_loss = max(0, captured_value + exposed_reply_value - recovered_value)
                best_reply_net_loss = min(best_reply_net_loss, net_loss)

            if not examined_reply:
                return None, 0
            if best_reply_net_loss >= threshold_cp:
                return True, int(best_reply_net_loss)
        return False, 0
    except Exception:
        return None, 0


def _opponent_has_immediate_promotion(child_board, our_player_name, deadline):
    """Check for an opponent promotion next move that cannot be immediately taken.

    A promotion is treated as a tactical emergency only if, after promoting, our
    side has no legal capture of the newly promoted piece on its promotion square.
    """
    try:
        if time.perf_counter() >= deadline:
            return None
        enemy = child_board.current_player
        if enemy.name == our_player_name:
            return None
        promotion_rank = 0 if enemy.name == "white" else 4
        for piece, move in list_legal_moves_for(child_board, enemy):
            if time.perf_counter() >= deadline:
                return None
            if (_piece_name(piece) != "pawn"
                    or getattr(getattr(move, "position", None), "y", None) != promotion_rank):
                continue
            promotion_square = getattr(move, "position", None)
            promoted_board = _make_move_on_clone(child_board, piece, move)
            if promoted_board is None or promoted_board.current_player.name != our_player_name:
                return None
            promoted_piece = None
            try:
                promoted_piece = promoted_board[promotion_square].piece
            except Exception:
                pass
            if promoted_piece is None or promoted_piece.player.name != enemy.name:
                return None
            replies = list_legal_moves_for(promoted_board, promoted_board.current_player)
            if not replies:
                return True
            can_capture_promotion = False
            for reply_piece, reply_move in replies:
                if time.perf_counter() >= deadline:
                    return None
                captures = getattr(reply_move, "captures", set()) or set()
                if any(_same_square(pos, promotion_square) for pos in captures):
                    can_capture_promotion = True
                    break
            if not can_capture_promotion:
                return True
        return False
    except Exception:
        return None


def _tactical_guard_status(child_board, our_player_name, deadline):
    """Return (material_loss_cp, immediate_promotion_threat) or (None, None)."""
    unsafe, loss_cp = _opponent_has_unrecapturable_major_capture(
        child_board, our_player_name, deadline)
    if unsafe is None:
        return None, None
    promotion = _opponent_has_immediate_promotion(
        child_board, our_player_name, deadline)
    if promotion is None:
        return None, None
    return (int(loss_cp) if unsafe else 0), bool(promotion)


def _material_blunder_guard(board, player, selected_piece, selected_move, deadline):
    """Avoid immediate major-piece hangs or next-move promotions conservatively.

    The selected move must have a fully resolved root score. A replacement must
    also have a fully resolved score no more than 150 cp below the selected move,
    and must pass both tactical checks. PVS bounds are never used as scores.
    """
    global _last_material_guard_triggered, _last_material_guard_loss
    global _last_material_guard_replacement, _last_promotion_guard_triggered
    global _last_promotion_guard_replacement
    if (selected_piece is None or selected_move is None
            or time.perf_counter() >= deadline):
        return selected_piece, selected_move
    child = _make_move_on_clone(board, selected_piece, selected_move)
    if child is None:
        return selected_piece, selected_move
    loss_cp, promotion_threat = _tactical_guard_status(
        child, player.name, deadline)
    if loss_cp is None or promotion_threat is None:
        return selected_piece, selected_move
    if loss_cp <= 0 and not promotion_threat:
        return selected_piece, selected_move

    _last_material_guard_triggered = loss_cp > 0
    _last_material_guard_loss = int(loss_cp)
    _last_promotion_guard_triggered = bool(promotion_threat)

    selected_key = _move_key(selected_piece, selected_move)
    selected_score = next((score for score, p, m in _last_root_exact_evals
                           if _move_key(p, m) == selected_key), None)
    # Do not guess when the chosen move has only a PVS bound or no completed
    # exact root score. The main search must retain authority in that case.
    if selected_score is None or abs(selected_score) >= MATE_THRESHOLD:
        return selected_piece, selected_move

    exact = sorted(_last_root_exact_evals, key=lambda item: -item[0])
    checked = 0
    for score, alt_piece, alt_move in exact:
        if time.perf_counter() >= deadline or checked >= _MATERIAL_GUARD_MAX_ALTERNATIVES:
            break
        if _move_key(alt_piece, alt_move) == selected_key:
            continue
        if score < selected_score - _MATERIAL_GUARD_MAX_SCORE_LOSS_CP:
            break
        checked += 1
        alt_child = _make_move_on_clone(board, alt_piece, alt_move)
        if alt_child is None:
            continue
        alt_loss, alt_promotion = _tactical_guard_status(
            alt_child, player.name, deadline)
        if alt_loss == 0 and alt_promotion is False:
            if loss_cp > 0:
                _last_material_guard_replacement = True
            if promotion_threat:
                _last_promotion_guard_replacement = True
            return alt_piece, alt_move
    return selected_piece, selected_move

def _entropy_guided_anti_loss(board, player, selected_piece, selected_move,
                              legal_moves, deadline):
    """Check tactical hangs/promotions, then preserve the terminal-loss guard.

    The new guard only substitutes a near-equal exact root alternative after
    finding a major-piece loss or an unanswerable next-move promotion.
    """
    selected_piece, selected_move = _material_blunder_guard(
        board, player, selected_piece, selected_move, deadline)
    if selected_piece is None or selected_move is None or time.perf_counter() >= deadline:
        return selected_piece, selected_move
    # Full reply verification remains low-material by default, but a king move
    # in a crowded position gets a narrowly targeted stalemate check too. The
    # v6.8 Strong/sample2 loss was exactly this pattern: Black's king move let
    # White's next king move leave Black with no legal moves. Other high-material
    # moves keep v6.8's original fast path to avoid broad extra branching.
    try:
        piece_count = len(board.get_pieces())
    except Exception:
        return selected_piece, selected_move
    high_material_king_move = (piece_count > 10 and
                               _piece_name(selected_piece) == "king")
    if piece_count > 10 and not high_material_king_move:
        return selected_piece, selected_move

    child = _make_move_on_clone(board, selected_piece, selected_move)
    if child is None:
        return selected_piece, selected_move
    unsafe = _opponent_has_immediate_terminal_win(child, player.name, deadline)
    if unsafe is not True:
        return selected_piece, selected_move

    entropy = _normalised_root_entropy(_last_root_evals)
    candidate_limit = min(6, 3 + int(round(3 * entropy)))
    # High-material king safety is an opportunistic guard. Keep alternative
    # verification bounded so the last-resort safety pass cannot dominate search.
    if high_material_king_move:
        candidate_limit = min(candidate_limit, 3)
    candidates = []
    seen = set()
    selected_key = _move_key(selected_piece, selected_move)
    seen.add(selected_key)
    for score, piece, move in _last_root_evals:
        key = _move_key(piece, move)
        if key not in seen:
            candidates.append((score, piece, move))
            seen.add(key)
    # Use the existing tactical order as a fallback if a completed iteration
    # has too few alternatives (for example, if the last iteration timed out).
    for piece, move in _order_moves(legal_moves, board, 0, None):
        key = _move_key(piece, move)
        if key not in seen:
            candidates.append((None, piece, move))
            seen.add(key)

    checked = 0
    first_unresolved = None
    for score, piece, move in candidates:
        if checked >= candidate_limit or time.perf_counter() >= deadline:
            if first_unresolved is None:
                first_unresolved = (piece, move)
            break
        checked += 1
        alt_child = _make_move_on_clone(board, piece, move)
        if alt_child is None:
            continue
        result = _opponent_has_immediate_terminal_win(alt_child, player.name, deadline)
        if result is False:
            return piece, move
        if result is None and first_unresolved is None:
            first_unresolved = (piece, move)

    # The selected move is known to lose immediately. If we cannot prove a safe
    # option before the small deadline, prefer an unverified alternative over a
    # move with a demonstrated one-reply loss. If every tested alternative also
    # loses immediately, keep the original search choice rather than inventing.
    return first_unresolved if first_unresolved is not None else (selected_piece, selected_move)


# ═══════════════════════════════════════════════════════════════════════════════
#                 BOUNDED ROOT PUCT / MCTS TIE-BREAK PROBE
# ═══════════════════════════════════════════════════════════════════════════════


class _PUCTNode:
    """Small per-move MCTS node; all values are from this node's side-to-move."""
    __slots__ = ("board", "depth", "to_play", "prior", "parent_move", "visits",
                 "value_sum", "children", "moves", "next_move", "terminal", "is_root",
                 "policy_mode")

    def __init__(self, board, depth, prior=1.0, parent_move=None, is_root=False,
                 policy_mode="balanced"):
        self.board = board
        self.depth = depth
        self.to_play = board.current_player.name
        self.prior = float(prior)
        self.parent_move = parent_move
        self.visits = 0
        self.value_sum = 0.0
        self.children = []
        self.moves = None
        self.next_move = 0
        self.terminal = None
        self.is_root = is_root
        self.policy_mode = policy_mode

    @property
    def mean_value(self):
        return self.value_sum / self.visits if self.visits else 0.0


def _puct_softmax(items):
    """Convert (logit, payload) pairs into stable priors summing to one."""
    if not items:
        return []
    top = max(item[0] for item in items)
    weights = [math.exp(max(-24.0, min(0.0, item[0] - top))) for item in items]
    total = sum(weights) or 1.0
    return [(weight / total, item[1]) for weight, item in zip(weights, items)]


def _puct_move_logit(board, piece, move, root_score=None, best_root_score=None,
                     policy_mode="balanced"):
    """Cheap handcrafted policy prior with position-dependent risk appetite.

    ``complicate`` is used when the classical root evaluation says we are behind:
    forcing checks, promotions and meaningful captures receive stronger priors.
    ``convert`` is used when ahead: sound exchanges are favoured over speculative
    captures. ``balanced`` stays between those policies. These are priors only;
    PUCT's adversarial backups and the classical search still evaluate outcomes.
    """
    logit = 0.0
    if root_score is not None and best_root_score is not None:
        gap_scale = 230.0 if policy_mode == "complicate" else 180.0
        logit += max(-3.0, min(0.0,
                               (float(root_score) - float(best_root_score)) / gap_scale))

    caps = getattr(move, "captures", set())
    victim_total = 0
    if caps:
        for cap_pos in caps:
            try:
                victim = board[cap_pos].piece
                if victim is not None:
                    victim_total += PIECE_VALUES.get(_piece_name(victim), 0)
            except Exception:
                victim_total += 300
        attacker_value = PIECE_VALUES.get(_piece_name(piece), 0)
        if policy_mode == "convert":
            logit += (0.48 if victim_total >= attacker_value else -0.30)
        elif policy_mode == "complicate":
            logit += 0.62 + min(0.95, victim_total / 900.0)
        else:
            logit += 0.45 + min(0.85, victim_total / 1000.0)

    if _piece_name(piece) == "pawn":
        if ((piece.player.name == "white" and move.position.y == 0) or
                (piece.player.name == "black" and move.position.y == 4)):
            logit += 1.35 if policy_mode == "complicate" else 1.15

    try:
        gives_check = _move_might_give_check(board, piece, move)
    except Exception:
        gives_check = False
    if gives_check:
        if policy_mode == "complicate":
            logit += 0.90
        elif policy_mode == "convert":
            logit += 0.12
        else:
            logit += 0.55

    tx, ty = move.position.x, move.position.y
    logit += max(0, 4 - abs(tx - 2) - abs(ty - 2)) * 0.035
    return max(-5.0, min(3.5, logit))


def _puct_terminal_value(score):
    """Map terminal centipawn/mate scores to a bounded side-to-move value."""
    if score > MATE_THRESHOLD:
        return 1.0
    if score < -MATE_THRESHOLD:
        return -1.0
    return 0.0 if score == 0 else (1.0 if score > 0 else -1.0)


def _puct_static_value(board):
    """Cheap leaf value from the current side-to-move's perspective."""
    terminal, score = _check_terminal(board, 0)
    if terminal:
        return _puct_terminal_value(score)
    moves = list_legal_moves_for(board, board.current_player)
    if not moves:
        return -1.0  # No legal move is a loss, even when not in check.
    score_white = evaluate_for_white(board)
    score_stm = score_white if board.current_player.name == "white" else -score_white
    return math.tanh(score_stm / 1050.0)


def _puct_prepare_node(node):
    """Generate and policy-order a node's legal moves once."""
    terminal, score = _check_terminal(node.board, node.depth)
    if terminal:
        node.terminal = _puct_terminal_value(score)
        node.moves = []
        return

    legal = list_legal_moves_for(node.board, node.board.current_player)
    if not legal:
        node.terminal = -1.0
        node.moves = []
        return

    ranked = []
    for index, (piece, move) in enumerate(legal):
        logit = _puct_move_logit(node.board, piece, move,
                                 policy_mode=node.policy_mode)
        ranked.append((logit, index, piece, move))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    priors = _puct_softmax([(item[0], (item[2], item[3])) for item in ranked])
    node.moves = [(prior, payload[0], payload[1]) for prior, payload in priors]


def _puct_select_child(node):
    """Select a child with adversarial PUCT; negate child Q at alternating turns."""
    root_scale = math.sqrt(max(1, node.visits))
    best_child = None
    best_score = -float("inf")
    for child in node.children:
        exploitation = -child.mean_value
        exploration = _PUCT_C * child.prior * root_scale / (1 + child.visits)
        score = exploitation + exploration
        if score > best_score:
            best_score = score
            best_child = child
    return best_child


def _puct_expand_one(node):
    """Expand the next policy-prior move. Returns child or None if exhausted."""
    if node.moves is None:
        _puct_prepare_node(node)
    if node.terminal is not None or node.next_move >= len(node.moves):
        return None
    prior, piece, move = node.moves[node.next_move]
    node.next_move += 1
    child_board = _make_move_on_clone(node.board, piece, move)
    if child_board is None:
        return None
    child = _PUCTNode(child_board, node.depth + 1, prior, (piece, move),
                      policy_mode=node.policy_mode)
    node.children.append(child)
    return child


def _puct_simulate(root, deadline, max_depth):
    """Run one deterministic-selection MCTS simulation with progressive widening."""
    path = [root]
    node = root

    while True:
        if time.perf_counter() >= deadline:
            return False

        terminal, terminal_score = _check_terminal(node.board, node.depth)
        if terminal:
            value = _puct_terminal_value(terminal_score)
            node.terminal = value
            break

        if node.depth >= max_depth:
            value = _puct_static_value(node.board)
            break

        if node.is_root:
            child = _puct_select_child(node)
            if child is None:
                value = _puct_static_value(node.board)
                break
            node = child
            path.append(node)
            continue

        if node.moves is None:
            _puct_prepare_node(node)
        if node.terminal is not None:
            value = node.terminal
            break

        # Progressive widening prevents a broad 5x5 node from cloning every
        # legal move up front. More alternatives become available as evidence grows.
        widening_limit = max(1, int(1.0 + 1.35 * math.sqrt(max(0, node.visits))))
        if len(node.children) < widening_limit and node.next_move < len(node.moves):
            child = _puct_expand_one(node)
            if child is None:
                continue
            node = child
            path.append(node)
            continue

        child = _puct_select_child(node)
        if child is None:
            value = _puct_static_value(node.board)
            break
        node = child
        path.append(node)

    # Value is stored from each node's own side-to-move perspective.
    for visited in reversed(path):
        visited.visits += 1
        visited.value_sum += value
        value = -value
    return True


def _puct_refine_root(board, player, selected_piece, selected_move, deadline,
                      budget_s=None):
    """Use a tiny PUCT tree only to adjudicate an ambiguous classical root.

    The PUCT probe is skipped for decisive or low-entropy positions. It sees only
    root moves already scored by a completed alpha-beta iteration, and it may only
    select among moves within a narrow centipawn window. The final one-reply
    terminal-loss verifier still runs after this function in ``agent()``.
    """
    global _last_puct_stats
    started = time.perf_counter()
    stats = {"used": False, "simulations": 0, "elapsed_s": 0.0,
             "entropy": 0.0, "candidate_count": 0, "overrode": False}
    _last_puct_stats = stats

    if (not _ENABLE_ROOT_PUCT or selected_piece is None or selected_move is None
            or len(_last_root_evals) < 2):
        return selected_piece, selected_move

    ordered_evals = sorted(_last_root_evals, key=lambda item: item[0], reverse=True)
    best_score = float(ordered_evals[0][0])
    if abs(best_score) >= MATE_THRESHOLD:
        return selected_piece, selected_move

    entropy = _normalised_root_entropy(ordered_evals)
    stats["entropy"] = round(entropy, 4)
    policy_mode = ("complicate" if best_score <= -180 else
                   "convert" if best_score >= 180 else "balanced")
    stats["policy_mode"] = policy_mode
    if entropy < _PUCT_MIN_ENTROPY:
        return selected_piece, selected_move

    selected_key = _move_key(selected_piece, selected_move)
    legal_by_key = {_move_key(p, m): (p, m) for p, m in
                    list_legal_moves_for(board, player)}
    candidates = []
    seen = set()
    for score, piece, move in ordered_evals:
        key = _move_key(piece, move)
        if key in seen or key not in legal_by_key:
            continue
        if best_score - float(score) > _PUCT_SCORE_WINDOW:
            continue
        # Use live root move objects, not move references from any cloned board.
        live_piece, live_move = legal_by_key[key]
        candidates.append((float(score), live_piece, live_move))
        seen.add(key)
        if len(candidates) >= _PUCT_MAX_CANDIDATES:
            break

    if len(candidates) < 2 or selected_key not in seen:
        return selected_piece, selected_move

    now = time.perf_counter()
    remaining = deadline - now
    if budget_s is None:
        budget_s = _PUCT_MAX_TIME
    allowance = min(_PUCT_MAX_TIME, max(0.0, float(budget_s)), max(0.0, remaining))
    if allowance < 0.035:
        return selected_piece, selected_move
    puct_deadline = now + allowance

    # A root node's children correspond exactly to the candidate moves from the
    # completed alpha-beta iteration. Root policy priors blend score proximity
    # with cheap tactical motifs.
    root = _PUCTNode(board, 0, 1.0, is_root=True, policy_mode=policy_mode)
    root_logits = []
    for score, piece, move in candidates:
        child_board = _make_move_on_clone(board, piece, move)
        if child_board is None:
            continue
        logit = _puct_move_logit(board, piece, move, score, best_score,
                                 policy_mode=policy_mode)
        root_logits.append((logit, (score, piece, move, child_board)))
    if len(root_logits) < 2:
        return selected_piece, selected_move

    root_priors = _puct_softmax(root_logits)
    for prior, payload in root_priors:
        score, piece, move, child_board = payload
        root.children.append(_PUCTNode(child_board, 1, prior, (piece, move),
                                       policy_mode=policy_mode))
    if len(root.children) < 2:
        return selected_piece, selected_move

    stats["used"] = True
    stats["candidate_count"] = len(root.children)
    for _ in range(_PUCT_MAX_SIMULATIONS):
        if time.perf_counter() >= puct_deadline:
            break
        if not _puct_simulate(root, puct_deadline, _PUCT_MAX_DEPTH):
            break
        stats["simulations"] += 1

    elapsed = max(0.0, time.perf_counter() - started)
    stats["elapsed_s"] = round(elapsed, 4)
    if not root.children or stats["simulations"] == 0:
        stats["used"] = False
        return selected_piece, selected_move

    chosen = max(root.children,
                 key=lambda child: (child.visits, -child.mean_value, child.prior))
    chosen_key = _move_key(*chosen.parent_move)
    baseline = next((child for child in root.children
                     if _move_key(*child.parent_move) == selected_key), None)
    stats["root_visits"] = [
        {"move": list(_move_key(*child.parent_move)),
         "visits": child.visits,
         "root_mean": round(-child.mean_value, 4),
         "prior": round(child.prior, 4)}
        for child in root.children
    ]

    # Avoid overturning a clear classical preference. A challenger must receive
    # at least two additional visits and its backed-up value must not be materially
    # worse than the classical move's value estimate.
    if baseline is not None and chosen is not baseline:
        visit_gain = chosen.visits - baseline.visits
        value_gap = (-chosen.mean_value) - (-baseline.mean_value)
        if visit_gain >= 2 and value_gap >= -0.06:
            stats["overrode"] = True
            return chosen.parent_move
    return selected_piece, selected_move


def _deterministic_fallback(legal_moves, board):
    """Return a stable tactical-order fallback; never inject random move noise."""
    if not legal_moves:
        return None, None
    ordered = _order_moves(legal_moves, board, 0, None)
    return ordered[0]


# ═══════════════════════════════════════════════════════════════════════════════
#                         MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════


_ENABLE_STDERR_LOG = True  # Can be set to False to gate stderr printing


def _charge_own_clock(started_at):
    """Charge only time this agent actually spent deciding a move."""
    global _own_clock_used, _own_moves_seen
    elapsed = max(0.0, time.perf_counter() - started_at)
    _own_clock_used += elapsed
    _own_moves_seen += 1
    return elapsed


def agent(board, player, var):
    """
    AI Agent for the 5×5 Chess Fragments game — Version 7.5 Endgame Depth candidate.

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
    global _tt, _opening_book, _position_history
    global _last_depth_reached, _last_nodes_searched, _last_branching_factor
    global _move_stats_log, _game_start_time, _last_seen_ply
    global _own_clock_used, _own_moves_seen
    global _killer_moves, _history, _last_puct_stats, _last_root_evals
    global _last_iteration_trace, _last_aborted_depth, _last_aborted_nodes
    global _last_check_extensions, _last_mobility_extensions
    global _last_material_guard_triggered, _last_material_guard_loss
    global _last_material_guard_replacement
    global _last_promotion_guard_triggered, _last_promotion_guard_replacement
    global _last_tb_probes, _last_tb_hits, _last_tb_wins, _last_tb_losses, _last_tb_draws

    try:
        call_started = time.perf_counter()
        _last_depth_reached = 0
        _last_nodes_searched = 0
        _last_branching_factor = 1.0
        _last_root_evals = []
        _last_root_exact_evals = []
        _last_iteration_trace = []
        _last_aborted_depth = 0
        _last_aborted_nodes = 0
        _last_check_extensions = 0
        _last_mobility_extensions = 0
        _last_tt_hits = 0
        _last_tt_cutoffs = 0
        _last_lmr_one_ply = 0
        _last_lmr_two_ply = 0
        _last_aspiration_fail_low = 0
        _last_aspiration_fail_high = 0
        _last_random_tiebreak = False
        _last_material_guard_triggered = False
        _last_material_guard_loss = 0
        _last_material_guard_replacement = False
        _last_promotion_guard_triggered = False
        _last_promotion_guard_replacement = False
        _last_tb_probes = 0
        _last_tb_hits = 0
        _last_tb_wins = 0
        _last_tb_losses = 0
        _last_tb_draws = 0
        _last_puct_stats = {"used": False, "simulations": 0, "elapsed_s": 0.0}
        ply = var[0]
        time_budget = var[1]
        now = call_started

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
            _own_clock_used = 0.0
            _own_moves_seen = 0
            _tt = OrderedDict()
            _position_history = {}
            _killer_moves = {}
            _history = {}

        _last_seen_ply = ply
        if not is_new_game:
            _age_history()

        # Each player owns a 300-second clock. Opponent thinking time must not
        # consume our clock, so budget from *our accumulated search time*, not
        # wall time elapsed since the game began.
        player_clock = 300.0
        clock_reserve = 2.0
        remaining_own = max(0.0, player_clock - _own_clock_used)
        max_budget = max(0.25, time_budget - 1.5)
        # Plan for roughly 27 turns by this agent. Recompute each turn, so a
        # short tactical game can spend more now while long games preserve time.
        estimated_own_turns_left = max(8, 27 - _own_moves_seen)
        clock_target = max(0.25, (remaining_own - clock_reserve) / estimated_own_turns_left)
        effective_budget = min(max_budget, clock_target, max(0.25, remaining_own - clock_reserve))

        # ── Forced Move (single legal move) ───────────────────────────────────
        legal_moves = list_legal_moves_for(board, player)
        if not legal_moves:
            return None, None
        if len(legal_moves) == 1:
            _last_depth_reached = 0
            _last_nodes_searched = 0
            _last_branching_factor = 1.0
            elapsed = _charge_own_clock(call_started)
            _log_move_stats(ply, player.name, elapsed)
            return legal_moves[0]

        deadline = time.perf_counter() + effective_budget
        # Keep a small bounded slice for terminal-threat verification. The search
        # remains the priority; this reserve is capped to avoid sacrificing depth.
        try:
            low_material = len(board.get_pieces()) <= 10
        except Exception:
            low_material = False
        # Keep a small tail of the budget for one-reply terminal safety checks.
        # Low material retains the original reserve; crowded positions now also
        # reserve a bounded slice for the rare selected-king-move stalemate check.
        safety_reserve = (min(0.35, max(0.04, effective_budget * 0.04))
                          if low_material else
                          min(0.45, max(0.06, effective_budget * 0.04)))
        search_deadline = deadline - safety_reserve

        # TT capacity is maintained by bounded LRU replacement on insertion.

        # Track position for repetition detection
        current_hash = _hash_board(board)
        current_sig = _board_signature(board)
        _position_history[current_hash] = _position_history.get(current_hash, 0) + 1
        _position_history[current_sig] = _position_history.get(current_sig, 0) + 1

        # ── Opening Book (plies 1–2) ──────────────────────────────────────────
        if ply <= 2:
            # Selective anti-loss opening patch: only the two exact positions
            # that were demonstrated losses in the 16/18 v6.6 tournament.
            # Other positions remain governed by the known-good v6.6 search/cache.
            static_entry = _lookup_static_opening(board, player.name, ply)
            if static_entry is not None:
                for bp, bm in legal_moves:
                    if _move_key(bp, bm) == static_entry:
                        elapsed = _charge_own_clock(call_started)
                        _log_move_stats(ply, player.name, elapsed)
                        return bp, bm
            book_key = (current_hash, player.name, ply)
            book_entry = _opening_book.get(book_key)
            if book_entry is not None:
                fx, fy, tx, ty = book_entry
                for p in board.get_player_pieces(player):
                    if p.position.x == fx and p.position.y == fy:
                        for m in p.get_move_options():
                            if m.position.x == tx and m.position.y == ty:
                                elapsed = _charge_own_clock(call_started)
                                _log_move_stats(ply, player.name, elapsed)
                                return p, m
            # Unknown position — search and self-learn
            piece, move_opt = _iterative_deepening(board, player.name, search_deadline)
            if piece is not None and move_opt is not None:
                piece, move_opt = _entropy_guided_anti_loss(
                    board, player, piece, move_opt, legal_moves, deadline)
                _opening_book[book_key] = (
                    piece.position.x, piece.position.y,
                    move_opt.position.x, move_opt.position.y,
                )
            if piece is None or move_opt is None:
                piece, move_opt = _deterministic_fallback(legal_moves, board)
            elapsed = _charge_own_clock(call_started)
            _log_move_stats(ply, player.name, elapsed)
            return piece, move_opt

        # ── Main Search ───────────────────────────────────────────────────────
        piece, move_opt = _iterative_deepening(board, player.name, search_deadline)

        # Optional root PUCT probe: run only after a completed classical iteration,
        # only when several root moves are genuinely close, and leave at least
        # 45% of the safety reserve for the proof-based terminal-loss verifier.
        if piece is not None and move_opt is not None and ply > 2:
            puct_allowance = min(_PUCT_MAX_TIME, max(0.0, safety_reserve * 0.55))
            piece, move_opt = _puct_refine_root(
                board, player, piece, move_opt, deadline - safety_reserve * 0.45,
                budget_s=puct_allowance)

        # Fallback if search returned None
        if piece is None or move_opt is None:
            piece, move_opt = _deterministic_fallback(legal_moves, board)

        # ── Repetition Avoidance (Draw Avoidance without Blundering) ──────────
        # Check if the chosen move leads to a position that has occurred >= 2 times.
        # If repeating, pick the highest-eval alternative from completed search iterations
        # that produces a fresh or less-repeated position, provided it stays within a safe margin.
        if piece is not None and move_opt is not None:
            test_board = _make_move_on_clone(board, piece, move_opt)
            if test_board is not None:
                future_sig = _board_signature(test_board)
                future_count = _position_history.get(future_sig, 0)
                if future_count >= 2 and _last_root_evals:
                    best_ev = _last_root_evals[0][0]
                    for alt_ev, alt_piece, alt_move in _last_root_evals[1:]:
                        alt_board = _make_move_on_clone(board, alt_piece, alt_move)
                        if alt_board is None:
                            continue
                        alt_sig = _board_signature(alt_board)
                        if _position_history.get(alt_sig, 0) < future_count:
                            if best_ev > MATE_THRESHOLD:
                                safe_alternative = alt_ev > MATE_THRESHOLD and alt_ev >= best_ev - 250
                            elif best_ev > 0:
                                safe_alternative = alt_ev > 0 and alt_ev >= best_ev - 100
                            else:
                                safe_alternative = alt_ev >= best_ev - 100
                            if safe_alternative:
                                piece, move_opt = alt_piece, alt_move
                                break

            # Proof-based anti-loss pass runs after repetition policy so repetition
            # avoidance cannot accidentally reintroduce a one-reply terminal loss.
            piece, move_opt = _entropy_guided_anti_loss(
                board, player, piece, move_opt, legal_moves, deadline)

            # Record the chosen child position in history
            final_board = _make_move_on_clone(board, piece, move_opt)
            if final_board is not None:
                final_sig = _board_signature(final_board)
                _position_history[final_sig] = _position_history.get(final_sig, 0) + 1

        elapsed = _charge_own_clock(call_started)
        _log_move_stats(ply, player.name, elapsed)
        return piece, move_opt

    except Exception:
        # Top-Level Fail-Safe: NEVER crash or forfeit a game
        try:
            legal = list_legal_moves_for(board, player)
            if legal:
                fallback_piece, fallback_move = _deterministic_fallback(legal, board)
                elapsed = _charge_own_clock(call_started if 'call_started' in locals() else time.perf_counter())
                _log_move_stats(var[0] if isinstance(var, (list, tuple)) and var else -1,
                                getattr(player, "name", "?"), elapsed)
                return fallback_piece, fallback_move
        except Exception:
            pass
        return None, None


# ─── Instrumentation ─────────────────────────────────────────────────────────

def _log_move_stats(ply, player_name, elapsed):
    """Record and print per-move search metrics to stderr."""
    global _move_stats_log, _last_puct_stats
    global _last_iteration_trace, _last_aborted_depth, _last_aborted_nodes
    global _last_tt_hits, _last_tt_cutoffs, _last_lmr_one_ply, _last_lmr_two_ply
    global _last_aspiration_fail_low, _last_aspiration_fail_high, _last_random_tiebreak
    stats = {
        "ply":    ply,
        "player": player_name,
        "depth":  _last_depth_reached,
        "nodes":  _last_nodes_searched,
        "ebf":    round(_last_branching_factor, 2),
        "time_s": round(elapsed, 2),
        "puct":   dict(_last_puct_stats),
        "iterations": list(_last_iteration_trace),
        "aborted_depth": _last_aborted_depth,
        "aborted_nodes": _last_aborted_nodes,
        "check_extensions": _last_check_extensions,
        "mobility_extensions": _last_mobility_extensions,
        "tt_hits": _last_tt_hits,
        "tt_cutoffs": _last_tt_cutoffs,
        "lmr_one_ply": _last_lmr_one_ply,
        "lmr_two_ply": _last_lmr_two_ply,
        "aspiration_fail_low": _last_aspiration_fail_low,
        "aspiration_fail_high": _last_aspiration_fail_high,
        "random_tiebreak": _last_random_tiebreak,
        "material_guard": _last_material_guard_triggered,
        "material_guard_loss_cp": _last_material_guard_loss,
        "material_guard_replacement": _last_material_guard_replacement,
        "promotion_guard": _last_promotion_guard_triggered,
        "promotion_guard_replacement": _last_promotion_guard_replacement,
        "tablebase_ready": _TABLEBASE_READY,
        "tablebase_probes": _last_tb_probes,
        "tablebase_hits": _last_tb_hits,
        "tablebase_wins": _last_tb_wins,
        "tablebase_losses": _last_tb_losses,
        "tablebase_draws": _last_tb_draws,
    }
    _move_stats_log.append(stats)
    if _ENABLE_STDERR_LOG:
        nps = int(_last_nodes_searched / elapsed) if elapsed > 0.01 else 0
        trace = ",".join(f"{item['depth']}:{item['nodes']}"
                          for item in _last_iteration_trace) or "-"
        partial = (f" partial={_last_aborted_depth}:{_last_aborted_nodes}"
                   if _last_aborted_depth else "")
        print(
            f"[agent v7.5-endgame-depth] ply={ply:>3d}  {player_name:>5s}  "
            f"depth={_last_depth_reached}  nodes={_last_nodes_searched:>7d}  "
            f"ebf={_last_branching_factor:.2f}  nps={nps:>6d}  "
            f"iter={trace}{partial}  "
            f"ext=check:{_last_check_extensions}/mob:{_last_mobility_extensions}  "
            f"tt={_last_tt_hits}/{_last_tt_cutoffs}  "
            f"lmr={_last_lmr_one_ply}/{_last_lmr_two_ply}  "
            f"asp={_last_aspiration_fail_low}/{_last_aspiration_fail_high}  "
            f"rnd={int(_last_random_tiebreak)}  guard={int(_last_material_guard_triggered)}:"
            f"{_last_material_guard_loss}→{int(_last_material_guard_replacement)}  "
            f"promo={int(_last_promotion_guard_triggered)}→{int(_last_promotion_guard_replacement)}  "
            f"tb={_last_tb_hits}/{_last_tb_probes}  "
            f"puct=off  time={elapsed:.2f}s",
            file=sys.stderr,
        )
