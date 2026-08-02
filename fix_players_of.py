"""Guard players_of against events with no leaderboardV2.

The 2024-25 backfill walks EVERY completed tournament, which includes formats the query
does not model (team events, and at least one cancelled/abandoned event). Those return a
null leaderboardV2 and the harvest died on it after 33 events. A missing leaderboard is a
skip, not a crash — one odd event must not cost the whole backfill.
"""
import ast, io
p = "pga_birdies.py"
s = io.open(p, encoding="utf-8").read()
old = '''def players_of(tid):
    d = gql('query L($id: ID!) {leaderboardV2(id: $id) {players '
            '{... on PlayerRowV2 {player {id displayName}}}}}', {"id": tid})
    return [(p["player"]["id"], p["player"]["displayName"])
            for p in (d.get("data", {}).get("leaderboardV2", {}) or {}).get("players") or []
            if p and p.get("player")]'''
new = '''def players_of(tid):
    """[] for any event without a modelled leaderboard (team formats, abandoned events) —
    a skip, not a crash: one odd event must not cost an entire season backfill."""
    d = gql('query L($id: ID!) {leaderboardV2(id: $id) {players '
            '{... on PlayerRowV2 {player {id displayName}}}}}', {"id": tid})
    lb = (d.get("data") or {}).get("leaderboardV2") or {}
    return [(p["player"]["id"], p["player"]["displayName"])
            for p in (lb.get("players") or [])
            if p and p.get("player") and p["player"].get("id")]'''
assert old in s
if "a skip, not a crash" not in s:
    s = s.replace(old, new, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + players_of guarded")
else:
    print("  = already guarded")

# and make the per-event body resilient so one bad event cannot abort the run
old2 = '''    for tid, tname in evs:
        ps = players_of(tid)
        rows = []'''
new2 = '''    for tid, tname in evs:
        try:
            ps = players_of(tid)
        except Exception as e:                                      # noqa: BLE001
            print(f"  {tname}: leaderboard unavailable ({str(e)[:40]}) - skipped", flush=True)
            continue
        if not ps:
            print(f"  {tname}: no player rows - skipped", flush=True)
            continue
        rows = []'''
s = io.open(p, encoding="utf-8").read()
if "no player rows - skipped" not in s:
    assert old2 in s
    s = s.replace(old2, new2, 1)
    ast.parse(s)
    io.open(p, "w", encoding="utf-8").write(s)
    print("  + per-event skip on failure")
else:
    print("  = already resilient")
