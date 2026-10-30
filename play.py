"""
play.py — Play Chess Fragments against your AI agent in the terminal.

Usage:
    python play.py                  # you play as White vs the agent (Black)
    python play.py --side black     # you play as Black vs the agent (White)
    python play.py --board sample1  # choose starting position (sample0/1/2)

Controls:
    On your turn enter the move as:  <from_x> <from_y> <to_x> <to_y>
    e.g.  "2 4 2 3"  moves the piece at column 2, row 4 → column 2, row 3
    Type  "board"  at any prompt to reprint the board.
    Type  "quit"   or Ctrl-C to resign.
"""

import sys
import time
import argparse
from itertools import cycle

from chessmaker.chess.base import Board
from extension.board_utils import print_board_ascii, copy_piece_move, list_legal_moves_for
from extension.board_rules import get_result, thinking_with_timeout, THINKING_TIME_BUDGET, GAME_TIME_BUDGET
from samples import white, black, sample0, sample1, sample2
from agent import agent

SAMPLES = {"sample0": sample0, "sample1": sample1, "sample2": sample2}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _show_board(board):
    print()
    print_board_ascii(board)
    print()

def _parse_args():
    p = argparse.ArgumentParser(description="Play Chess Fragments vs your AI agent")
    p.add_argument("--side",  choices=["white", "black"], default="white",
                   help="Which side you want to play as (default: white)")
    p.add_argument("--board", choices=["sample0", "sample1", "sample2"], default="sample0",
                   help="Starting board position (default: sample0)")
    return p.parse_args()

def _list_moves(board, player):
    """Return a list of legal (piece, move) pairs for player."""
    return list_legal_moves_for(board, player)

def _human_move(board, player):
    """Ask the human to pick a move. Returns (piece, move_option) or None on resign."""
    moves = _list_moves(board, player)
    if not moves:
        return None, None

    while True:
        raw = input(f"  Your move [{player.name}]  (from_x from_y to_x to_y | board | quit): ").strip()
        if not raw:
            continue
        if raw.lower() == "quit":
            print("You resigned.")
            sys.exit(0)
        if raw.lower() == "board":
            _show_board(board)
            continue

        parts = raw.split()
        if len(parts) != 4:
            print("  ⚠  Enter exactly 4 numbers: from_x from_y to_x to_y")
            continue

        try:
            fx, fy, tx, ty = (int(v) for v in parts)
        except ValueError:
            print("  ⚠  Numbers only please.")
            continue

        matched = [(pc, mv) for pc, mv in moves
                   if pc.position.x == fx and pc.position.y == fy
                   and mv.position.x == tx and mv.position.y == ty]

        if not matched:
            # Show legal moves for the chosen piece so the user knows what's allowed
            piece_moves = [(pc, mv) for pc, mv in moves if pc.position.x == fx and pc.position.y == fy]
            if not piece_moves:
                print(f"  ⚠  No piece at ({fx},{fy}) that you can move.")
            else:
                legal = ", ".join(f"({mv.position.x},{mv.position.y})" for _,mv in piece_moves)
                print(f"  ⚠  Illegal destination. Legal targets for ({fx},{fy}): {legal}")
            continue

        return matched[0]   # return first match (there is normally only one)

# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def main():
    args = _parse_args()
    board_sample = SAMPLES[args.board]
    human_side = args.side
    ai_side = "black" if human_side == "white" else "white"

    print("=" * 56)
    print("   Chess Fragments — Human vs AI Agent")
    print("=" * 56)
    print(f"   You play as  : {human_side.upper()}")
    print(f"   AI plays as  : {ai_side.upper()}")
    print(f"   Board        : {args.board}")
    print(f"   AI time budget per move: {THINKING_TIME_BUDGET}s")
    print()
    print("  Piece symbols  (UPPER=White, lower=Black)")
    print("  P=Pawn  N=Knight  B=Bishop  R=Right  Q=Queen  K=King")
    print()
    print("  Coordinates: x=column (0-4, left→right), y=row (0-4, top→bottom)")
    print("=" * 56)

    players = [white, black]
    board = Board(squares=board_sample, players=players, turn_iterator=cycle(players))
    _show_board(board)

    turn_order = cycle(players)
    t_game_end = time.perf_counter() + GAME_TIME_BUDGET
    ply = 1

    while True:
        try:
            # --- game-time check ---
            if time.perf_counter() > t_game_end:
                print("=== Game ended: Draw — overall time limit reached ===")
                break

            player = next(turn_order)

            # --- check for legal moves first (stalemate / no moves) ---
            legal = _list_moves(board, player)
            if not legal:
                res = get_result(board)
                msg = res if res else f"{player.name} has no legal moves"
                print(f"=== Game ended: {msg} ===")
                break

            if player.name == human_side:
                # ---- HUMAN TURN ----
                print(f"Ply {ply} — YOUR turn ({player.name.upper()})")
                temp_board = board.clone()
                h_piece_tmp, h_move_tmp = _human_move(temp_board, player)
                if h_piece_tmp is None:
                    print(f"=== Game ended: {player.name} has no legal moves ===")
                    break
                board, piece, move_opt = copy_piece_move(board, h_piece_tmp, h_move_tmp)

            else:
                # ---- AI TURN ----
                print(f"Ply {ply} — AI thinking ({player.name.upper()})…")
                temp_board = board.clone()
                t0 = time.perf_counter()
                ai_piece_tmp, ai_move_tmp = thinking_with_timeout(
                    func=agent,
                    thinking_time=THINKING_TIME_BUDGET,
                    board=temp_board,
                    player=player,
                    var=[ply, THINKING_TIME_BUDGET]
                )
                elapsed = time.perf_counter() - t0
                board, piece, move_opt = copy_piece_move(board, ai_piece_tmp, ai_move_tmp)
                print(f"  AI chose: {piece} → ({move_opt.position.x},{move_opt.position.y})  [{elapsed:.1f}s]")

            if (not piece) or (not move_opt):
                print(f"=== Game ended: {player.name} could not make a legal move ===")
                break

            # --- apply move ---
            try:
                piece.move(move_opt)
                ply += 1
                if getattr(move_opt, "captures", None):
                    caps = ", ".join(f"({c.x},{c.y})" for c in move_opt.captures)
                    if caps:
                        print(f"  Captured at: {caps}")
            except Exception as e:
                print(f"=== Game ended: move error — {e} ===")
                break

            _show_board(board)

            res = get_result(board)
            if res:
                print(f"=== Game ended: {res} ===")
                break

        except KeyboardInterrupt:
            print("\n=== Game ended by user (Ctrl-C) ===")
            sys.exit(0)


if __name__ == "__main__":
    main()
