"""
run_arena_benchmark.py — Multi-Tier Arena Benchmark for Chess Fragments AI
===========================================================================
COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces.

Tests our agent against four calibrated strength tiers:
  • Club Player      (~1600 Elo)
  • Candidate Master (~2100 Elo)
  • National Master  (~2350 Elo)
  • Grandmaster      (~2600 Elo)

Features:
  - Individual 300.0s player clocks (no clock bleed)
  - Multiprocessing parallelism (8 workers on multi-core CPUs)
  - Real-time logging to `arena_results.jsonl`
  - Auto-generated scorecard & report in `ARENA_REPORT.md`
"""

import sys
import os
import time
import json
import math
from itertools import cycle
from concurrent.futures import ProcessPoolExecutor, as_completed

# Framework imports
from chessmaker.chess.base import Player, Board, Square
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right import Right
from extension.piece_pawn import Pawn_Q
from extension.board_utils import copy_piece_move
from extension.board_rules import get_result, thinking_with_timeout, THINKING_TIME_BUDGET

# Opponents & Agent
from agent import agent
from stronger_opponents import club_player, candidate_master, national_master, grandmaster

INDIVIDUAL_GAME_BUDGET = 300.0


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
    elif sample_name == "sample3":
        squares = [
            [Square(Right(black)), Square(Queen(black)), Square(King(black)), Square(Right(black)), Square(Knight(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Knight(white)), Square(Right(white)), Square(King(white)), Square(Queen(white)), Square(Right(white))],
        ]
    elif sample_name == "sample4":
        squares = [
            [Square(Right(black)), Square(Bishop(black)), Square(King(black)), Square(Knight(black)), Square(Right(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Right(white)), Square(Knight(white)), Square(King(white)), Square(Bishop(white)), Square(Right(white))],
        ]
    else:
        raise ValueError(f"Unknown board sample: {sample_name}")

    board = Board(squares=squares, players=players, turn_iterator=cycle(players))
    return board, players


def play_arena_game(match_id, tier_name, opp_fn_name, board_sample_name, agent_color):
    """Executes a single game with individual 300s player clocks."""
    t_start = time.perf_counter()
    board, players = make_fresh_board(board_sample_name)
    turn_order = cycle(players)

    opp_map = {
        "club_player": club_player,
        "candidate_master": candidate_master,
        "national_master": national_master,
        "grandmaster": grandmaster,
    }
    opp_fn = opp_map[opp_fn_name]

    if agent_color == "white":
        p_white = agent
        p_black = opp_fn
    else:
        p_white = opp_fn
        p_black = agent

    clock = {"white": INDIVIDUAL_GAME_BUDGET, "black": INDIVIDUAL_GAME_BUDGET}
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
                var=[ply, THINKING_TIME_BUDGET]
            )
            board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)
        except Exception as e:
            termination_reason = f"{player.name} exception: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        move_duration = time.perf_counter() - t_move_start
        clock[player.name] -= move_duration

        if (not piece) or (not move_opt):
            res = get_result(board)
            if res:
                termination_reason = res
                res_low = res.lower()
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
                termination_reason = f"{player.name} cannot make a legal move"
                outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        try:
            piece.move(move_opt)
            ply += 1
        except Exception as e:
            termination_reason = f"{player.name} illegal move exception: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        res = get_result(board)
        if res:
            termination_reason = res
            res_low = res.lower()
            if "draw" in res_low:
                outcome = "DRAW"
            elif f"{agent_color} loses" in res_low:
                outcome = "LOSS"
            else:
                outcome = "WIN"
            break

    elapsed = round(time.perf_counter() - t_start, 1)
    pieces_left = len(list(board.get_pieces()))

    result = {
        "match_id": match_id,
        "tier": tier_name,
        "opp_fn": opp_fn_name,
        "board": board_sample_name,
        "agent_color": agent_color,
        "outcome": outcome,
        "termination": termination_reason,
        "plies": ply,
        "duration_s": elapsed,
        "pieces_left": pieces_left,
        "white_time_spent": round(INDIVIDUAL_GAME_BUDGET - clock["white"], 1),
        "black_time_spent": round(INDIVIDUAL_GAME_BUDGET - clock["black"], 1),
    }

    print(
        f"[ARENA Match {match_id:>2d}] {tier_name:<16s} | {board_sample_name} | "
        f"Agent {agent_color:>5s} -> {outcome:<4s} | {termination_reason} "
        f"({ply} plies, {elapsed}s, {pieces_left} pcs)"
    )
    sys.stdout.flush()

    # Append to jsonl
    with open("arena_results.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    return result


def generate_arena_report(results):
    total = len(results)
    if total == 0:
        return

    wins = sum(1 for r in results if r["outcome"] == "WIN")
    draws = sum(1 for r in results if r["outcome"] == "DRAW")
    losses = sum(1 for r in results if r["outcome"] == "LOSS")
    score = wins + 0.5 * draws
    score_pct = (score / total) * 100.0

    # Elo diff calculation
    s = max(0.001, min(0.999, score / total))
    elo_diff = -400.0 * math.log10((1.0 / s) - 1.0)

    # Per-tier breakdown
    tiers = {}
    for r in results:
        t = r["tier"]
        if t not in tiers:
            tiers[t] = {"wins": 0, "draws": 0, "losses": 0, "total": 0}
        tiers[t]["total"] += 1
        if r["outcome"] == "WIN": tiers[t]["wins"] += 1
        elif r["outcome"] == "DRAW": tiers[t]["draws"] += 1
        else: tiers[t]["losses"] += 1

    lines = [
        "# Chess Fragments AI Arena Benchmark Report",
        f"**Generated**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Overall Summary",
        f"- **Total Matches**: {total}",
        f"- **Score**: **{score}/{total} ({score_pct:.1f}%)**",
        f"- **Wins**: {wins} | **Draws**: {draws} | **Losses**: {losses}",
        f"- **Performance Rating Advantage**: **{'+' if elo_diff >= 0 else ''}{elo_diff:.1f} Elo**",
        "",
        "## Performance by Opponent Tier",
        "| Opponent Tier | Games | Wins | Draws | Losses | Win % | Score % |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    for t_name, stats in tiers.items():
        w, d, l, tot = stats["wins"], stats["draws"], stats["losses"], stats["total"]
        sc = (w + 0.5 * d) / tot * 100.0
        wr = w / tot * 100.0
        lines.append(f"| **{t_name}** | {tot} | {w} | {d} | {l} | {wr:.1f}% | {sc:.1f}% |")

    lines.extend([
        "",
        "## Key Match Highlights",
        "| Match | Tier | Board | Color | Outcome | Termination | Plies | Duration |",
        "|:---:|:---|:---:|:---:|:---:|:---|:---:|:---:|",
    ])

    for r in sorted(results, key=lambda x: x["match_id"]):
        lines.append(
            f"| {r['match_id']} | {r['tier']} | {r['board']} | {r['agent_color']} | "
            f"**{r['outcome']}** | {r['termination']} | {r['plies']} | {r['duration_s']}s |"
        )

    with open("ARENA_REPORT.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("Report written to ARENA_REPORT.md")


def main():
    # Define test suite: 4 tiers across sample0, sample1, sample2 (both White and Black)
    # Total = 4 tiers * 3 boards * 2 colors = 24 matches
    matches = []
    m_id = 1
    tier_configs = [
        ("Club Player (D4)", "club_player"),
        ("Candidate Master (D6)", "candidate_master"),
        ("National Master (D8)", "national_master"),
        ("Grandmaster (Mirror)", "grandmaster"),
    ]

    for tier_name, fn_name in tier_configs:
        for board_name in ["sample0", "sample1", "sample2"]:
            matches.append((m_id, tier_name, fn_name, board_name, "white"))
            m_id += 1
            matches.append((m_id, tier_name, fn_name, board_name, "black"))
            m_id += 1

    print("=" * 80)
    print(f"STARTING MULTI-TIER ARENA BENCHMARK ({len(matches)} MATCHES)")
    print("Tiers: Club Player (D4) | Candidate Master (D6) | National Master (D8) | Grandmaster")
    print("=" * 80)
    sys.stdout.flush()

    results = []
    with ProcessPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(play_arena_game, m[0], m[1], m[2], m[3], m[4]): m[0]
            for m in matches
        }
        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
            except Exception as e:
                mid = futures[future]
                print(f"Arena Match {mid} encountered error: {e}")

    generate_arena_report(results)


if __name__ == "__main__":
    main()
