"""
head_to_head_v69_vs_v79.py  (v3 — subprocess-isolated, correct board setup)
============================================================================
Runs v6.9 vs v7.9 head-to-head across all 3 board samples.

Each game runs in a FRESH subprocess so neither agent's global state
(TT, position history, _last_seen_ply) bleeds into the next game.

HOW TO RUN:
    cd "c:\\Users\\arnav\\Downloads\\CW-COMP2321-fullgame -Post Cut V5.6"
    python head_to_head_v69_vs_v79.py

Results saved to:  H2H_v69_vs_v79_results.json
Expected runtime:  ~30-45 minutes (12 games x ~2-5 min each)
"""

import sys, os, json, subprocess, time

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── Match schedule ─────────────────────────────────────────────────────────────
BOARDS = ["sample0", "sample1", "sample2"]
SCHEDULE = []
for b in BOARDS:
    SCHEDULE.append((b, "white"))   # v7.9=White, v6.9=Black
    SCHEDULE.append((b, "black"))   # v7.9=Black, v6.9=White
    SCHEDULE.append((b, "white"))   # round 2
    SCHEDULE.append((b, "black"))   # round 2
TOTAL = len(SCHEDULE)   # 12 games


# ── Single-game worker (one clean Python process per game) ────────────────────
WORKER_TEMPLATE = '''\
import sys, os, json, time
from itertools import cycle

ROOT = %(root)r
sys.path.insert(0, ROOT)

from chessmaker.chess.base  import Player, Board, Square
from chessmaker.chess.pieces import King, Bishop, Knight, Queen
from extension.piece_right   import Right
from extension.piece_pawn    import Pawn_Q
from extension.board_utils   import copy_piece_move
from extension.board_rules   import (get_result, thinking_with_timeout,
                                      THINKING_TIME_BUDGET)

import agent                     as v79_mod
import agent_v69_stalemate_guard as v69_mod

BOARD_NAME = %(board_name)r
V79_COLOR  = %(v79_color)r

# ── Board factory — every Square/piece is a fresh unique object ──────────────
def make_board(name):
    white = Player("white")
    black = Player("black")
    layouts = {
        "sample0": [
            [Square(Knight(black)), Square(Queen(black)),  Square(King(black)),
             Square(Bishop(black)), Square(Right(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)),
             Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)),
             Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Right(white)),  Square(Bishop(white)), Square(King(white)),
             Square(Queen(white)),  Square(Knight(white))],
        ],
        "sample1": [
            [Square(Right(black)),  Square(Queen(black)),  Square(King(black)),
             Square(Knight(black)), Square(Bishop(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)),
             Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)),
             Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Bishop(white)), Square(Knight(white)), Square(King(white)),
             Square(Queen(white)),  Square(Right(white))],
        ],
        "sample2": [
            [Square(Right(black)),  Square(Bishop(black)), Square(King(black)),
             Square(Queen(black)),  Square(Knight(black))],
            [Square(Pawn_Q(black)), Square(Pawn_Q(black)), Square(Pawn_Q(black)),
             Square(Pawn_Q(black)), Square(Pawn_Q(black))],
            [Square(), Square(), Square(), Square(), Square()],
            [Square(Pawn_Q(white)), Square(Pawn_Q(white)), Square(Pawn_Q(white)),
             Square(Pawn_Q(white)), Square(Pawn_Q(white))],
            [Square(Knight(white)), Square(Queen(white)),  Square(King(white)),
             Square(Bishop(white)), Square(Right(white))],
        ],
    }
    if name not in layouts:
        raise ValueError(f"Unknown board: {name}")
    board = Board(squares=layouts[name], players=[white, black],
                  turn_iterator=cycle([white, black]))
    return board

# ── Game loop ────────────────────────────────────────────────────────────────
board = make_board(BOARD_NAME)

fn_white = v79_mod.agent if V79_COLOR == "white" else v69_mod.agent
fn_black = v69_mod.agent if V79_COLOR == "white" else v79_mod.agent

players    = list(board.players)
turn_order = cycle(players)
clock      = {"white": 300.0, "black": 300.0}
ply        = 1
termination = "Unknown"
outcome     = "UNKNOWN"
t0          = time.perf_counter()

while True:
    player = next(turn_order)
    tmp    = board.clone()

    if clock[player.name] <= 0.0:
        termination = f"{player.name} clock exhausted"
        outcome = "LOSS" if player.name == V79_COLOR else "WIN"
        break

    cur_fn = fn_white if player.name == "white" else fn_black
    ts = time.perf_counter()
    try:
        pp, pm = thinking_with_timeout(
            func=cur_fn,
            thinking_time=min(THINKING_TIME_BUDGET, clock[player.name]),
            board=tmp, player=player,
            var=[ply, THINKING_TIME_BUDGET])
        board, piece, move_opt = copy_piece_move(board, pp, pm)
    except Exception as e:
        termination = f"{player.name} error: {e}"
        outcome = "LOSS" if player.name == V79_COLOR else "WIN"
        break

    clock[player.name] -= time.perf_counter() - ts

    if not piece or not move_opt:
        res = get_result(board)
        if res:
            termination = str(res)
            rl = termination.lower()
            if "draw" in rl:
                outcome = "DRAW"
            elif f"{V79_COLOR} loses" in rl:
                outcome = "LOSS"
            else:
                outcome = "WIN"
        elif pp == 99:
            termination = f"{player.name} thinking time out"
            outcome = "LOSS" if player.name == V79_COLOR else "WIN"
        else:
            termination = f"{player.name} no legal move"
            outcome = "LOSS" if player.name == V79_COLOR else "WIN"
        break

    try:
        piece.move(move_opt)
        ply += 1
    except Exception as e:
        termination = f"{player.name} move error: {e}"
        outcome = "LOSS" if player.name == V79_COLOR else "WIN"
        break

    res = get_result(board)
    if res:
        termination = str(res)
        rl = termination.lower()
        if "draw" in rl:
            outcome = "DRAW"
        elif f"{V79_COLOR} loses" in rl:
            outcome = "LOSS"
        else:
            outcome = "WIN"
        break

    if ply > 400:
        termination = "Move limit (400 plies)"
        outcome = "DRAW"
        break

elapsed = round(time.perf_counter() - t0, 1)
pcs     = len(list(board.get_pieces()))
print(json.dumps({
    "outcome_v79": outcome,
    "termination": termination,
    "plies":       ply,
    "duration_s":  elapsed,
    "pieces_left": pcs,
}))
'''


def run_game(game_num, board_name, v79_color):
    label = (f"{board_name} | v7.9="
             f"{'White' if v79_color=='white' else 'Black'}, "
             f"v6.9={'Black' if v79_color=='white' else 'White'}")

    code = WORKER_TEMPLATE % dict(root=ROOT, board_name=board_name,
                                   v79_color=v79_color)

    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, cwd=ROOT,
            timeout=900   # 15-min hard cap per game
        )
    except subprocess.TimeoutExpired:
        print(f"[{game_num:>2}/{TOTAL}] {label:<50} !! TIMEOUT after 15 min !!")
        return _err_record(game_num, board_name, v79_color, label, "timeout")

    wall = round(time.perf_counter() - t0, 1)

    # Parse last JSON line from stdout
    result = None
    for line in reversed(proc.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except Exception:
                pass

    if result is None:
        print(f"[{game_num:>2}/{TOTAL}] {label}")
        print(f"         !! SUBPROCESS ERROR ({wall}s, exit={proc.returncode}) !!")
        for ln in proc.stderr.strip().splitlines()[-8:]:
            print(f"         STDERR: {ln}")
        return _err_record(game_num, board_name, v79_color, label, "error")

    sym = {"WIN": "W", "DRAW": "D", "LOSS": "L"}.get(result["outcome_v79"], "?")
    print(
        f"[{game_num:>2}/{TOTAL}] {label:<50} "
        f"v7.9={v79_color:<5} -> {sym}  | {result['termination']} "
        f"({result['plies']} plies, {result['duration_s']}s, {result['pieces_left']} pcs)"
    )
    sys.stdout.flush()
    return {"game": game_num, "board": board_name, "v79_color": v79_color,
            "label": label, **result}


def _err_record(game_num, board_name, v79_color, label, kind):
    return {"game": game_num, "board": board_name, "v79_color": v79_color,
            "label": label, "outcome_v79": "ERROR", "termination": kind,
            "plies": 0, "duration_s": 0, "pieces_left": -1}


def main():
    print("=" * 80)
    print("  HEAD-TO-HEAD: v7.9 vs v6.9  (subprocess-isolated, fresh state per game)")
    print(f"  {TOTAL} games  |  Rule: only WIN counts  |  Perspective: v7.9")
    print("=" * 80)
    sys.stdout.flush()

    results = []
    for i, (board_name, v79_color) in enumerate(SCHEDULE, 1):
        r = run_game(i, board_name, v79_color)
        results.append(r)

    wins   = sum(1 for r in results if r["outcome_v79"] == "WIN")
    draws  = sum(1 for r in results if r["outcome_v79"] == "DRAW")
    losses = sum(1 for r in results if r["outcome_v79"] == "LOSS")
    errors = sum(1 for r in results if r["outcome_v79"] == "ERROR")

    print("\n" + "=" * 80)
    print(f"  RESULT (v7.9 perspective):  {wins}W / {draws}D / {losses}L"
          + (f" / {errors}ERR" if errors else "") + f"  out of {TOTAL}")
    print(f"  Win rate: {100*wins/TOTAL:.1f}%   Win-only score: {wins}/{TOTAL}")

    print("\n  Per board:")
    for b in BOARDS:
        br = [r for r in results if r["board"] == b]
        bw = sum(1 for r in br if r["outcome_v79"] == "WIN")
        bd = sum(1 for r in br if r["outcome_v79"] == "DRAW")
        bl = sum(1 for r in br if r["outcome_v79"] == "LOSS")
        print(f"    {b}: {bw}W {bd}D {bl}L")

    print("\n  Per colour (v7.9 playing as):")
    for col in ("white", "black"):
        cr = [r for r in results if r["v79_color"] == col]
        cw = sum(1 for r in cr if r["outcome_v79"] == "WIN")
        cd = sum(1 for r in cr if r["outcome_v79"] == "DRAW")
        cl = sum(1 for r in cr if r["outcome_v79"] == "LOSS")
        print(f"    {col}: {cw}W {cd}D {cl}L")

    print()
    if wins == TOTAL:
        print("  *** v7.9 WON EVERY GAME against v6.9. ***")
    elif wins > losses:
        print(f"  v7.9 is STRONGER: {wins}W vs {losses}L")
    elif wins == losses:
        print(f"  EVEN: {wins}W each — these boards are symmetrically balanced.")
    else:
        print(f"  v6.9 leads: v7.9 only won {wins}/{TOTAL}")
    print("=" * 80)

    out = {
        "matchup": "v7.9 vs v6.9 (subprocess-isolated v3)",
        "total_games": TOTAL,
        "wins_v79": wins, "draws": draws, "losses_v79": losses, "errors": errors,
        "win_rate_pct": round(100 * wins / TOTAL, 1),
        "games": results,
    }
    out_path = os.path.join(ROOT, "H2H_v69_vs_v79_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Results saved -> H2H_v69_vs_v79_results.json")


if __name__ == "__main__":
    main()
