import wnba_wowy as W
ps = W.players()
def log(n):
    return W.game_log(ps[n]["id"])
A, R, S, M = "Julie Allemand", "Kiki Rice", "Brittney Sykes", "Aneesah Morrow"
logs = {n: log(n) for n in (A, R, S, M)}

print("=== KIKI RICE — is she back and ramping? (last 12 team games) ===")
rl = sorted(logs[R], key=lambda g: g.get("date") or "")
for g in rl[-12:]:
    print("  %s  min=%-5s pts=%-4s ast=%-4s" % (g.get("date"), g.get("min"), g.get("pts"), g.get("ast")))

print("\n=== JULIE ALLEMAND — minutes + assists trend (last 12) ===")
al = sorted(logs[A], key=lambda g: g.get("date") or "")
for g in al[-12:]:
    print("  %s  min=%-5s ast=%-4s  (gid %s)" % (g.get("date"), g.get("min"), g.get("ast"), g.get("game_id")))

print("\n=== the WOWY sample the bet was priced on: Morrow+Sykes both out ===")
w = W.wowy_multi(logs[A], [logs[S], logs[M]])
print("  n_without=%s  n_with=%s" % (w["n_without"], w["n_with"]))
print("  without:", {k: v for k, v in w["without"].items() if k in ("min", "ast")})
print("  with   :", {k: v for k, v in w["with"].items() if k in ("min", "ast")})

present = {g["game_id"] for lg in (logs[S], logs[M]) for g in lg if (g.get("min") or 0) > 0}
elev = [g for g in al if g["game_id"] not in present and (g.get("min") or 0) > 0]
rice_ids = {g["game_id"] for g in logs[R] if (g.get("min") or 0) > 0}
print("\n=== CONFOUND CHECK: of those elevated games, how many also had RICE out? ===")
with_rice = [g for g in elev if g["game_id"] in rice_ids]
without_rice = [g for g in elev if g["game_id"] not in rice_ids]
def avg(gs, k): return round(sum((g.get(k) or 0) for g in gs)/len(gs), 2) if gs else None
print("  elevated games total: %d" % len(elev))
print("  ...with Rice PLAYING : %d   min %s  ast %s" % (len(with_rice), avg(with_rice,"min"), avg(with_rice,"ast")))
print("  ...with Rice OUT     : %d   min %s  ast %s" % (len(without_rice), avg(without_rice,"min"), avg(without_rice,"ast")))
