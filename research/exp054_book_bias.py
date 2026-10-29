"""Is the longshot effect REAL structure or a grading artifact? Two decisive splits:
  A. restricted to players who actually PLAYED (removes all DNP handling from the estimate)
  B. concentration — is it a few players/nights, or broad?"""
import sqlite3, sys, datetime as dt, statistics as st, math
from collections import Counter
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L, wnba_wowy as W, wnba_tonight as T
FRESH = float(getattr(T, "FRESH_MIN", 10))
pl = W.players()
team_of = {str(n).lower(): v["team"] for n, v in pl.items() if v.get("team")}
mpg = {str(n).lower(): (v.get("min") or 0) for n, v in pl.items()}
def tm(n):
    k = str(n).lower()
    return team_of.get(k) or next((v for kk, v in team_of.items() if k and (k in kk or kk in k)), None)
def mp(n):
    k = str(n).lower()
    return mpg.get(k) or next((v for kk, v in mpg.items() if k and (k in kk or kk in k)), 0)
tick = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/tick_archive.sqlite?mode=ro",
                       uri=True, timeout=600)
rows = []
for (d,) in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d"):
    box = L.box_actuals(d)
    if not box or not L.box_complete(d): continue
    played = {t for k in box for t in [tm(k)] if t}
    last, newest = {}, {}
    for player, stat, line, ca, odds in tick.execute(
            "SELECT player, stat, line, collected_at, odds FROM obs WHERE d=? AND side='over' "
            "AND book='fd' ORDER BY collected_at", (d,)):
        last[(player, stat, float(line))] = (str(ca), float(odds))
        if player not in newest or str(ca) > newest[player]: newest[player] = str(ca)
    for (player, stat, line), (ca, odds) in last.items():
        if odds <= 1 or 1.0/odds < 0.02: continue
        if (dt.datetime.fromisoformat(newest[player]) - dt.datetime.fromisoformat(ca)).total_seconds()/60 > FRESH:
            continue
        t = tm(player)
        if t is None or t not in played: continue
        hit = L.box_lookup(box, player)
        if hit is None:
            won, did = 0, False
        else:
            v = hit.get(stat)
            if v is None or float(v) == line: continue
            won, did = (1 if float(v) > line else 0), True
        rows.append({"d": d, "player": player, "odds": odds, "ip": 1.0/odds, "won": won,
                     "played": did, "mpg": mp(player), "line": line})
ls = [r for r in rows if r["ip"] < 0.24]
print(f"longshot rungs (implied < 0.24): {len(ls)}   of which player PLAYED: "
      f"{sum(1 for r in ls if r['played'])}")
def roi(sel, lab):
    if len(sel) < 40: print(f"  {lab:36s} thin ({len(sel)})"); return
    u = [(r["odds"]-1) if r["won"] else -1 for r in sel]
    se = st.pstdev(u)/math.sqrt(len(u)) or 1e-9
    print(f"  {lab:36s} n={len(sel):5d}  over {sum(r['won'] for r in sel)/len(sel)*100:5.1f}%  "
          f"ROI {st.mean(u)*100:+8.1f}%  t={st.mean(u)/se:+5.2f}")
print("\n=== A. does the longshot effect survive on players who PLAYED? ===")
roi(ls, "all longshot rungs")
roi([r for r in ls if r["played"]], "  players who PLAYED only")
roi([r for r in ls if not r["played"]], "  scratched only (must be -100%)")
print("\n=== B. by the player's season minutes (are these deep-bench rungs?) ===")
for lo, hi in ((0,10),(10,20),(20,45)):
    roi([r for r in ls if lo <= r["mpg"] < hi], f"  mpg {lo}-{hi}")
print("\n=== C. concentration — who supplies the winners? ===")
w = Counter(r["player"] for r in ls if r["won"])
tot = sum(1 for r in ls if r["won"])
print(f"  {tot} winning longshot rungs from {len(w)} distinct players")
for p, n in w.most_common(6):
    print(f"     {str(p)[:22]:22s} {n:3d}  ({n/tot*100:.0f}% of all longshot winners)")
