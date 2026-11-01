#!/usr/bin/env python3
"""
5x5 Chess Fragments — Endgame Tablebase Generator
==================================================
Standalone script. Run once to pre-compute perfect endgame play.
Saves checkpoints so it survives interruptions.

Usage:  python generate_tablebase.py
Output: endgame_tb_snippet.py  (paste into agent.py)
        tb_checkpoint.pkl      (resume checkpoint)

Estimated time: 3-piece ~5 min, 4-piece ~3-5 hours (CPython)
"""

import sys, time, zlib, base64, pickle, os
from collections import deque

# ============================================================================
# Constants
# ============================================================================
EMPTY = 0
KING = 1; QUEEN = 2; RIGHT = 3; KNIGHT = 4; BISHOP = 5; PAWN = 6
WHITE = 0; BLACK = 1

# Result codes stored in tablebase
UNKNOWN = 0; TB_WIN = 1; TB_LOSS = 2; TB_DRAW = 3; ILLEGAL = 255

PIECE_NAMES = {QUEEN:'queen', RIGHT:'right', KNIGHT:'knight', BISHOP:'bishop', PAWN:'pawn'}
PIECE_SYMBOLS = {QUEEN:'Q', RIGHT:'Ri', KNIGHT:'N', BISHOP:'B', PAWN:'P'}
COLOR_CHAR = {WHITE:'W', BLACK:'B'}

# Move offsets
KING_OFF   = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
KNIGHT_OFF = [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]
ROOK_DIR   = [(0,1),(0,-1),(1,0),(-1,0)]
BISHOP_DIR = [(1,1),(1,-1),(-1,1),(-1,-1)]

TABLE_3 = 25 * 25 * 25 * 2   # 31,250
TABLE_4 = 25 * 25 * 25 * 25 * 2  # 781,250

CHECKPOINT_FILE = "tb_checkpoint.pkl"
OUTPUT_FILE     = "endgame_tb_snippet.py"

# ============================================================================
# Helpers
# ============================================================================
def sq2xy(s):       return s % 5, s // 5
def xy2sq(x, y):    return y * 5 + x
def inb(x, y):      return 0 <= x < 5 and 0 <= y < 5

def enc3(wk, bk, p1, stm):         return wk*1250 + bk*50 + p1*2 + stm
def enc4(wk, bk, p1, p2, stm):     return wk*31250 + bk*1250 + p1*50 + p2*2 + stm

# ============================================================================
# Attack detection — is 'target' square attacked by any piece of 'by_color'?
# ============================================================================
def attacked(board, target, by_color):
    tx, ty = sq2xy(target)
    sgn = 1 if by_color == WHITE else -1

    # King
    for dx, dy in KING_OFF:
        nx, ny = tx+dx, ty+dy
        if inb(nx, ny) and board[xy2sq(nx,ny)] == sgn*KING:
            return True

    # Knight / Right (knight component)
    for dx, dy in KNIGHT_OFF:
        nx, ny = tx+dx, ty+dy
        if inb(nx, ny):
            p = board[xy2sq(nx,ny)]
            if p == sgn*KNIGHT or p == sgn*RIGHT:
                return True

    # Rook rays (Right rook part + Queen)
    for dx, dy in ROOK_DIR:
        nx, ny = tx+dx, ty+dy
        while inb(nx, ny):
            p = board[xy2sq(nx,ny)]
            if p != EMPTY:
                if p == sgn*RIGHT or p == sgn*QUEEN:
                    return True
                break
            nx += dx; ny += dy

    # Bishop rays (Bishop + Queen)
    for dx, dy in BISHOP_DIR:
        nx, ny = tx+dx, ty+dy
        while inb(nx, ny):
            p = board[xy2sq(nx,ny)]
            if p != EMPTY:
                if p == sgn*BISHOP or p == sgn*QUEEN:
                    return True
                break
            nx += dx; ny += dy

    # Pawn captures (attack squares, not move squares)
    if by_color == WHITE:
        # White pawn at (tx±1, ty+1) attacks (tx, ty)
        for dx in (-1, 1):
            px, py = tx+dx, ty+1
            if inb(px, py) and board[xy2sq(px,py)] == PAWN:
                return True
    else:
        # Black pawn at (tx±1, ty-1) attacks (tx, ty)
        for dx in (-1, 1):
            px, py = tx+dx, ty-1
            if inb(px, py) and board[xy2sq(px,py)] == -PAWN:
                return True

    return False

# ============================================================================
# Legal move generation
# Returns list of (from_sq, to_sq, is_promotion) — only truly legal moves
# ============================================================================
def gen_legal(board, stm):
    sgn = 1 if stm == WHITE else -1
    opp = 1 - stm

    # Find our king
    my_king = -1
    for s in range(25):
        if board[s] == sgn*KING:
            my_king = s
            break
    if my_king < 0:
        return []

    legal = []
    for s in range(25):
        p = board[s]
        if p == EMPTY or (p > 0) != (sgn > 0):
            continue
        pt = abs(p)
        x, y = sq2xy(s)
        targets = []

        if pt == KING:
            for dx, dy in KING_OFF:
                nx, ny = x+dx, y+dy
                if inb(nx, ny):
                    t = board[xy2sq(nx,ny)]
                    if t == EMPTY or (t > 0) != (sgn > 0):
                        targets.append((xy2sq(nx,ny), False))

        elif pt == KNIGHT:
            for dx, dy in KNIGHT_OFF:
                nx, ny = x+dx, y+dy
                if inb(nx, ny):
                    t = board[xy2sq(nx,ny)]
                    if t == EMPTY or (t > 0) != (sgn > 0):
                        targets.append((xy2sq(nx,ny), False))

        elif pt == BISHOP:
            for dx, dy in BISHOP_DIR:
                nx, ny = x+dx, y+dy
                while inb(nx, ny):
                    t = board[xy2sq(nx,ny)]
                    if t == EMPTY:
                        targets.append((xy2sq(nx,ny), False))
                    elif (t > 0) != (sgn > 0):
                        targets.append((xy2sq(nx,ny), False)); break
                    else: break
                    nx += dx; ny += dy

        elif pt == RIGHT:
            # Knight moves
            for dx, dy in KNIGHT_OFF:
                nx, ny = x+dx, y+dy
                if inb(nx, ny):
                    t = board[xy2sq(nx,ny)]
                    if t == EMPTY or (t > 0) != (sgn > 0):
                        targets.append((xy2sq(nx,ny), False))
            # Rook moves
            for dx, dy in ROOK_DIR:
                nx, ny = x+dx, y+dy
                while inb(nx, ny):
                    t = board[xy2sq(nx,ny)]
                    if t == EMPTY:
                        targets.append((xy2sq(nx,ny), False))
                    elif (t > 0) != (sgn > 0):
                        targets.append((xy2sq(nx,ny), False)); break
                    else: break
                    nx += dx; ny += dy

        elif pt == QUEEN:
            for dx, dy in BISHOP_DIR + ROOK_DIR:
                nx, ny = x+dx, y+dy
                while inb(nx, ny):
                    t = board[xy2sq(nx,ny)]
                    if t == EMPTY:
                        targets.append((xy2sq(nx,ny), False))
                    elif (t > 0) != (sgn > 0):
                        targets.append((xy2sq(nx,ny), False)); break
                    else: break
                    nx += dx; ny += dy

        elif pt == PAWN:
            direction = -1 if stm == WHITE else 1
            ny = y + direction
            if inb(x, ny):
                promo = (stm == WHITE and ny == 0) or (stm == BLACK and ny == 4)
                # Forward (non-capture)
                if board[xy2sq(x, ny)] == EMPTY:
                    targets.append((xy2sq(x, ny), promo))
                # Diagonal captures
                for dx in (-1, 1):
                    nx2 = x + dx
                    if inb(nx2, ny):
                        t = board[xy2sq(nx2, ny)]
                        if t != EMPTY and (t > 0) != (sgn > 0):
                            targets.append((xy2sq(nx2, ny), promo))

        # Filter: move must not leave our king in check
        for to_sq, promo in targets:
            if abs(board[to_sq]) == KING:
                continue  # can't capture king in legal play
            nb = list(board)
            nb[s] = EMPTY
            nb[to_sq] = sgn*QUEEN if promo else p
            nk = to_sq if pt == KING else my_king
            if not attacked(nb, nk, opp):
                legal.append((s, to_sq, promo))

    return legal


def apply_move(board, fs, ts, promo):
    nb = list(board)
    p = nb[fs]
    sgn = 1 if p > 0 else -1
    nb[fs] = EMPTY
    nb[ts] = sgn*QUEEN if promo else p
    return nb


def get_material(board):
    """Extract sorted material tuple from board (excludes kings)."""
    extra = []
    for s in range(25):
        p = board[s]
        if p != EMPTY and abs(p) != KING:
            extra.append((abs(p), WHITE if p > 0 else BLACK))
    extra.sort()
    return tuple(extra)


# ============================================================================
# Build board from material config + piece squares
# ============================================================================
def build3(mc, wk, bk, p1):
    b = [EMPTY]*25
    b[wk] = KING; b[bk] = -KING
    pt, pc = mc[0]
    b[p1] = (1 if pc == WHITE else -1) * pt
    return b

def build4(mc, wk, bk, p1, p2):
    b = [EMPTY]*25
    b[wk] = KING; b[bk] = -KING
    pt1, pc1 = mc[0]; b[p1] = (1 if pc1 == WHITE else -1) * pt1
    pt2, pc2 = mc[1]; b[p2] = (1 if pc2 == WHITE else -1) * pt2
    return b


def lookup_ext(solved, mat_key, board, stm):
    """Look up result in a previously solved table."""
    if not mat_key:
        return TB_DRAW  # K vs K
    if mat_key not in solved:
        return TB_DRAW  # not yet computed — treat as draw (conservative)
    table = solved[mat_key]
    wk = bk = -1
    ex = []
    for s in range(25):
        p = board[s]
        if p == KING:    wk = s
        elif p == -KING: bk = s
        elif p != EMPTY:
            ex.append((abs(p), WHITE if p > 0 else BLACK, s))
    if wk < 0 or bk < 0:
        return TB_DRAW
    ex.sort()
    sqs = [s for _, _, s in ex]
    if len(sqs) == 1:
        idx = enc3(wk, bk, sqs[0], stm)
    elif len(sqs) == 2:
        idx = enc4(wk, bk, sqs[0], sqs[1], stm)
    else:
        return TB_DRAW
    if idx >= len(table):
        return TB_DRAW
    r = table[idx]
    if r == UNKNOWN or r == ILLEGAL:
        return TB_DRAW
    return r


def config_name(mc):
    parts = []
    for pt, pc in mc:
        parts.append(f"{COLOR_CHAR[pc]}{PIECE_SYMBOLS[pt]}")
    return "K" + "+".join(parts) + "vK"


# ============================================================================
# Solve one material configuration
# ============================================================================
def solve(mc, solved, is4=False):
    name = config_name(mc)
    tsize = TABLE_4 if is4 else TABLE_3
    print(f"\n{'='*60}")
    print(f"  Solving {name}  ({'4-piece' if is4 else '3-piece'})")
    print(f"  Table size: {tsize:,} entries")
    print(f"{'='*60}")
    sys.stdout.flush()

    result = bytearray(tsize)
    preds = {}       # succ_idx -> [pred_idx, ...]
    remaining = {}   # idx -> count of successors NOT yet proven WIN for opponent
    loss_q = deque()
    win_q  = deque()

    t0 = time.perf_counter()
    legal_cnt = 0
    scan_cnt = 0
    same_piece = is4 and mc[0] == mc[1]

    for wk in range(25):
        if (wk % 5 == 0):
            elapsed = time.perf_counter() - t0
            pct = wk / 25 * 100
            print(f"    wk={wk}/24  ({pct:.0f}%)  legal={legal_cnt:,}  "
                  f"elapsed={elapsed:.1f}s", end='\r')
            sys.stdout.flush()

        for bk in range(25):
            if bk == wk:
                continue

            avail = [s for s in range(25) if s != wk and s != bk]

            if is4:
                pairs = []
                for i in range(len(avail)):
                    start_j = i + 1 if same_piece else 0
                    for j in range(start_j, len(avail)):
                        if i == j:
                            continue
                        pairs.append((avail[i], avail[j]))
            else:
                pairs = [(a,) for a in avail]

            for extras in pairs:
                for stm in (WHITE, BLACK):
                    scan_cnt += 1

                    if is4:
                        p1, p2 = extras
                        idx = enc4(wk, bk, p1, p2, stm)
                        board = build4(mc, wk, bk, p1, p2)
                    else:
                        p1 = extras[0]
                        idx = enc3(wk, bk, p1, stm)
                        board = build3(mc, wk, bk, p1)

                    # Pawn on promotion rank → illegal
                    pawn_bad = False
                    for pi, (pt, pc) in enumerate(mc):
                        if pt == PAWN:
                            psq = extras[pi] if is4 else extras[0]
                            _, py = sq2xy(psq)
                            if (pc == WHITE and py == 0) or (pc == BLACK and py == 4):
                                pawn_bad = True; break
                    if pawn_bad:
                        result[idx] = ILLEGAL; continue

                    # Side-not-to-move in check → illegal
                    opp = 1 - stm
                    opp_king = bk if opp == BLACK else wk
                    if attacked(board, opp_king, stm):
                        result[idx] = ILLEGAL; continue

                    legal_cnt += 1
                    moves = gen_legal(board, stm)

                    if not moves:
                        result[idx] = TB_LOSS
                        loss_q.append(idx)
                        continue

                    n_not_win = len(moves)
                    found_win = False

                    for fs, ts, promo in moves:
                        sb = apply_move(board, fs, ts, promo)
                        ss = 1 - stm
                        sm = get_material(sb)

                        if sm == mc:
                            # Internal edge — successor in same table
                            swk = sbk = -1
                            se = []
                            for s in range(25):
                                sp = sb[s]
                                if sp == KING: swk = s
                                elif sp == -KING: sbk = s
                                elif sp != EMPTY:
                                    se.append((abs(sp), WHITE if sp > 0 else BLACK, s))
                            se.sort()
                            sx = [s for _, _, s in se]
                            if is4 and len(sx) == 2:
                                si = enc4(swk, sbk, sx[0], sx[1], ss)
                            elif not is4 and len(sx) == 1:
                                si = enc3(swk, sbk, sx[0], ss)
                            else:
                                continue
                            if si not in preds:
                                preds[si] = []
                            preds[si].append(idx)
                        else:
                            # External edge — lookup in solved tables
                            er = lookup_ext(solved, sm, sb, ss)
                            if er == TB_LOSS:
                                found_win = True
                            elif er == TB_WIN:
                                n_not_win -= 1

                    if found_win:
                        result[idx] = TB_WIN
                        win_q.append(idx)
                    else:
                        remaining[idx] = n_not_win
                        if n_not_win == 0:
                            result[idx] = TB_LOSS
                            loss_q.append(idx)

    t1 = time.perf_counter()
    print(f"\n    Phase 1 done: {legal_cnt:,} legal positions, "
          f"{len(loss_q):,} initial LOSS, {len(win_q):,} initial WIN  "
          f"({t1-t0:.1f}s)")
    sys.stdout.flush()

    # BFS propagation
    iters = 0
    while loss_q or win_q:
        while loss_q:
            si = loss_q.popleft()
            iters += 1
            for pi in preds.get(si, []):
                if result[pi] == UNKNOWN:
                    result[pi] = TB_WIN
                    win_q.append(pi)

        batch = []
        while win_q:
            batch.append(win_q.popleft())
        for si in batch:
            iters += 1
            for pi in preds.get(si, []):
                if result[pi] == UNKNOWN:
                    remaining[pi] -= 1
                    if remaining[pi] == 0:
                        result[pi] = TB_LOSS
                        loss_q.append(pi)

    # Remaining UNKNOWN → DRAW
    for i in range(tsize):
        if result[i] == UNKNOWN:
            result[i] = TB_DRAW

    t2 = time.perf_counter()
    w = sum(1 for x in result if x == TB_WIN)
    l = sum(1 for x in result if x == TB_LOSS)
    d = sum(1 for x in result if x == TB_DRAW)
    il = sum(1 for x in result if x == ILLEGAL)
    print(f"    BFS: {iters:,} iterations ({t2-t1:.1f}s)")
    print(f"    Results: WIN={w:,}  LOSS={l:,}  DRAW={d:,}  ILLEGAL={il:,}")
    print(f"    Total time for {name}: {t2-t0:.1f}s")
    sys.stdout.flush()

    # Free predecessor graph
    del preds
    del remaining

    return bytes(result)


# ============================================================================
# Material configuration enumeration (dependency-ordered)
# ============================================================================
def build_config_order():
    """Return list of material configs in dependency order."""
    non_pawn = [(pt, pc) for pt in [QUEEN, RIGHT, KNIGHT, BISHOP]
                         for pc in [WHITE, BLACK]]
    pawn_pcs = [(PAWN, pc) for pc in [WHITE, BLACK]]
    all_pcs  = non_pawn + pawn_pcs  # 10 items total

    # 3-piece (1 extra piece)
    three_np = [((p,),) for p in non_pawn]      # 8 configs
    three_p  = [((p,),) for p in pawn_pcs]       # 2 configs

    # 4-piece (2 extra pieces) — choose pairs (i <= j)
    four_np = []; four_1p = []; four_2p = []
    for i in range(len(all_pcs)):
        for j in range(i, len(all_pcs)):
            c = (all_pcs[i], all_pcs[j])
            npawns = sum(1 for pt, _ in c if pt == PAWN)
            if npawns == 0:   four_np.append(c)
            elif npawns == 1: four_1p.append(c)
            else:             four_2p.append(c)

    # Flatten 3-piece configs (they were double-wrapped)
    three_np = [c[0] for c in three_np]
    three_p  = [c[0] for c in three_p]

    order = []
    # 1) 3-piece non-pawn
    for mc in three_np: order.append((mc, False))
    # 2) 3-piece pawn (promotions → non-pawn 3-piece)
    for mc in three_p:  order.append((mc, False))
    # 3) 4-piece non-pawn
    for mc in four_np:  order.append((mc, True))
    # 4) 4-piece 1-pawn (promotions → non-pawn 4-piece)
    for mc in four_1p:  order.append((mc, True))
    # 5) 4-piece 2-pawn (promotions → 1-pawn 4-piece)
    for mc in four_2p:  order.append((mc, True))

    return order


# ============================================================================
# Checkpoint save/load
# ============================================================================
def save_checkpoint(solved, completed_names):
    with open(CHECKPOINT_FILE, 'wb') as f:
        pickle.dump({'solved': solved, 'completed': completed_names}, f)
    print(f"    [checkpoint saved: {len(completed_names)} tables]")

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, 'rb') as f:
            data = pickle.load(f)
        print(f"Resuming from checkpoint: {len(data['completed'])} tables already done")
        return data['solved'], set(data['completed'])
    return {}, set()


# ============================================================================
# Output generation — create Python snippet for agent.py
# ============================================================================
def generate_output(solved):
    """Compress tablebase data and write Python code snippet."""
    # Serialize
    raw = pickle.dumps(solved, protocol=pickle.HIGHEST_PROTOCOL)
    compressed = zlib.compress(raw, 9)
    encoded = base64.b64encode(compressed)

    raw_mb = len(raw) / (1024*1024)
    comp_mb = len(compressed) / (1024*1024)
    enc_mb = len(encoded) / (1024*1024)

    print(f"\nSerialization:")
    print(f"  Raw:        {raw_mb:.2f} MB")
    print(f"  Compressed: {comp_mb:.2f} MB")
    print(f"  Base64:     {enc_mb:.2f} MB")

    # Write Python snippet file
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write('# ============================================================\n')
        f.write('# Endgame Tablebase Data (auto-generated)\n')
        f.write(f'# {len(solved)} material configurations\n')
        f.write(f'# Compressed size: {comp_mb:.2f} MB\n')
        f.write('# ============================================================\n')
        f.write('import zlib as _zlib, base64 as _b64, pickle as _pkl\n\n')

        # Write data in chunks (avoid huge single line)
        f.write('_TB_DATA = (\n')
        chunk_size = 76  # base64 line length
        for i in range(0, len(encoded), chunk_size):
            chunk = encoded[i:i+chunk_size]
            f.write(f'    b"{chunk.decode()}"\n')
        f.write(')\n\n')

        f.write('# Result codes\n')
        f.write('_TB_WIN = 1; _TB_LOSS = 2; _TB_DRAW = 3\n')
        f.write('_TB_TYPE_MAP = {"queen":2,"right":3,"knight":4,"bishop":5,"pawn":6}\n\n')

        f.write('# Decompress on module load\n')
        f.write('_ENDGAME_TB = {}\n')
        f.write('def _init_endgame_tb():\n')
        f.write('    global _ENDGAME_TB\n')
        f.write('    try:\n')
        f.write('        raw = _zlib.decompress(_b64.b64decode(_TB_DATA))\n')
        f.write('        _ENDGAME_TB = _pkl.loads(raw)\n')
        f.write('    except Exception:\n')
        f.write('        _ENDGAME_TB = {}\n')
        f.write('_init_endgame_tb()\n\n')

        f.write('def _probe_endgame_tb(board, _pn_func):\n')
        f.write('    """Probe endgame tablebase. Returns (hit, score_for_stm)."""\n')
        f.write('    pcs = []\n')
        f.write('    for p in board.get_pieces():\n')
        f.write('        pcs.append(p)\n')
        f.write('        if len(pcs) > 4: return False, 0\n')
        f.write('    n = len(pcs)\n')
        f.write('    if n < 2: return False, 0\n')
        f.write('    if n == 2: return True, 0  # K vs K = draw\n')
        f.write('    wk = bk = -1\n')
        f.write('    extra = []\n')
        f.write('    for p in pcs:\n')
        f.write('        nm = _pn_func(p)\n')
        f.write('        sq = p.position.y * 5 + p.position.x\n')
        f.write('        if nm == "king":\n')
        f.write('            if p.player.name == "white": wk = sq\n')
        f.write('            else: bk = sq\n')
        f.write('        else:\n')
        f.write('            pt = _TB_TYPE_MAP.get(nm, 0)\n')
        f.write('            pc = 0 if p.player.name == "white" else 1\n')
        f.write('            extra.append((pt, pc, sq))\n')
        f.write('    if wk < 0 or bk < 0: return False, 0\n')
        f.write('    extra.sort()\n')
        f.write('    mk = tuple((t,c) for t,c,s in extra)\n')
        f.write('    if mk not in _ENDGAME_TB: return False, 0\n')
        f.write('    tbl = _ENDGAME_TB[mk]\n')
        f.write('    stm = 0 if board.current_player.name == "white" else 1\n')
        f.write('    ne = len(extra)\n')
        f.write('    if ne == 1:\n')
        f.write('        idx = wk*1250 + bk*50 + extra[0][2]*2 + stm\n')
        f.write('    elif ne == 2:\n')
        f.write('        idx = wk*31250 + bk*1250 + extra[0][2]*50 + extra[1][2]*2 + stm\n')
        f.write('    else: return False, 0\n')
        f.write('    if idx >= len(tbl): return False, 0\n')
        f.write('    r = tbl[idx]\n')
        f.write('    if r == _TB_WIN:  return True,  95000\n')
        f.write('    if r == _TB_LOSS: return True, -95000\n')
        f.write('    if r == _TB_DRAW: return True,  0\n')
        f.write('    return False, 0\n')

    print(f"\nOutput written to: {OUTPUT_FILE}")
    print(f"  Paste its contents into agent.py to enable tablebase probing.")


# ============================================================================
# Validation
# ============================================================================
def validate(solved):
    """Quick sanity checks on computed tables."""
    print("\n" + "="*60)
    print("  Validation")
    print("="*60)

    checks = [
        # (mat_key, description, expected_majority)
        ((QUEEN, WHITE),),
        ((RIGHT, WHITE),),
        ((KNIGHT, WHITE),),
        ((BISHOP, WHITE),),
        ((PAWN, WHITE),),
    ]

    for mc_tuple in checks:
        mc = mc_tuple[0] if len(mc_tuple) == 1 and isinstance(mc_tuple[0], tuple) else mc_tuple
        if isinstance(mc[0], int):
            mc = (mc,)
        if mc not in solved:
            continue
        table = solved[mc]
        w = sum(1 for x in table if x == TB_WIN)
        l = sum(1 for x in table if x == TB_LOSS)
        d = sum(1 for x in table if x == TB_DRAW)
        legal = w + l + d
        name = config_name(mc)
        if legal > 0:
            wp = w/legal*100
            lp = l/legal*100
            dp = d/legal*100
            print(f"  {name:20s}  WIN={wp:5.1f}%  LOSS={lp:5.1f}%  DRAW={dp:5.1f}%  (n={legal:,})")
        else:
            print(f"  {name:20s}  no legal positions!")


# ============================================================================
# Main
# ============================================================================
def main():
    print("="*60)
    print("  5x5 Chess Fragments — Endgame Tablebase Generator")
    print("="*60)
    print(f"  Python {sys.version.split()[0]}")
    print(f"  Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    solved, completed = load_checkpoint()
    config_order = build_config_order()

    total = len(config_order)
    print(f"Total material configurations to solve: {total}")
    print(f"  3-piece: {sum(1 for _,is4 in config_order if not is4)}")
    print(f"  4-piece: {sum(1 for _,is4 in config_order if is4)}")
    if completed:
        print(f"  Already completed: {len(completed)}")
    print()

    overall_start = time.perf_counter()

    for ci, (mc, is4) in enumerate(config_order):
        name = config_name(mc)
        if name in completed:
            print(f"[{ci+1}/{total}] {name} — already done (skipping)")
            continue

        print(f"\n[{ci+1}/{total}] Starting {name}...")
        table = solve(mc, solved, is4)
        solved[mc] = table
        completed.add(name)

        # Checkpoint every config
        save_checkpoint(solved, completed)

        # ETA
        elapsed = time.perf_counter() - overall_start
        done = ci + 1
        remaining = total - done
        if done > 0:
            avg = elapsed / max(1, done - len([n for n in completed if n != name]))
            # rough eta
            eta_s = avg * remaining
            eta_str = time.strftime('%H:%M:%S', time.gmtime(eta_s)) if eta_s < 86400 else f"{eta_s/3600:.1f}h"
            print(f"    Overall: {done}/{total} done, elapsed={elapsed:.0f}s, ETA~{eta_str}")

    total_elapsed = time.perf_counter() - overall_start
    print(f"\n{'='*60}")
    print(f"  ALL TABLES COMPLETE!")
    print(f"  Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print(f"  Tables computed: {len(solved)}")
    print(f"{'='*60}")

    validate(solved)
    generate_output(solved)

    # Final summary
    total_bytes = sum(len(v) for v in solved.values())
    print(f"\n  Total tablebase size: {total_bytes:,} bytes ({total_bytes/1024/1024:.2f} MB)")
    print(f"  Configs: {len(solved)}")
    print(f"\n  DONE! Paste contents of '{OUTPUT_FILE}' into agent.py")
    print(f"  Then add _probe_endgame_tb() calls in _negamax and _quiescence.")

    # Audible notification
    try:
        import winsound
        winsound.Beep(1000, 500)
        winsound.Beep(1500, 500)
        winsound.Beep(2000, 500)
    except Exception:
        print("\a")  # terminal bell


if __name__ == "__main__":
    main()
