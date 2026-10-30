"""
opening_book.py — Master Opening Table for 5×5 Chess Fragments
==============================================================
COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces.

Pre-computed opening table for the 5 official board variants:
  • sample0 (Standard)
  • sample1 (Flipped Minor)
  • sample2 (Queen/Bishop Swap)
  • sample3 (Double Right)
  • sample4 (Queenless / Double Right + Bishop + Knight)

Uses a deterministic 25-cell FEN string representation that is 100%
immune to Python process hash-seed randomization.

Provides instant O(1) response (0.00s) on plies 1 and 2, preserving
game clock budget for deep endgame/middlegame calculations.
"""

_PIECE_SYMBOLS = {
    'pawn': 'p', 'knight': 'n', 'bishop': 'b',
    'right': 'r', 'queen': 'q', 'king': 'k'
}

def get_board_key(board, player_name, ply):
    """Generate a deterministic 25-character string representation of the board."""
    chars = []
    for row in board._squares:
        for sq in row:
            p = sq.piece
            if p is None:
                chars.append('.')
            else:
                c = _PIECE_SYMBOLS.get(type(p).__name__.lower(), '?')
                chars.append(c.upper() if p.player.name == 'white' else c)
    return ''.join(chars) + f"_{player_name}_{ply}"


MASTER_OPENINGS = {
    # ── Ply 1: White Openings ────────────────────────────────────────────────
    "nqkbrppppp.....PPPPPRBKQN_white_1": (2, 3, 2, 2),  # sample0: Central pawn push
    "rqknbppppp.....PPPPPBNKQR_white_1": (2, 3, 2, 2),  # sample1: Central pawn push
    "rbkqnppppp.....PPPPPNQKBR_white_1": (2, 3, 2, 2),  # sample2: Central pawn push
    "rqkrnppppp.....PPPPPNRKQR_white_1": (0, 3, 0, 2),  # sample3: a-pawn push
    "rbknrppppp.....PPPPPRNKBR_white_1": (2, 3, 2, 2),  # sample4: Central pawn push

    # ── Ply 2: Black Responses ───────────────────────────────────────────────
    # Responses to central pawn push (2, 3) -> (2, 2)
    "nqkbrppppp..P..PP.PPRBKQN_black_2": (1, 1, 2, 2),  # sample0: Contest central pawn
    "rqknbppppp..P..PP.PPBNKQR_black_2": (1, 1, 2, 2),  # sample1: Contest central pawn
    "rbkqnppppp..P..PP.PPNQKBR_black_2": (1, 1, 2, 2),  # sample2: Contest central pawn
    "rqkrnpppppP.....PPPPNRKQR_black_2": (1, 1, 0, 2),  # sample3: Contest a-pawn
    "rbknrppppp..P..PP.PPRNKBR_black_2": (1, 1, 2, 2),  # sample4: Contest central pawn

    # Responses to flank pawn push (0, 3) -> (0, 2)
    "nqkbrpppppP.....PPPPRBKQN_black_2": (1, 1, 0, 2),  # sample0: Capture flank pawn
    "rqknbpppppP.....PPPPBNKQR_black_2": (3, 1, 3, 2),  # sample1: Central anchor, seals file 3
    "rbkqnpppppP.....PPPPNQKBR_black_2": (1, 1, 1, 2),  # sample2: Block flank pawn & protect diagonal

    # Responses to flank e-pawn push (4, 3) -> (4, 2)
    "nqkbrppppp....PPPPP.RBKQN_black_2": (3, 1, 3, 2),  # sample0: Block e-pawn, seal file 3
    "rqknbppppp....PPPPP.BNKQR_black_2": (3, 1, 3, 2),  # sample1: Block e-pawn, seal file 3
    "rbkqnppppp....PPPPP.NQKBR_black_2": (3, 1, 3, 2),  # sample2: Block e-pawn, seal file 3
}


def lookup_book_move(board, player_name, ply):
    """
    Check if the current board position is in the master opening book.

    Returns
    -------
    tuple[int, int, int, int] or None
        (from_x, from_y, to_x, to_y) coordinates if found, else None.
    """
    key = get_board_key(board, player_name, ply)
    return MASTER_OPENINGS.get(key)
