import wnba_wowy as W
ps = W.players()
A, R, S, M = "Julie Allemand", "Kiki Rice", "Brittney Sykes", "Aneesah Morrow"
logs = {n: W.game_log(ps[n]["id"]) for n in (A, R, S, M)}
present = {g["game_id"] for lg in (logs[S], logs[M]) for g in lg if (g.get("min") or 0) > 0}
al = sorted(logs[A], key=lambda g: g.get("date") or "")
elev = [g for g in al if g["game_id"] not in present and (g.get("min") or 0) > 0]
rice = {g["game_id"]: g for g in logs[R] if (g.get("min") or 0) > 0}

print("=== WHICH 2 games are the 'Rice playing' matches? ===")
for g in elev:
    if g["game_id"] in rice:
        rg = rice[g["game_id"]]
        print("  %s   Allemand %sm / %sa   |   Rice %sm" % (g["date"][:10], g["min"], g["ast"], rg["min"]))

print("\n=== Rice's baseline BEFORE the absence vs the 2 games back ===")
rl = sorted(logs[R], key=lambda g: g.get("date") or "")
pre = [g for g in rl if (g["date"][:10] < "2026-06-10") and (g.get("min") or 0) > 0]
post = [g for g in rl if (g["date"][:10] >= "2026-07-01") and (g.get("min") or 0) > 0]
avg = lambda gs: round(sum(g["min"] for g in gs) / len(gs), 1) if gs else None
print("  pre-absence  n=%d  mean %s min  (last 5: %s)" % (len(pre), avg(pre), [g["min"] for g in pre[-5:]]))
print("  since return n=%d  mean %s min  (%s)" % (len(post), avg(post), [g["min"] for g in post]))
print("  -> she is %s below her own pre-absence norm, and CLIMBING (%s -> %s)"
      % (round(avg(pre) - avg(post), 1), post[0]["min"], post[-1]["min"]))

print("\n=== so the ONLY 2 matching games are themselves ramp games ===")
print("  Tonight is Rice's game 3 back. Both matched games had her at 17 and 23 min,")
print("  vs a %s-min pre-absence norm. The matched sub-sample is not a steady state." % avg(pre))
