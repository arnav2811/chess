#!/usr/bin/env python3
"""Unique-position EMPEROR v7.4 self-play and tactical-data collector."""
from __future__ import annotations
import argparse, contextlib, csv, hashlib, importlib.util, io, json, math, random, re, statistics, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from itertools import cycle
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
ENGINE_FILE = "agent_v74_tactical_guard.py"
ENGINE_SHA256 = "f071799b7ac06d30a3f912adc541313942e536cf0c1285d5cff294e73abd57dd"
ENGINE_VERSION = "7.4"
# Original five layouts plus eight new controlled variants.
LAYOUT_ROWS = {
 "sample0": (("Knight","Queen","King","Bishop","Right"),("Right","Bishop","King","Queen","Knight")),
 "sample1": (("Right","Queen","King","Knight","Bishop"),("Bishop","Knight","King","Queen","Right")),
 "sample2": (("Right","Bishop","King","Queen","Knight"),("Knight","Queen","King","Bishop","Right")),
 "sample3": (("Right","Queen","King","Right","Knight"),("Knight","Right","King","Queen","Right")),
 "sample4": (("Right","Bishop","King","Knight","Right"),("Right","Knight","King","Bishop","Right")),
 "sample5": (("Bishop","Knight","King","Right","Queen"),("Queen","Right","King","Knight","Bishop")),
 "sample6": (("Queen","Right","King","Bishop","Knight"),("Knight","Bishop","King","Right","Queen")),
 "sample7": (("Knight","Right","King","Queen","Bishop"),("Bishop","Queen","King","Right","Knight")),
 "sample8": (("Bishop","Queen","King","Knight","Right"),("Right","Knight","King","Queen","Bishop")),
 "sample9": (("Right","Knight","King","Bishop","Queen"),("Queen","Bishop","King","Knight","Right")),
 "sample10": (("Knight","Bishop","King","Right","Queen"),("Queen","Right","King","Bishop","Knight")),
 "sample11": (("Queen","Bishop","King","Right","Knight"),("Knight","Right","King","Bishop","Queen")),
 "sample12": (("Bishop","Right","King","Queen","Knight"),("Knight","Queen","King","Right","Bishop")),
}
BOARDS = tuple(LAYOUT_ROWS)
VALUES = {"pawn":100,"knight":320,"bishop":330,"right":600,"queen":900,"king":20000}


def sha256(path): return hashlib.sha256(path.read_bytes().replace(b"\r\n",b"\n")).hexdigest()
def verify_engine():
    path=ROOT/ENGINE_FILE
    if not path.is_file(): raise SystemExit(f"Missing {path}")
    actual=sha256(path)
    if actual != ENGINE_SHA256: raise SystemExit(f"SAFETY STOP: v7.4 hash mismatch; expected {ENGINE_SHA256}, got {actual}")
    src=path.read_text(encoding="utf-8",errors="replace")
    marks=re.findall(r"\[agent v(\d+(?:\.\d+)?)(?:-[^\]]*)?\]",src)
    if not marks or marks[-1] != ENGINE_VERSION: raise SystemExit(f"Expected v7.4 source marker, got {marks[-1:]}")
    return {"file":ENGINE_FILE,"sha256":actual}


def load_engine(module_name):
    path=ROOT/ENGINE_FILE; spec=importlib.util.spec_from_file_location(module_name,path)
    if spec is None or spec.loader is None: raise RuntimeError(f"Cannot load {path}")
    module=importlib.util.module_from_spec(spec); sys.modules[module_name]=module; spec.loader.exec_module(module)
    if not callable(getattr(module,"agent",None)): raise RuntimeError("agent() missing")
    for flag in ("_ENABLE_ROOT_PUCT","_ENABLE_CHECK_EXTENSION","_ENABLE_ROOT_RANDOM_TIEBREAK"):
        if getattr(module,flag,None) is not False: raise RuntimeError(f"v7.4 {flag} must be OFF")
    if getattr(module,"_MATERIAL_GUARD_MAX_SCORE_LOSS_CP",None) != 150: raise RuntimeError("Unexpected v7.4 guard margin")
    if hasattr(module,"_ENABLE_STDERR_LOG"): module._ENABLE_STDERR_LOG=False
    return module


def make_fresh_board(layout_name):
    from chessmaker.chess.base import Player, Board, Square
    from chessmaker.chess.pieces import King, Bishop, Knight, Queen
    from extension.piece_right import Right
    from extension.piece_pawn import Pawn_Q
    constructors={"King":King,"Bishop":Bishop,"Knight":Knight,"Queen":Queen,"Right":Right}
    if layout_name not in LAYOUT_ROWS: raise ValueError(f"Unknown layout {layout_name}")
    white,black=Player("white"),Player("black")
    black_back,white_back=LAYOUT_ROWS[layout_name]
    rows=[[constructors[n](black) for n in black_back], [Pawn_Q(black) for _ in range(5)], [None]*5,
          [Pawn_Q(white) for _ in range(5)], [constructors[n](white) for n in white_back]]
    squares=[[Square(p) if p is not None else Square() for p in row] for row in rows]
    players=[white,black]
    return Board(squares=squares,players=players,turn_iterator=cycle(players)),players


def piece_name(piece):
    name=type(piece).__name__.lower()
    return "pawn" if name.startswith("pawn_") or name=="pawnq" else name

def coord(obj):
    if obj is None:return None
    pos=getattr(obj,"position",obj); x=getattr(pos,"x",None); y=getattr(pos,"y",None)
    return [int(x),int(y)] if x is not None and y is not None else None

def board_state(board):
    rows=[{"piece":piece_name(p),"class":type(p).__name__,"side":str(p.player.name).lower(),"x":int(p.position.x),"y":int(p.position.y)} for p in board.get_pieces()]
    return sorted(rows,key=lambda r:(r["y"],r["x"],r["side"],r["piece"]))

def position_signature(state,side_to_move):
    pieces=sorted([{k:r[k] for k in ("piece","side","x","y")} for r in state],key=lambda r:(r["y"],r["x"],r["side"],r["piece"]))
    raw=json.dumps({"side_to_move":side_to_move.lower(),"pieces":pieces},sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def capture_coords(move):
    out=[]
    try:
        for item in (getattr(move,"captures",set()) or set()):
            c=coord(item)
            if c is not None: out.append(c)
    except TypeError: pass
    return sorted(out)

def is_king_capture(board,move):
    for pos in (getattr(move,"captures",set()) or set()):
        try: victim=board[pos].piece
        except Exception: victim=None
        if victim is not None and piece_name(victim)=="king": return True
    return False

def opening_weight(board,piece,move,moved_counts):
    captures=getattr(move,"captures",set()) or set(); weight=0.78 if piece_name(piece)=="pawn" else 1.12
    if captures:
        victim_value=0
        for square in captures:
            try: victim=board[square].piece
            except Exception: victim=None
            if victim is not None: victim_value+=VALUES.get(piece_name(victim),0)
        weight*=0.48 if victim_value<600 else 0.62
    if piece_name(piece)=="pawn" and move.position.y in (0,4): weight*=1.35
    key=id(piece)
    return max(0.05,weight*(0.62**min(moved_counts[key],3)))


def generate_unique_openings(count,seed,min_plies=4,max_plies=14,max_attempts=None,progress=True):
    from extension.board_utils import list_legal_moves_for
    from extension.board_rules import get_result
    if count<1 or min_plies<2 or max_plies<min_plies: raise ValueError("Invalid corpus arguments")
    max_attempts=max_attempts or count*80
    master=random.Random(seed^0xE6A07400); seen=set(); corpus=[]; attempts=0
    while len(corpus)<count and attempts<max_attempts:
        attempts+=1; layout=BOARDS[len(corpus)%len(BOARDS)]
        board,players=make_fresh_board(layout); turn_order=cycle(players)
        local_seed=master.randrange(1,2**63); rng=random.Random(local_seed)
        parity=len(corpus)%2 # even => White next, odd => Black next
        ply_choices=[n for n in range(min_plies,max_plies+1) if n%2==parity]
        if not ply_choices: raise ValueError("Opening ply range must contain both parities")
        target=rng.choice(ply_choices); opening=[]; moved=Counter(); valid=True
        for _ in range(target):
            player=next(turn_order); side=player.name.lower()
            if board.current_player.name.lower()!=side: valid=False; break
            legal=[(p,m) for p,m in list_legal_moves_for(board,player) if not is_king_capture(board,m)]
            if not legal: valid=False; break
            piece,move=rng.choices(legal,weights=[opening_weight(board,p,m,moved) for p,m in legal],k=1)[0]
            rec={"side":side,"piece":piece_name(piece),"piece_class":type(piece).__name__,"from":coord(piece.position),"to":coord(move),"captures":capture_coords(move)}
            moved[id(piece)]+=1
            try: piece.move(move)
            except Exception: valid=False; break
            opening.append(rec)
        if not valid or len(opening)!=target: continue
        state=board_state(board); side=board.current_player.name.lower()
        kings={r["side"] for r in state if r["piece"]=="king"}
        if kings!={"white","black"} or len(state)<=2: continue
        if not list_legal_moves_for(board,board.current_player): continue
        other=players[1] if side=="white" else players[0]
        if not list_legal_moves_for(board,other): continue
        if get_result(board) is not None: continue
        sig=position_signature(state,side)
        if sig in seen: continue
        seen.add(sig)
        corpus.append({"game_id":len(corpus)+1,"board":layout,"opening_seed":local_seed,"opening_plies":len(opening),
                       "opening_side_to_move":side,"opening_signature":sig,"opening_moves":opening,"start_state":state})
        if progress and (len(corpus)%50==0 or len(corpus)==count):
            print(f"Unique starting positions: {len(corpus)}/{count} via {attempts} attempts",flush=True)
    if len(corpus)!=count: raise RuntimeError(f"Generated only {len(corpus)}/{count} unique positions in {attempts} attempts")
    if len({r["opening_signature"] for r in corpus})!=count: raise AssertionError("Duplicate starting positions")
    return corpus


def find_move_for_record(board,player,record):
    from extension.board_utils import list_legal_moves_for
    for piece,move in list_legal_moves_for(board,player):
        if (piece.player.name.lower()==record["side"] and piece_name(piece)==record["piece"]
                and coord(piece.position)==record["from"] and coord(move)==record["to"]):
            return piece,move
    return None,None

def replay_opening(board,players,opening_moves):
    turn_order=cycle(players)
    for index,record in enumerate(opening_moves,1):
        player=next(turn_order)
        if player.name.lower()!=record["side"] or board.current_player.name.lower()!=record["side"]:
            raise RuntimeError(f"Opening turn mismatch at ply {index}")
        piece,move=find_move_for_record(board,player,record)
        if piece is None: raise RuntimeError(f"Stored opening move is no longer legal: {record}")
        piece.move(move)
    return turn_order


def root_candidates(module,limit=8):
    out=[]
    for item in (getattr(module,"_last_root_evals",[]) or [])[:limit]:
        try:
            score,piece,move=item
            out.append({"score_cp_or_bound":float(score),"piece":piece_name(piece),"side":piece.player.name.lower(),"from":coord(piece.position),"to":coord(move)})
        except Exception: pass
    return out

def stats_snapshot(module):
    puct=getattr(module,"_last_puct_stats",{}) or {}
    return {
      "depth":int(getattr(module,"_last_depth_reached",0) or 0),"nodes":int(getattr(module,"_last_nodes_searched",0) or 0),
      "ebf":float(getattr(module,"_last_branching_factor",0.0) or 0.0),"iterations":list(getattr(module,"_last_iteration_trace",[]) or []),
      "aborted_depth":int(getattr(module,"_last_aborted_depth",0) or 0),"aborted_nodes":int(getattr(module,"_last_aborted_nodes",0) or 0),
      "tt_hits":int(getattr(module,"_last_tt_hits",0) or 0),"tt_cutoffs":int(getattr(module,"_last_tt_cutoffs",0) or 0),
      "lmr_one_ply":int(getattr(module,"_last_lmr_one_ply",0) or 0),"lmr_two_ply":int(getattr(module,"_last_lmr_two_ply",0) or 0),
      "aspiration_fail_low":int(getattr(module,"_last_aspiration_fail_low",0) or 0),"aspiration_fail_high":int(getattr(module,"_last_aspiration_fail_high",0) or 0),
      "check_extensions":int(getattr(module,"_last_check_extensions",0) or 0),"mobility_extensions":int(getattr(module,"_last_mobility_extensions",0) or 0),
      "random_tiebreak":bool(getattr(module,"_last_random_tiebreak",False)),
      "material_guard":bool(getattr(module,"_last_material_guard_triggered",False)),
      "material_guard_loss_cp":int(getattr(module,"_last_material_guard_loss",0) or 0),
      "material_guard_replacement":bool(getattr(module,"_last_material_guard_replacement",False)),
      "promotion_guard":bool(getattr(module,"_last_promotion_guard_triggered",False)),
      "promotion_guard_replacement":bool(getattr(module,"_last_promotion_guard_replacement",False)),
      "puct_used":bool(puct.get("used",False)),"root_candidates":root_candidates(module)}

def call_with_rng(module,board,player,var,rng):
    outer=random.getstate(); random.setstate(rng.getstate())
    try:
        result=module.agent(board,player,var); rng.setstate(random.getstate()); return result
    finally: random.setstate(outer)

def result_winner(result):
    text=(result or "").lower()
    if "draw" in text:return None,True
    m=re.search(r"\b(white|black)\s+loses\b",text)
    if m:return ("black" if m.group(1)=="white" else "white"),False
    m=re.search(r"\b(white|black)\s+wins?\b",text)
    if m:return m.group(1),False
    return None,False


def play_one_game(task):
    from extension.board_utils import copy_piece_move
    from extension.board_rules import get_result
    gid=int(task["game_id"]); suffix=f"v74sp_{gid}_{task['opening_seed']}"
    module_names=(suffix+"_white",suffix+"_black"); modules={}
    start=time.perf_counter(); cpu_start=time.process_time()
    clocks={"white":float(task["game_time"]),"black":float(task["game_time"])}
    log=[]; outcome="ERROR"; termination="Worker failed before setup"; winner=None; plies=0
    try:
        modules["white"]=load_engine(module_names[0]); modules["black"]=load_engine(module_names[1])
        if modules["white"] is modules["black"]: raise RuntimeError("Engine seats share one module instance")
        board,players=make_fresh_board(task["board"])
        turn_order=replay_opening(board,players,task["opening_moves"])
        state=board_state(board); side=board.current_player.name.lower()
        if state!=task["start_state"] or side!=task["opening_side_to_move"]: raise RuntimeError("Opening replay state mismatch")
        if position_signature(state,side)!=task["opening_signature"]: raise RuntimeError("Opening replay signature mismatch")
        if get_result(board) is not None: raise RuntimeError("Stored opening replay is already terminal")
        rngs={"white":random.Random(task["white_rng_seed"]),"black":random.Random(task["black_rng_seed"])}
        for ply in range(len(task["opening_moves"])+1,601):
            player=next(turn_order); side=player.name.lower(); module=modules[side]
            if board.current_player.name.lower()!=side: raise RuntimeError(f"Turn iterator desynchronised at ply {ply}")
            if clocks[side]<=0:
                winner="black" if side=="white" else "white"; outcome=f"{winner.upper()}_WIN"
                termination=f"{side} exhausted its game clock"; break
            pre=board_state(board); t0=time.perf_counter(); err=None; piece=move=None
            try:
                thinking_board=board.clone()
                with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
                    tmp_piece,tmp_move=call_with_rng(module,thinking_board,player,[ply,float(task["thinking_time"])],rngs[side])
                board,piece,move=copy_piece_move(board,tmp_piece,tmp_move)
            except Exception as exc: err=f"{type(exc).__name__}: {exc}"
            elapsed=time.perf_counter()-t0; clocks[side]-=elapsed; search=stats_snapshot(module)
            row={"ply":ply,"side":side,"engine":"v7.4","thinking_time_s":round(elapsed,4),
                 "clock_remaining_s":round(clocks[side],3),"search":search,"error":err}
            if err:
                log.append({**row,"pre_state":pre}); winner="black" if side=="white" else "white"
                outcome=f"{winner.upper()}_WIN"; termination=f"engine exception: {err}"; break
            if elapsed>task["thinking_time"]+0.25:
                log.append({**row,"pre_state":pre,"timeout":True}); winner="black" if side=="white" else "white"
                outcome=f"{winner.upper()}_WIN"; termination=f"move budget exceeded ({elapsed:.3f}s)"; break
            if not piece or not move:
                result=get_result(board); winner,is_draw=result_winner(result)
                log.append({**row,"pre_state":pre,"post_state":board_state(board),"result":result})
                if is_draw: outcome="DRAW"; termination=str(result)
                elif winner: outcome=f"{winner.upper()}_WIN"; termination=str(result)
                else:
                    winner="black" if side=="white" else "white"; outcome=f"{winner.upper()}_WIN"
                    termination="agent returned no move without terminal result"
                break
            move_data={"piece":piece_name(piece),"piece_class":type(piece).__name__,"from":coord(piece.position),
                       "to":coord(move),"captures":capture_coords(move)}
            try:
                piece.move(move); result=get_result(board)
            except Exception as exc:
                log.append({**row,"move":move_data,"pre_state":pre,"error":f"{type(exc).__name__}: {exc}"})
                winner="black" if side=="white" else "white"; outcome=f"{winner.upper()}_WIN"; termination=f"move application error: {exc}"; break
            plies=ply; log.append({**row,"move":move_data,"pre_state":pre,"post_state":board_state(board),"result":result})
            if result:
                winner,is_draw=result_winner(result)
                if is_draw: outcome="DRAW"; termination=str(result)
                elif winner: outcome=f"{winner.upper()}_WIN"; termination=str(result)
                else: outcome="ERROR"; termination=f"Unrecognised result: {result}"
                break
        else: outcome="DRAW"; termination="600-ply safety cap"
        return {k:task[k] for k in ("game_id","board","opening_seed","opening_plies","opening_side_to_move","opening_signature")} | {
            "opening_moves":task["opening_moves"],
            "winner_color":winner,"outcome":outcome,"termination":termination,"plies":plies,
            "wall_time_s":round(time.perf_counter()-start,3),"process_cpu_s":round(time.process_time()-cpu_start,3),
            "white_clock_remaining_s":round(clocks["white"],3),"black_clock_remaining_s":round(clocks["black"],3),
            "move_count":len(log),"moves":log}
    finally:
        for name in module_names:sys.modules.pop(name,None)


def build_tasks(corpus,thinking_time,game_time,seed):
    tasks=[]
    for row in corpus:
        gid=row["game_id"]; task=dict(row)
        task.update({"white_rng_seed":seed+gid*7919+17,"black_rng_seed":seed+gid*104729+29,
                     "thinking_time":thinking_time,"game_time":game_time}); tasks.append(task)
    random.Random(seed^0x74D15EED).shuffle(tasks); return tasks


def atomic_json(path,data):
    tmp=path.with_suffix(path.suffix+".tmp"); tmp.write_text(json.dumps(data,indent=2),encoding="utf-8"); tmp.replace(path)

def load_checkpoint(path):
    if not path.exists():return []
    rows=[]
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            try:rows.append(json.loads(line))
            except json.JSONDecodeError as exc:raise SystemExit(f"Malformed checkpoint line {n}: {exc}")
    ids=[r.get("game_id") for r in rows]
    if len(ids)!=len(set(ids)):raise SystemExit("Duplicate game IDs in checkpoint")
    return rows


def summarize(results,elapsed=None):
    outcomes=Counter(r.get("outcome","ERROR") for r in results)
    moves=[m for g in results for m in g.get("moves",[])]
    depths=[int(m.get("search",{}).get("depth",0) or 0) for m in moves]
    total_time=sum(float(m.get("thinking_time_s",0) or 0) for m in moves)
    total_nodes=sum(int(m.get("search",{}).get("nodes",0) or 0) for m in moves)
    trajectories=Counter()
    for game in results:
        line=[{"side":m.get("side"),"piece":m.get("piece"),"from":m.get("from"),"to":m.get("to"),"captures":m.get("captures",[])} for m in game.get("opening_moves",[])]
        line += [{k:m.get("move",{}).get(k) for k in ("piece","from","to","captures")} | {"side":m.get("side")} for m in game.get("moves",[]) if m.get("move")]
        digest=hashlib.sha256(json.dumps(line,sort_keys=True,separators=(",",":")).encode()).hexdigest(); trajectories[digest]+=1
    by_board={b:{"games":sum(g.get("board")==b for g in results),"unique":len({g.get("opening_signature") for g in results if g.get("board")==b})} for b in BOARDS}
    metrics={
      "moves":len(moves),"average_depth":round(statistics.mean(depths),3) if depths else 0,
      "median_depth":round(statistics.median(depths),3) if depths else 0,
      "p90_depth":sorted(depths)[max(0,math.ceil(.9*len(depths))-1)] if depths else 0,
      "max_depth":max(depths,default=0),"moves_depth_ge_6":sum(d>=6 for d in depths),
      "moves_depth_ge_8":sum(d>=8 for d in depths),"moves_depth_ge_10":sum(d>=10 for d in depths),
      "total_nodes":total_nodes,"average_move_time_s":round(total_time/len(moves),4) if moves else 0,
      "aggregate_nps":round(total_nodes/total_time,1) if total_time else 0,
      "tt_hits":sum(m.get("search",{}).get("tt_hits",0) for m in moves),
      "tt_cutoffs":sum(m.get("search",{}).get("tt_cutoffs",0) for m in moves),
      "lmr_one_ply":sum(m.get("search",{}).get("lmr_one_ply",0) for m in moves),
      "material_guard_triggers":sum(bool(m.get("search",{}).get("material_guard")) for m in moves),
      "material_guard_replacements":sum(bool(m.get("search",{}).get("material_guard_replacement")) for m in moves),
      "promotion_guard_triggers":sum(bool(m.get("search",{}).get("promotion_guard")) for m in moves),
      "promotion_guard_replacements":sum(bool(m.get("search",{}).get("promotion_guard_replacement")) for m in moves),
      "puct_calls":sum(bool(m.get("search",{}).get("puct_used")) for m in moves),
      "errors":sum(bool(m.get("error")) for m in moves),"timeouts":sum(bool(m.get("timeout")) for m in moves)}
    summary={"title":"EMPEROR v7.4 unique-position self-play","games_completed":len(results),"outcomes":dict(outcomes),
      "unique_start_positions":len({g.get("opening_signature") for g in results if g.get("opening_signature")}),
      "opening_side_to_move_counts":dict(Counter(g.get("opening_side_to_move") for g in results)),
      "unique_complete_trajectories":len(trajectories),"repeated_trajectory_games":sum(n for n in trajectories.values() if n>1),
      "maximum_trajectory_repeat":max(trajectories.values(),default=0),"by_board":by_board,"search_metrics":metrics,
      "average_plies_after_start":round(sum(max(0,g.get("plies",0)-g.get("opening_plies",0)) for g in results)/len(results),2) if results else 0}
    if elapsed is not None:summary.update({"elapsed_wall_s":round(elapsed,2),"games_per_hour":round(len(results)/elapsed*3600,2) if elapsed else 0})
    return summary


def write_outputs(out_dir,results,elapsed):
    results.sort(key=lambda r:r["game_id"]); atomic_json(out_dir/"games.json",results)
    atomic_json(out_dir/"summary.json",summarize(results,elapsed))
    game_fields=["game_id","board","opening_seed","opening_plies","opening_side_to_move","opening_signature","winner_color","outcome","termination","plies","wall_time_s","process_cpu_s","white_clock_remaining_s","black_clock_remaining_s","move_count"]
    with (out_dir/"games.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=game_fields);w.writeheader();w.writerows({k:g.get(k,"") for k in game_fields} for g in results)
    move_fields=["game_id","board","ply","side","thinking_time_s","clock_remaining_s","depth","nodes","ebf","tt_hits","tt_cutoffs","lmr_one_ply","material_guard","material_guard_loss_cp","material_guard_replacement","promotion_guard","promotion_guard_replacement","from","to","captures","error"]
    with (out_dir/"move_metrics.csv").open("w",newline="",encoding="utf-8") as f, (out_dir/"moves.jsonl").open("w",encoding="utf-8") as jf:
        w=csv.DictWriter(f,fieldnames=move_fields);w.writeheader()
        for g in results:
            for m in g.get("moves",[]):
                s=m.get("search",{}); mv=m.get("move",{})
                row={"game_id":g["game_id"],"board":g["board"],"ply":m.get("ply"),"side":m.get("side"),
                     "thinking_time_s":m.get("thinking_time_s"),"clock_remaining_s":m.get("clock_remaining_s"),
                     "depth":s.get("depth",0),"nodes":s.get("nodes",0),"ebf":s.get("ebf",0),
                     "tt_hits":s.get("tt_hits",0),"tt_cutoffs":s.get("tt_cutoffs",0),"lmr_one_ply":s.get("lmr_one_ply",0),
                     "material_guard":s.get("material_guard",False),"material_guard_loss_cp":s.get("material_guard_loss_cp",0),
                     "material_guard_replacement":s.get("material_guard_replacement",False),"promotion_guard":s.get("promotion_guard",False),
                     "promotion_guard_replacement":s.get("promotion_guard_replacement",False),"from":mv.get("from"),"to":mv.get("to"),
                     "captures":mv.get("captures"),"error":m.get("error")};w.writerow(row)
                jf.write(json.dumps({"game_id":g["game_id"],"opening_signature":g.get("opening_signature"),**m},separators=(",",":"))+"\n")


def validate_environment():
    import chessmaker  # noqa: F401
    from extension.board_utils import list_legal_moves_for
    for name in BOARDS:
        board,players=make_fresh_board(name)
        if not list_legal_moves_for(board,players[0]) or not list_legal_moves_for(board,players[1]):raise RuntimeError(f"{name}: side has no legal initial moves")
        kings=Counter((piece_name(p),p.player.name) for p in board.get_pieces())
        if kings[("king","white")]!=1 or kings[("king","black")]!=1:raise RuntimeError(f"{name}: king count invalid")
    white=load_engine("v74_validate_white");black=load_engine("v74_validate_black")
    try:
        if white is black:raise RuntimeError("Self-play modules are not isolated")
        if white._ENABLE_ROOT_PUCT or black._ENABLE_ROOT_PUCT:raise RuntimeError("PUCT must be OFF")
        if white._ENABLE_CHECK_EXTENSION or black._ENABLE_CHECK_EXTENSION:raise RuntimeError("Check extensions must be OFF")
    finally:
        sys.modules.pop("v74_validate_white",None);sys.modules.pop("v74_validate_black",None)
    test=generate_unique_openings(20,740074,4,10,2000,False)
    sides=Counter(r["opening_side_to_move"] for r in test)
    if sides!={"white":10,"black":10}:raise RuntimeError(f"Opening colour balance failed: {dict(sides)}")
    return f"ChessMaker + extension passed; {len(BOARDS)} layouts legal; isolated v7.4 seats loaded; 20/20 distinct openers (10 each side to move)."


def main():
    p=argparse.ArgumentParser(description="EMPEROR v7.4 diverse-position self-play")
    p.add_argument("--games",type=int,default=600);p.add_argument("--workers",type=int,default=4)
    p.add_argument("--thinking-time",type=float,default=8.0);p.add_argument("--game-time",type=float,default=300.0)
    p.add_argument("--seed",type=int,default=740600);p.add_argument("--min-opening-plies",type=int,default=4);p.add_argument("--max-opening-plies",type=int,default=14)
    p.add_argument("--out",default="");p.add_argument("--validate-only",action="store_true");p.add_argument("--resume",action="store_true")
    a=p.parse_args()
    if a.games<10 or not 1<=a.workers<=12 or a.thinking_time<=0 or a.game_time<=0:raise SystemExit("Invalid game/worker/time arguments")
    if a.min_opening_plies<2 or a.max_opening_plies<a.min_opening_plies or len({n%2 for n in range(a.min_opening_plies,a.max_opening_plies+1)})<2:raise SystemExit("Opening-ply interval must include both odd and even plies")
    engine=verify_engine()
    try:check=validate_environment()
    except Exception as exc:raise SystemExit(f"Live validation failed: {type(exc).__name__}: {exc}")
    print(check,flush=True)
    if a.validate_only:print("Validation-only: no games started.");return
    if not a.out:raise SystemExit("--out is required unless --validate-only is used")
    out=(ROOT/a.out).resolve() if not Path(a.out).is_absolute() else Path(a.out).resolve()
    manifest=out/"manifest.json"; corpus_file=out/"opening_corpus.jsonl"; checkpoint=out/"games.jsonl"
    settings={"title":"EMPEROR v7.4 unique-position self-play","games_requested":a.games,"workers":a.workers,
      "thinking_time_s_per_move":a.thinking_time,"game_clock_s_per_player":a.game_time,"seed":a.seed,
      "opening_plies_min":a.min_opening_plies,"opening_plies_max":a.max_opening_plies,"opening_side_to_move_balance":"alternating 50/50",
      "opening_generation":"legal random playout; mild quiet-move preference; capture opportunities retained; unique canonical position hash",
      "board_layouts":list(BOARDS),"engine":engine,"puct":False,"check_extensions":False,"root_random_tiebreak":False,
      "material_guard_max_score_loss_cp":150,"python":sys.version,"output_directory":str(out)}
    if out.exists():
        if not a.resume:raise SystemExit(f"Output exists; use --resume: {out}")
        if not manifest.is_file() or not corpus_file.is_file():raise SystemExit("Cannot resume without manifest and opening corpus")
        old=json.loads(manifest.read_text(encoding="utf-8"))
        for k in ("games_requested","thinking_time_s_per_move","game_clock_s_per_player","seed","opening_plies_min","opening_plies_max","board_layouts","engine"):
            if old.get(k)!=settings.get(k):raise SystemExit(f"Resume refused: manifest mismatch for {k}")
        corpus=[json.loads(line) for line in corpus_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(corpus)!=a.games:raise SystemExit("Opening corpus length mismatch")
        done=load_checkpoint(checkpoint);done_ids={r["game_id"] for r in done}
        tasks=[t for t in build_tasks(corpus,a.thinking_time,a.game_time,a.seed) if t["game_id"] not in done_ids]
        print(f"Resuming: {len(done)} complete, {len(tasks)} remaining")
    else:
        if a.resume:raise SystemExit(f"Cannot resume missing output path: {out}")
        out.mkdir(parents=True)
        corpus=generate_unique_openings(a.games,a.seed,a.min_opening_plies,a.max_opening_plies,progress=True)
        with corpus_file.open("w",encoding="utf-8") as f:
            for row in corpus:f.write(json.dumps(row,separators=(",",":"))+"\n")
        settings["unique_opening_positions_generated"]=len({r["opening_signature"] for r in corpus})
        settings["opening_side_to_move_counts"]=dict(Counter(r["opening_side_to_move"] for r in corpus))
        settings["board_layout_counts"]=dict(Counter(r["board"] for r in corpus));atomic_json(manifest,settings)
        done=[];tasks=build_tasks(corpus,a.thinking_time,a.game_time,a.seed)
    print("="*76);print("EMPEROR v7.4 — DIVERSE UNIQUE-POSITION SELF-PLAY")
    print(f"Games={a.games}; unique start positions={len(corpus)}; layouts={len(BOARDS)}; workers={a.workers}")
    print(f"Time/move={a.thinking_time:.1f}s; clock/player={a.game_time:.1f}s; opening ply range={a.min_opening_plies}-{a.max_opening_plies}")
    print(f"Seed={a.seed}; source SHA-256={engine['sha256']}; output={out}")
    print("Both sides run independent v7.4 instances. PUCT/check extensions/random tie-break remain OFF.");print("="*76,flush=True)
    results=list(done);started=time.perf_counter()
    if tasks:
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            future_map={pool.submit(play_one_game,t):t for t in tasks}
            for future in as_completed(future_map):
                task=future_map[future]
                try:result=future.result()
                except Exception as exc:
                    result={"game_id":task["game_id"],"board":task["board"],"opening_seed":task["opening_seed"],
                      "opening_plies":task["opening_plies"],"opening_side_to_move":task["opening_side_to_move"],
                      "opening_signature":task["opening_signature"],"opening_moves":task["opening_moves"],"winner_color":None,"outcome":"ERROR",
                      "termination":f"Worker exception: {type(exc).__name__}: {exc}","plies":0,"wall_time_s":0,"process_cpu_s":0,
                      "white_clock_remaining_s":None,"black_clock_remaining_s":None,"move_count":0,"moves":[]}
                    print(f"WORKER ERROR {task['game_id']}: {result['termination']}",flush=True)
                results.append(result)
                with checkpoint.open("a",encoding="utf-8") as f:f.write(json.dumps(result,separators=(",",":"))+"\n")
                elapsed=time.perf_counter()-started;sm=summarize(results)
                print(f"Completed {len(results):>3}/{a.games} | unique starts {sm['unique_start_positions']} | "
                      f"errors {sm['search_metrics']['errors']} | timeouts {sm['search_metrics']['timeouts']} | "
                      f"{(len(results)/elapsed*3600 if elapsed else 0):.1f} games/hour",flush=True)
    elapsed=time.perf_counter()-started;write_outputs(out,results,elapsed)
    print("\nFINAL SELF-PLAY SUMMARY");print(json.dumps(summarize(results,elapsed),indent=2));print(f"Data: {out}")
    print("Self-play diagnoses tactics and search behaviour; it does not itself prove a strength gain.")

if __name__=="__main__":main()
