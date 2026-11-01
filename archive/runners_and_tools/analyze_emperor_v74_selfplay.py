#!/usr/bin/env python3
"""Analyse EMPEROR diverse self-play: uniqueness, tactical blunders and guard data."""
from __future__ import annotations
import argparse, collections, hashlib, json
from pathlib import Path

VALUES={"pawn":100,"knight":320,"bishop":330,"right":600,"queen":900,"king":20000}
MAJOR={"right","queen"}
TACTICAL={"right","queen","bishop","knight"}


def read_jsonl(path):
    out=[]
    for line_no,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            try:out.append(json.loads(line))
            except json.JSONDecodeError as exc:raise ValueError(f"{path}: malformed JSONL line {line_no}: {exc}")
    return out


def load_run(path):
    path=Path(path)
    if path.is_dir():
        jp=path/"games.json"
        if jp.is_file():return json.loads(jp.read_text(encoding="utf-8")), path
        jl=path/"games.jsonl"
        if jl.is_file():return read_jsonl(jl), path
        raise FileNotFoundError(f"No games.json or games.jsonl in {path}")
    if path.suffix.lower()==".jsonl":return read_jsonl(path),path.parent
    if path.suffix.lower()==".json":return json.loads(path.read_text(encoding="utf-8")),path.parent
    raise ValueError("Input must be a run directory, games.json or games.jsonl")


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def canonical_position(state,side):
    pieces=sorted([{k:r[k] for k in ("piece","side","x","y")} for r in (state or [])],
                  key=lambda r:(r["y"],r["x"],r["side"],r["piece"]))
    return digest({"side_to_move":side,"pieces":pieces})


def material_of(state,side):
    return sum(VALUES.get(p.get("piece"),0) for p in (state or []) if p.get("side")==side and p.get("piece")!="king")


def find_at(state,coords):
    if not coords:return None
    x,y=coords
    return next((p for p in (state or []) if p.get("x")==x and p.get("y")==y),None)


def analyse_games(games,corpus=None):
    events=[]; position_bank={}; starts=[]; trajectories=collections.Counter(); move_positions=collections.Counter()
    guard_counts=collections.Counter(); outcome_counts=collections.Counter(); board_counts=collections.Counter()
    unique_opening_keys=set(); duplicate_ids=[]; tactical_capture_value=[]; plies=[]

    corpus_by_id={r.get("game_id"):r for r in (corpus or [])}
    for game in games:
        gid=game.get("game_id"); board=game.get("board","unknown"); board_counts[board]+=1
        outcome_counts[game.get("outcome","ERROR")]+=1; plies.append(game.get("plies",0))
        start_sig=game.get("opening_signature")
        if start_sig:unique_opening_keys.add(start_sig)
        if game.get("opening_signature"):
            starts.append({"game_id":gid,"board":board,"signature":start_sig,
                           "side_to_move":game.get("opening_side_to_move"),"opening_plies":game.get("opening_plies")})
        source=corpus_by_id.get(gid,{})
        opening_moves=source.get("opening_moves",[]) or game.get("opening_moves",[])
        logged=[m for m in game.get("moves",[]) if m.get("move")]
        full_line=[{"side":m.get("side"),"piece":m.get("piece"),"from":m.get("from"),"to":m.get("to"),"captures":m.get("captures",[])} for m in opening_moves]
        full_line += [{"side":m.get("side"),"piece":m.get("move",{}).get("piece"),"from":m.get("move",{}).get("from"),
                       "to":m.get("move",{}).get("to"),"captures":m.get("move",{}).get("captures",[])} for m in logged]
        trajectories[digest(full_line)]+=1

        for i,m in enumerate(logged):
            side=m.get("side"); move=m.get("move",{}); pre=m.get("pre_state",[]); post=m.get("post_state",[])
            key=canonical_position(pre,side or "unknown")
            move_positions[key]+=1
            search=m.get("search",{}) or {}
            if search.get("material_guard"):
                guard_counts["material_guard_triggers"]+=1
                ev={"type":"material_guard_trigger","game_id":gid,"board":board,"ply":m.get("ply"),
                    "side_to_move":side,"position_key":key,"pre_state":pre,"chosen_move":move,
                    "guard_loss_cp":search.get("material_guard_loss_cp"),
                    "guard_replaced":bool(search.get("material_guard_replacement")),
                    "root_candidates_are_bounds_or_mixed":True}
                events.append(ev);position_bank.setdefault(key,ev)
            if search.get("promotion_guard"):
                guard_counts["promotion_guard_triggers"]+=1
                ev={"type":"promotion_guard_trigger","game_id":gid,"board":board,"ply":m.get("ply"),
                    "side_to_move":side,"position_key":key,"pre_state":pre,"chosen_move":move,
                    "guard_replaced":bool(search.get("promotion_guard_replacement"))}
                events.append(ev);position_bank.setdefault(key,ev)
            guard_counts["material_guard_replacements"]+=int(bool(search.get("material_guard_replacement")))
            guard_counts["promotion_guard_replacements"]+=int(bool(search.get("promotion_guard_replacement")))

            captured=[]
            for xy in move.get("captures",[]):
                victim=find_at(pre,xy)
                if victim and victim.get("side")!=side:
                    value=VALUES.get(victim.get("piece"),0);tactical_capture_value.append(value)
                    captured.append({"piece":victim.get("piece"),"side":victim.get("side"),"square":xy,"value":value})
            if captured:
                ev={"type":"capture","game_id":gid,"board":board,"ply":m.get("ply"),"side_to_move":side,
                    "position_key":key,"pre_state":pre,"move":move,"captured":captured,
                    "captured_material_cp":sum(x["value"] for x in captured)}
                events.append(ev)
                if any(x["piece"] in TACTICAL for x in captured):position_bank.setdefault(key,ev)

            # If the next ply captures a major piece of the side that just moved,
            # the preceding decision is a concrete one-move tactical loss.
            if i+1<len(logged):
                nxt=logged[i+1]; next_move=nxt.get("move",{}); next_caps=next_move.get("captures",[])
                hanging=[]
                for xy in next_caps:
                    victim=find_at(post,xy)
                    if victim and victim.get("side")==side and victim.get("piece") in MAJOR:
                        hanging.append({"piece":victim["piece"],"square":xy,"value":VALUES[victim["piece"]],
                                        "captured_by":nxt.get("side"),"capturing_piece":next_move.get("piece")})
                if hanging:
                    ev={"type":"immediate_major_piece_hang","game_id":gid,"board":board,"ply":m.get("ply"),
                        "side_to_move":side,"position_key":key,"pre_state":pre,"post_state":post,
                        "chosen_move":move,"next_reply":next_move,"lost_pieces":hanging,
                        "material_lost_cp":sum(x["value"] for x in hanging)}
                    events.append(ev);position_bank.setdefault(key,ev)

                # Record the defensive decision immediately before an opponent
                # promotes on the following ply.
                next_to=next_move.get("to") or [None,None]
                promoted=(next_move.get("piece")=="pawn" and
                          ((nxt.get("side")=="white" and next_to[1]==0) or
                           (nxt.get("side")=="black" and next_to[1]==4)))
                if promoted:
                    ev={"type":"promotion_allowed_next_ply","game_id":gid,"board":board,"ply":m.get("ply"),
                        "side_to_move":side,"position_key":key,"pre_state":pre,"chosen_move":move,
                        "opponent_promotion":{"side":nxt.get("side"),"from":next_move.get("from"),"to":next_to}}
                    events.append(ev);position_bank.setdefault(key,ev)

            to=move.get("to") or [None,None]
            is_promotion=(move.get("piece")=="pawn" and
                          ((side=="white" and to[1]==0) or (side=="black" and to[1]==4)))
            if is_promotion:
                captured_next=False
                if i+1<len(logged):
                    captured_next=to in (logged[i+1].get("move",{}).get("captures",[]) or [])
                ev={"type":"promotion_played","game_id":gid,"board":board,"ply":m.get("ply"),
                    "side_to_move":side,"position_key":key,"pre_state":pre,"move":move,
                    "captured_on_immediate_reply":captured_next}
                events.append(ev);position_bank.setdefault(key,ev)

    event_counts=collections.Counter(e["type"] for e in events)
    unique_trajectories=len(trajectories)
    report={"games":len(games),"unique_opening_positions":len(unique_opening_keys),
      "opening_position_duplicates":max(0,len(games)-len(unique_opening_keys)),
      "unique_complete_trajectories":unique_trajectories,
      "repeated_trajectory_games":sum(n for n in trajectories.values() if n>1),
      "max_trajectory_repeats":max(trajectories.values(),default=0),
      "unique_decision_positions":len(move_positions),"decision_position_revisits":sum(n-1 for n in move_positions.values() if n>1),
      "outcomes":dict(outcome_counts),"games_by_board":dict(board_counts),
      "games_by_opening_side_to_move":dict(collections.Counter(g.get("opening_side_to_move") for g in games)),
      "guard_counters":dict(guard_counts),"tactical_event_counts":dict(event_counts),
      "unique_tactical_positions":len(position_bank),
      "major_piece_hangs":event_counts.get("immediate_major_piece_hang",0),
      "promotion_events":event_counts.get("promotion_played",0),
      "promotions_allowed_next_ply":event_counts.get("promotion_allowed_next_ply",0),
      "average_game_plies_total":round(sum(plies)/len(plies),2) if plies else 0,
      "captured_material_cp_total":sum(tactical_capture_value)}
    return report,events,list(position_bank.values()),starts


def write_analysis(report,events,bank,out_dir):
    out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/"analysis.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    with (out_dir/"tactical_events.jsonl").open("w",encoding="utf-8") as f:
        for row in events:f.write(json.dumps(row,separators=(",",":"))+"\n")
    with (out_dir/"tactical_position_bank.jsonl").open("w",encoding="utf-8") as f:
        for row in bank:f.write(json.dumps(row,separators=(",",":"))+"\n")
    # A regression-candidate file contains positions and labels, not asserted best moves.
    with (out_dir/"tactical_regression_candidates.jsonl").open("w",encoding="utf-8") as f:
        for row in bank:
            f.write(json.dumps({"position_key":row["position_key"],"game_id":row["game_id"],"board":row["board"],
              "ply":row["ply"],"side_to_move":row["side_to_move"],"reason":row["type"],
              "position":row["pre_state"],"observed_move":row.get("chosen_move",row.get("move")),
              "label_status":"review_required_no_ground_truth_move"},separators=(",",":"))+"\n")
    md=["# EMPEROR v7.4 — diverse self-play analysis","", "## Dataset integrity", "",
        f"- Completed games: **{report['games']}**",
        f"- Unique starting positions: **{report['unique_opening_positions']}**",
        f"- Duplicate starting positions: **{report['opening_position_duplicates']}**",
        f"- Unique complete trajectories: **{report['unique_complete_trajectories']}**",
        f"- Unique decision positions: **{report['unique_decision_positions']}**",
        f"- Unique tactical review positions: **{report['unique_tactical_positions']}**","",
        "## Tactical signals",""]
    for k,v in sorted(report["tactical_event_counts"].items()):md.append(f"- {k}: {v}")
    md += ["", "## Guard activity", ""]
    for k,v in sorted(report["guard_counters"].items()):md.append(f"- {k}: {v}")
    md += ["", "## Outcomes and layout coverage", "", "```json",json.dumps(report["outcomes"],indent=2),"```","", "```json",json.dumps(report["games_by_board"],indent=2),"```","",
      "## Interpretation", "",
      "Self-play is not a strength rating. White/Black wins are not independent engine comparisons because both seats run the same v7.4 source.",
      "Immediate major-piece hangs and promotion events are concrete review leads; they are not automatically proven search bugs.",
      "Root candidate values are recorded as score/bound hints and must not be treated as exact evaluations.",
      "The regression-candidate file deliberately does not invent a correct move. Each position requires deeper independent analysis or manual verification.",""]
    (out_dir/"REPORT.md").write_text("\n".join(md),encoding="utf-8")


def main():
    p=argparse.ArgumentParser(description="Analyse v7.4 unique-position self-play data")
    p.add_argument("run",help="Self-play result directory or games.json/jsonl")
    p.add_argument("--out",default="",help="Analysis output directory")
    a=p.parse_args();games,root=load_run(a.run)
    corpus_path=root/"opening_corpus.jsonl"
    corpus=read_jsonl(corpus_path) if corpus_path.is_file() else None
    report,events,bank,starts=analyse_games(games,corpus)
    out=Path(a.out).resolve() if a.out else root/"analysis"
    write_analysis(report,events,bank,out)
    print(json.dumps(report,indent=2));print(f"\nReport: {out/'REPORT.md'}")

if __name__=="__main__":main()
