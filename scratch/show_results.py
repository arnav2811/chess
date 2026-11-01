import json
data = json.load(open('V78_TOURNAMENT_RESULTS.json', encoding='utf-8'))
print(f"W/D/L: {data['wins']}/{data['draws']}/{data['losses']}")
for g in data['games']:
    mid = g['match_id']
    opp = g['opp'][:8]
    col = g['agent_color']
    brd = g['board']
    out = g['outcome']
    pls = g['plies']
    pcs = g['pieces_left']
    dur = g['duration_s']
    print(f"  [{mid:2d}] {opp:8s} {col:5s} {brd:7s} -> {out} ({pls}p, {pcs}pcs, {dur}s)")

