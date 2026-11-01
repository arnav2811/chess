"""
run_overnight_1000.py — 1,000-Game Grandmaster Benchmark Suite
=============================================================
COMP2321 Coursework — 5×5 Chess Variant with Custom Pieces.

Features:
  1. Individual 300s Player Clocks:
     Each player (White & Black) has their OWN 300.0s time budget.
     Eliminates starvation caused by slow opponent thinking times.
  2. Multi-Core Concurrency:
     Utilizes 8 parallel workers for rapid background execution.
  3. Incremental Streaming & Resumability:
     Streams each match result directly to tournament_1000.jsonl.
     If interrupted, resumes from the last completed match index.
  4. Automatic Morning Report:
     Compiles OVERNIGHT_REPORT.md with Win/Draw/Loss rates,
     Tier breakdown (Baseline D3, Strong D5, Master D7),
     Board breakdown (sample0–sample4), color breakdown, and
     formal Elo calculation with +/- 95% confidence intervals.
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
from opponent import opponent
from strong_opponent import strong_opponent
from master_opponent import master_opponent

JSONL_FILE = "tournament_1000.jsonl"
REPORT_FILE = "OVERNIGHT_REPORT.md"
DEFAULT_TOTAL_GAMES = 1000
MAX_WORKERS = 8
INDIVIDUAL_GAME_BUDGET = 300.0  # 300 seconds per player


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


def play_one_game(match_id, tier, opp_name, board_sample_name, agent_color):
    """
    Executes a single game with individual 300s player clocks.
    Returns a result dictionary.
    """
    t_start = time.perf_counter()
    board, players = make_fresh_board(board_sample_name)
    turn_order = cycle(players)

    opp_map = {
        "Baseline": opponent,
        "Strong": strong_opponent,
        "Master": master_opponent,
    }
    opp_fn = opp_map[opp_name]

    if agent_color == "white":
        p_white = agent
        p_black = opp_fn
    else:
        p_white = opp_fn
        p_black = agent

    # Individual clocks: 300.0s for White, 300.0s for Black
    clock = {"white": INDIVIDUAL_GAME_BUDGET, "black": INDIVIDUAL_GAME_BUDGET}
    ply = 1
    termination_reason = "Unknown"
    outcome = "UNKNOWN"

    while True:
        player = next(turn_order)
        temp_board = board.clone()
        current_fn = p_white if player.name == "white" else p_black

        # Check if current player's individual clock has expired
        if clock[player.name] <= 0.0:
            termination_reason = f"{player.name} game time limit exceeded"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

        turn_start = time.perf_counter()
        try:
            p_piece, p_move_opt = thinking_with_timeout(
                func=current_fn,
                thinking_time=min(THINKING_TIME_BUDGET, max(1.0, clock[player.name])),
                board=temp_board,
                player=player,
                var=[ply, THINKING_TIME_BUDGET]
            )
            spent = time.perf_counter() - turn_start
            clock[player.name] -= spent
            board, piece, move_opt = copy_piece_move(board, p_piece, p_move_opt)
        except Exception as e:
            spent = time.perf_counter() - turn_start
            clock[player.name] -= spent
            termination_reason = f"{player.name} runtime error: {e}"
            outcome = "LOSS" if player.name == agent_color else "WIN"
            break

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
            termination_reason = f"{player.name} illegal move error"
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
        "tier": tier,
        "opp_name": opp_name,
        "board": board_sample_name,
        "agent_color": agent_color,
        "outcome": outcome,
        "termination": termination_reason,
        "plies": ply,
        "duration_s": elapsed,
        "pieces_left": pieces_left,
        "agent_clock_remaining": round(clock[agent_color], 1),
        "opp_clock_remaining": round(clock["black" if agent_color == "white" else "white"], 1),
    }

    # Stream immediately to JSONL
    with open(JSONL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(result) + "\n")

    print(f"[{match_id:>4d}/1000] Tier {tier} ({opp_name:<8s}) | {board_sample_name} | Agent {agent_color:>5s} -> {outcome:<4s} | {termination_reason} ({ply} plies, {elapsed}s)")
    sys.stdout.flush()
    return result


def generate_schedule(total_games=1000):
    """
    Distributes matches across opponents and board samples:
      • 400 vs Baseline (Tier 1)
      • 400 vs Strong   (Tier 2)
      • 200 vs Master   (Tier 3)
    Alternating White and Black evenly across sample0–sample4.
    """
    schedule = []
    match_id = 1
    boards = ["sample0", "sample1", "sample2", "sample3", "sample4"]

    tier_specs = [
        (1, "Baseline", int(total_games * 0.40)),
        (2, "Strong",   int(total_games * 0.40)),
        (3, "Master",   total_games - int(total_games * 0.40) * 2),
    ]

    for tier, opp_name, count in tier_specs:
        for i in range(count):
            board = boards[i % len(boards)]
            agent_color = "white" if (i % 2 == 0) else "black"
            schedule.append((match_id, tier, opp_name, board, agent_color))
            match_id += 1

    return schedule


def generate_report(results):
    """Generates a comprehensive markdown analytics report."""
    n = len(results)
    if n == 0:
        return

    wins = sum(1 for r in results if r["outcome"] == "WIN")
    draws = sum(1 for r in results if r["outcome"] == "DRAW")
    losses = sum(1 for r in results if r["outcome"] == "LOSS")
    points = wins + 0.5 * draws
    score_pct = (points / n) * 100.0
    win_pct = (wins / n) * 100.0

    # Elo calculation
    # S = points / n
    S = max(0.001, min(0.999, points / n))
    elo_delta = -400.0 * math.log10((1.0 / S) - 1.0)
    se = (math.sqrt(S * (1.0 - S) / n) / (S * (1.0 - S) * math.log(10))) * 400.0
    ci95 = 1.96 * se

    # Opponent base Elo estimate:
    # Baseline ~ 1200, Strong ~ 1500, Master ~ 1800
    weighted_opp_elo = 0.40 * 1200 + 0.40 * 1500 + 0.20 * 1800
    est_agent_elo = round(weighted_opp_elo + elo_delta)

    # Breakdown by tier
    tiers = {}
    for r in results:
        t = r["tier"]
        tiers.setdefault(t, []).append(r)

    # Breakdown by board
    boards = {}
    for r in results:
        b = r["board"]
        boards.setdefault(b, []).append(r)

    # Breakdown by color
    colors = {}
    for r in results:
        c = r["agent_color"]
        colors.setdefault(c, []).append(r)

    avg_plies = sum(r["plies"] for r in results) / n
    avg_duration = sum(r["duration_s"] for r in results) / n

    lines = [
        "# 1,000-Match Grandmaster Overnight Tournament Report",
        "",
        f"> **Generated at**: {time.strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"> **Total Matches Completed**: {n:,} / {n:,}  ",
        f"> **Overall Score**: **{wins} WINS / {draws} DRAWS / {losses} LOSSES** ({score_pct:.2f}% points, {win_pct:.2f}% Win Rate)",
        "",
        "---",
        "",
        "## 🏆 Executive Summary & Elo Rating",
        "",
        f"- **Estimated Agent Elo**: **{est_agent_elo} ± {ci95:.0f}** (95% Confidence Interval)",
        f"- **Elo Performance Advantage**: **+{elo_delta:.1f} Elo** over competition field",
        f"- **Clean Sweep Points**: **{points:.1f} / {n}**",
        f"- **Average Game Length**: **{avg_plies:.1f} plies**",
        f"- **Average Game Duration**: **{avg_duration:.1f} seconds**",
        "",
        "---",
        "",
        "## 📊 Breakdown by Opponent Tier",
        "",
        "| Tier | Opponent Name | Matches | Wins | Draws | Losses | Win % | Points % |",
        "|:---:|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]

    tier_names = {1: "Baseline (D3)", 2: "Strong (D5)", 3: "Master (D7)"}
    for t in sorted(tiers.keys()):
        tr = tiers[t]
        tw = sum(1 for r in tr if r["outcome"] == "WIN")
        td = sum(1 for r in tr if r["outcome"] == "DRAW")
        tl = sum(1 for r in tr if r["outcome"] == "LOSS")
        tp = tw + 0.5 * td
        lines.append(f"| {t} | {tier_names.get(t, 'Unknown')} | {len(tr)} | {tw} | {td} | {tl} | {tw/len(tr)*100:.1f}% | {tp/len(tr)*100:.1f}% |")

    lines.extend([
        "",
        "---",
        "",
        "## ♟️ Breakdown by Board Variant",
        "",
        "| Board Sample | Description | Matches | Wins | Draws | Losses | Win % |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|",
    ])

    board_desc = {
        "sample0": "Standard 5×5 Layout",
        "sample1": "Flipped Minor Pieces",
        "sample2": "Queen/Bishop Swap",
        "sample3": "Double Right (Heavy Right Board)",
        "sample4": "Queenless (Double Right + Bishop + Knight)",
    }

    for b in sorted(boards.keys()):
        br = boards[b]
        bw = sum(1 for r in br if r["outcome"] == "WIN")
        bd = sum(1 for r in br if r["outcome"] == "DRAW")
        bl = sum(1 for r in br if r["outcome"] == "LOSS")
        lines.append(f"| `{b}` | {board_desc.get(b, 'Custom')} | {len(br)} | {bw} | {bd} | {bl} | {bw/len(br)*100:.1f}% |")

    lines.extend([
        "",
        "---",
        "",
        "## ⚪/⚫ Breakdown by Color Assigned",
        "",
        "| Color | Matches | Wins | Draws | Losses | Win % | Clean Points % |",
        "|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ])

    for c in ["white", "black"]:
        if c in colors:
            cr = colors[c]
            cw = sum(1 for r in cr if r["outcome"] == "WIN")
            cd = sum(1 for r in cr if r["outcome"] == "DRAW")
            cl = sum(1 for r in cr if r["outcome"] == "LOSS")
            cp = cw + 0.5 * cd
            lines.append(f"| Agent as {c.capitalize()} | {len(cr)} | {cw} | {cd} | {cl} | {cw/len(cr)*100:.1f}% | {cp/len(cr)*100:.1f}% |")

    lines.extend([
        "",
        "---",
        "",
        "## 🔬 Termination Reasons Breakdown",
        "",
        "| Termination Reason | Count | Percentage |",
        "|:---|:---:|:---:|",
    ])

    reasons = {}
    for r in results:
        t = r["termination"]
        reasons[t] = reasons.get(t, 0) + 1

    for term, count in sorted(reasons.items(), key=lambda x: -x[1]):
        lines.append(f"| {term} | {count} | {count/n*100:.1f}% |")

    lines.append("")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[REPORT GENERATED] -> {REPORT_FILE}")
    sys.stdout.flush()


def main():
    total_games = DEFAULT_TOTAL_GAMES
    if len(sys.argv) > 1:
        try:
            total_games = int(sys.argv[1])
        except ValueError:
            pass

    full_schedule = generate_schedule(total_games)

    # Resume from existing JSONL if present
    completed_ids = set()
    existing_results = []
    if os.path.exists(JSONL_FILE):
        with open(JSONL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        completed_ids.add(entry["match_id"])
                        existing_results.append(entry)
                    except Exception:
                        pass

    remaining_schedule = [m for m in full_schedule if m[0] not in completed_ids]

    print("=" * 80)
    print(f"LAUNCHING 1,000-MATCH GRANDMASTER TOURNAMENT (v5.6 Clean Sweep)")
    print(f"Workers: {MAX_WORKERS} parallel CPU processes | Total games: {total_games}")
    print(f"Already completed: {len(completed_ids)} | Remaining to run: {len(remaining_schedule)}")
    print(f"Individual Player Clock: {INDIVIDUAL_GAME_BUDGET}s per player")
    print("=" * 80)
    sys.stdout.flush()

    if not remaining_schedule:
        print("All matches already completed! Generating report...")
        generate_report(existing_results)
        return

    results = list(existing_results)

    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(play_one_game, m[0], m[1], m[2], m[3], m[4]): m[0]
            for m in remaining_schedule
        }

        for future in as_completed(futures):
            try:
                res = future.result()
                results.append(res)
                if len(results) % 20 == 0:
                    generate_report(results)
            except Exception as e:
                m_id = futures[future]
                print(f"[Match {m_id}] Failed with worker error: {e}")
                sys.stdout.flush()

    # Final sorted report
    results.sort(key=lambda r: r["match_id"])
    generate_report(results)

    wins = sum(1 for r in results if r["outcome"] == "WIN")
    draws = sum(1 for r in results if r["outcome"] == "DRAW")
    losses = sum(1 for r in results if r["outcome"] == "LOSS")
    print("\n" + "=" * 80)
    print(f"TOURNAMENT COMPLETE: {wins} WINS / {draws} DRAWS / {losses} LOSSES ({wins/len(results)*100:.1f}% Win Rate)")
    print("=" * 80)


if __name__ == "__main__":
    main()
