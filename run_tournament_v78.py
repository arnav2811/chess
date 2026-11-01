"""
18-game tournament runner for agent v7.8 (draw-contempt / win-only build).
Adapted from CHESS_FRAGMENTS_V77_FINAL_HANDOFF/run_v77_18_tournament.py.
Uses the live agent.py in the project root.
"""
import sys, os, time, json
from itertools import cycle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from chessmaker.chess.base import Player, Board, Square
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right import Right
from extension.piece_pawn import Pawn_Q
from extension.board_utils import copy_piece_move
from extension.board_rules import get_result, thinking_with_timeout, THINKING_TIME_BUDGET, GAME_TIME_BUDGET

import agent as agent_module
from opponent import opponent as baseline_opponent
from strong_opponent import strong_opponent
from master_opponent import master_opponent


def make_fresh_board(sample_name):
    white = Player("white")
    black = Player("black")
    players = [white, black]

    if sample_name == "sample0":
        squares = [
            [Square(Knight(black)), Square(Queen(black)), Square(King(black)), Square(Bishop(black)), Square(Right(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Right(white)), Square(Bishop(white)), Square(King(white)), Square(Queen(white)), Square(Knight(white))],
        ]
    elif sample_name == "sample1":
        squares = [
            [Square(Right(black)), Square(Queen(black)), Square(King(black)), Square(Knight(black)), Square(Bishop(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Bishop(white)), Square(Knight(white)), Square(King(white)), Square(Queen(white)), Square(Right(white))],
        ]
    elif sample_name == "sample2":
        squares = [
            [Square(Right(black)), Square(Bishop(black)), Square(King(black)), Square(Queen(black)), Square(Knight(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Knight(white)), Square(Queen(white)), Square(King(white)), Square(Bishop(white)), Square(Right(white))],
        ]
    else:
        raise ValueError(f"Unknown sample: {sample_name}")

    board = Board(squares=squares, players=players, turn_iterator=cycle(players))
    return board, players


def play_one_game(match_id, tier, opp_name, board_sample_name, agent_color):
    t0 = time.perf_counter()
    board, players = make_fresh_board(board_sample_name)
    turn_order = cycle(players)

    opp_map = {
        "Baseline": baseline_opponent,
        "Strong":   strong_opponent,
        "Master":   master_opponent,
    }
    opp_fn = opp_map[opp_name]

    if agent_color == "white":
        p_white = agent_module.agent
        p_black = opp_fn
    else:
        p_white = opp_fn
        p_black = agent_module.agent

    clock = {"white": 300.0, "black": 300.0}
    ply = 1
    termination_reason = "Unknown"
    outcome = "UNKNOWN"

    while True:
        player = next(turn_order)
        temp_board = board.clone()

        if clock[player.name] <= 0.0:
            termination_reason = f"{player.name} game time limit exceeded"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        current_fn = p_white if player.name == "white" else p_black
        t_move_start = time.perf_counter()

        try:
            p_piece, p_move_opt = thinking_with_timeout(
                func=current_fn,
                thinking_time=min(THINKING_TIME_BUDGET, clock[player.name]),
                board=temp_board,
                player=player,
                var=[ply, THINKING_TIME_BUDGET],
            )
            board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)
        except Exception as e:
            termination_reason = f"{player.name} error: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        move_duration = time.perf_counter() - t_move_start
        clock[player.name] -= move_duration

        if (not piece) or (not move_opt):
            res = get_result(board)
            if res:
                termination_reason = str(res)
                res_low = termination_reason.lower()
                if "draw" in res_low:
                    outcome = "DRAW"
                elif f"{agent_color} loses" in res_low:
                    outcome = "LOSS"
                else:
                    outcome = "WIN"
            elif p_piece == 99:
                termination_reason = f"{player.name} thinking time out"
                outcome = "LOSS" if player.name == agent_color else "WIN"
            else:
                termination_reason = f"{player.name} no legal move"
                outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        try:
            piece.move(move_opt)
            ply += 1
        except Exception as e:
            termination_reason = f"{player.name} move error: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        res = get_result(board)
        if res:
            termination_reason = str(res)
            res_low = termination_reason.lower()
            if "draw" in res_low:
                outcome = "DRAW"
            elif f"{agent_color} loses" in res_low:
                outcome = "LOSS"
            else:
                outcome = "WIN"
            break

        if ply > 400:
            termination_reason = "Move limit (400 plies)"
            outcome = "DRAW"
            break

    elapsed = round(time.perf_counter() - t0, 1)
    pieces_left = len(list(board.get_pieces()))

    result_str = outcome
    symbol = {"WIN": "W", "DRAW": "D", "LOSS": "L"}.get(outcome, "?")
    print(
        f"[{match_id:>2d}/18] Tier {tier} ({opp_name:<8s}) | {board_sample_name} | "
        f"Agent {agent_color:<5s} -> {symbol}  | {termination_reason} "
        f"({ply} plies, {elapsed}s, {pieces_left} pcs)"
    )
    sys.stdout.flush()

    return {
        "match_id": match_id,
        "tier": tier,
        "opp": opp_name,
        "board": board_sample_name,
        "agent_color": agent_color,
        "outcome": outcome,
        "termination": termination_reason,
        "plies": ply,
        "duration_s": elapsed,
        "pieces_left": pieces_left,
    }


def main():
    matches = [
        # Tier 1: Baseline
        (1,  1, "Baseline", "sample0", "white"),
        (2,  1, "Baseline", "sample0", "black"),
        (3,  1, "Baseline", "sample1", "white"),
        (4,  1, "Baseline", "sample1", "black"),
        (5,  1, "Baseline", "sample2", "white"),
        (6,  1, "Baseline", "sample2", "black"),
        # Tier 2: Strong
        (7,  2, "Strong",   "sample0", "white"),
        (8,  2, "Strong",   "sample0", "black"),
        (9,  2, "Strong",   "sample1", "white"),
        (10, 2, "Strong",   "sample1", "black"),
        (11, 2, "Strong",   "sample2", "white"),
        (12, 2, "Strong",   "sample2", "black"),
        # Tier 3: Master
        (13, 3, "Master",   "sample0", "white"),
        (14, 3, "Master",   "sample0", "black"),
        (15, 3, "Master",   "sample1", "white"),
        (16, 3, "Master",   "sample1", "black"),
        (17, 3, "Master",   "sample2", "white"),
        (18, 3, "Master",   "sample2", "black"),
    ]

    print("=" * 80)
    print("  v7.8 18-GAME TOURNAMENT  |  Rule: only WIN counts")
    print("=" * 80)
    sys.stdout.flush()

    results = []
    for m in matches:
        r = play_one_game(*m)
        results.append(r)

    print("\n" + "=" * 80)
    wins   = sum(1 for r in results if r["outcome"] == "WIN")
    draws  = sum(1 for r in results if r["outcome"] == "DRAW")
    losses = sum(1 for r in results if r["outcome"] == "LOSS")
    total  = len(results)
    print(f"  FINAL: {wins}W / {draws}D / {losses}L  out of {total}")
    print(f"  Score (wins only): {wins}/{total}  ({100*wins/total:.1f}%)")

    for tier_name in ("Baseline", "Strong", "Master"):
        tr = [r for r in results if r["opp"] == tier_name]
        tw = sum(1 for r in tr if r["outcome"] == "WIN")
        td = sum(1 for r in tr if r["outcome"] == "DRAW")
        tl = sum(1 for r in tr if r["outcome"] == "LOSS")
        print(f"    {tier_name:<8s}: {tw}W {td}D {tl}L")

    out_data = {
        "engine": "v7.8-win-only-no-draws",
        "total": total, "wins": wins, "draws": draws, "losses": losses,
        "win_pct": round(100*wins/total, 1),
        "games": results,
    }
    with open("V78_TOURNAMENT_RESULTS.json", "w", encoding="utf-8") as f:
        json.dump(out_data, f, indent=2)
    print(f"\n  Saved -> V78_TOURNAMENT_RESULTS.json")
    print("=" * 80)


if __name__ == "__main__":
    main()
