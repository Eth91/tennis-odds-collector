"""FINAL. Full sample, clustered by game, plus a conditional strategy the data CAN support:
in-play line movement as a proxy for game state (I have no score/clock feed, but the line encodes
it). If a player starts cold the line drops -- is the over then value? That is the classic
mean-reversion bet and it is testable entirely within the collected snapshots."""
import sqlite3, sys, statistics as st, math
from collections import defaultdict
sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
import wnba_ledger as L
MAP = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists"}
db = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/live_odds.sqlite?mode=ro",
                     uri=True, timeout=180)
db.row_factory = sqlite3.Row
rows = [dict(r) for r in db.execute("SELECT * FROM q")]
boxes = {}
def box(d):
    if d not in boxes:
        b = L.box_actuals(d); boxes[d] = b if (b and L.box_complete(d)) else None
    return boxes[d]
g = []
for r in rows:
    b = box(r["box_date"])
    if not b: continue
    hit = L.box_lookup(b, r["player"])
    if hit is None: continue
    fin = hit.get(MAP.get(r["market"], ""))
    if fin is None: continue
    fin = float(fin); line = float(r["line"])
    if fin == line: continue
    g.append({**r, "final": fin, "won": 1 if ((fin > line) if r["side"]=="Over" else (fin < line)) else 0})
print(f"graded {len(g)} | {len({x['event_id'] for x in g})} games | {len({x['box_date'] for x in g})} dates")
def clustered(sel, unit="event_id"):
    if not sel: return None
    by = defaultdict(list)
    for r in sel: by[r[unit]].append((r["price"]-1.0) if r["won"] else -1.0)
    per = [sum(v)/len(v) for v in by.values()]
    k = len(per)
    if k < 8: return None
    m = st.mean(per); se = st.pstdev(per)/math.sqrt(k)
    return m*100, se*100, (m/se if se else 0), len(sel), k
print(f"\n{'strategy':30s} {'ROI':>8s} {'SE':>7s} {'t':>7s} {'bets':>7s} {'games':>6s}")
for lab, sel in (("ALL overs", [r for r in g if r["side"]=="Over"]),
                 ("ALL unders", [r for r in g if r["side"]=="Under"])):
    c = clustered(sel)
    if c: print(f"{lab:30s} {c[0]:+7.2f}% {c[1]:6.2f} {c[2]:+7.2f} {c[3]:7d} {c[4]:6d}")

# ---- conditional: in-play line movement vs the FIRST observed (+10 min) line ----
first = {}
for r in g:
    k = (r["event_id"], r["player"], r["market"], r["book"])
    if k not in first or r["offset_min"] < first[k][0]:
        first[k] = (r["offset_min"], float(r["line"]))
mv = []
for r in g:
    k = (r["event_id"], r["player"], r["market"], r["book"])
    f = first.get(k)
    if not f or r["offset_min"] <= f[0]: continue
    mv.append({**r, "dline": float(r["line"]) - f[1]})
print(f"\n=== CONDITIONAL: line movement since the first in-play quote (n={len(mv)}) ===")
print(f"{'bucket':30s} {'ROI':>8s} {'SE':>7s} {'t':>7s} {'bets':>7s} {'games':>6s}")
cells = []
for lab, f in (("line DROPPED >=2 -> Over", lambda r: r["dline"] <= -2 and r["side"]=="Over"),
               ("line DROPPED >=2 -> Under", lambda r: r["dline"] <= -2 and r["side"]=="Under"),
               ("line ROSE >=2 -> Over", lambda r: r["dline"] >= 2 and r["side"]=="Over"),
               ("line ROSE >=2 -> Under", lambda r: r["dline"] >= 2 and r["side"]=="Under"),
               ("line flat -> Over", lambda r: abs(r["dline"]) < 1 and r["side"]=="Over"),
               ("line flat -> Under", lambda r: abs(r["dline"]) < 1 and r["side"]=="Under")):
    c = clustered([r for r in mv if f(r)])
    if c:
        cells.append((lab, c))
        print(f"{lab:30s} {c[0]:+7.2f}% {c[1]:6.2f} {c[2]:+7.2f} {c[3]:7d} {c[4]:6d}")
allcells = cells + []
for off in sorted({r["offset_min"] for r in g}):
    for side in ("Over","Under"):
        c = clustered([r for r in g if r["offset_min"]==off and r["side"]==side])
        if c: allcells.append((f"+{off}min {side}", c))
for mk in sorted({r["market"] for r in g}):
    for side in ("Over","Under"):
        c = clustered([r for r in g if r["market"]==mk and r["side"]==side])
        if c: allcells.append((f"{mk.replace('player_','')} {side}", c))
allcells.sort(key=lambda x: -x[1][0])
need = 2.7 + 0.35*math.log(max(len(allcells),1))
print(f"\n=== BEST CELLS OF ALL {len(allcells)} INSPECTED (Bonferroni |t| needed ~{need:.2f}) ===")
for lab, c in allcells[:6]:
    print(f"  {lab:30s} ROI {c[0]:+7.2f}%  t {c[2]:+6.2f}  n={c[3]:5d} games={c[4]}"
          + ("   <-- SURVIVES" if abs(c[2]) > need else ""))
surv = [x for x in allcells if abs(x[1][2]) > need and x[1][0] > 0]
print(f"\n  profitable cells surviving multiple testing: {len(surv)}")
print("\n=== POWER: what could this sample even detect? ===")
c = clustered([r for r in g if r["side"]=="Over"])
print(f"  clustered SE on the headline is {c[1]:.2f}pp over {c[4]} games")
print(f"  -> a real edge smaller than ~{2*c[1]:.1f}pp ROI is INVISIBLE at this sample size.")
print(f"  -> to resolve a +3% edge you would need ~{int(c[4]*(c[1]/1.5)**2)} games.")
