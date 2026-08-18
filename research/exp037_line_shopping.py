"""REAL line shopping: FanDuel's over price vs DraftKings' over price at the SAME rung and the
SAME moment. Measured as a PRICE question, not an ROI question -- price has vastly more power
because it does not depend on who won, and it converts 1:1 into ROI on a fixed selection.

(My first attempt used predictions.odds_other, which is the OPPOSITE-SIDE (under) price, not a
second book. Taking max() of those credits the under's price on an over bet. Void.)"""
import sqlite3, statistics as st, math
from collections import defaultdict
tick = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/tick_archive.sqlite?mode=ro",
                       uri=True, timeout=900)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
print(f"archive days: {len(days)}  {days[0]}..{days[-1]}")
gain, both, fdbest, dkbest = [], 0, 0, 0
for d in days:
    last = {}
    for player, stat, line, book, ca, odds in tick.execute(
            "SELECT player,stat,line,book,collected_at,odds FROM obs WHERE d=? AND side='over' "
            "ORDER BY collected_at", (d,)):
        if book in ("fd", "dk"):
            last[(player, stat, float(line), book)] = float(odds)
    keys = {(p, s, l) for (p, s, l, _b) in last}
    for k in keys:
        f = last.get((*k, "fd")); dk = last.get((*k, "dk"))
        if not f or not dk or f <= 1 or dk <= 1: continue
        both += 1
        best = max(f, dk)
        gain.append(best / f - 1.0)
        if f > dk: fdbest += 1
        elif dk > f: dkbest += 1
print(f"\nrungs quoted by BOTH books (last pre-game price): {both}")
if gain:
    m = st.mean(gain); se = st.pstdev(gain)/math.sqrt(len(gain))
    print(f"  best-of-two vs FanDuel alone: {m*100:+.2f}% better price  (t={m/se:.1f})")
    print(f"  FanDuel already best: {fdbest} ({fdbest/both*100:.1f}%)   "
          f"DraftKings better: {dkbest} ({dkbest/both*100:.1f}%)   tie: {both-fdbest-dkbest}")
    print(f"  median uplift when dk is better: "
          f"{st.median([g for g in gain if g>0])*100:.2f}%" if dkbest else "")
    print(f"\n  >>> a fixed selection bet at best-of-two earns ~{m*100:.2f}pp MORE ROI than")
    print(f"      the same selection bet on FanDuel alone. That is free: same bets, better price.")
print("\n=== does the advantage concentrate anywhere? ===")
bys = defaultdict(list)
for d in days[:1]: pass
for d in days:
    last = {}
    for player, stat, line, book, ca, odds in tick.execute(
            "SELECT player,stat,line,book,collected_at,odds FROM obs WHERE d=? AND side='over' "
            "ORDER BY collected_at", (d,)):
        if book in ("fd","dk"): last[(player,stat,float(line),book)]=float(odds)
    for (p,s,l,bk) in list(last):
        if bk!="fd": continue
        f=last[(p,s,l,"fd")]; dk=last.get((p,s,l,"dk"))
        if not dk or f<=1 or dk<=1: continue
        bys[s].append(max(f,dk)/f-1.0)
        bys["line<=5.5" if l<=5.5 else ("5.5-10.5" if l<=10.5 else ">10.5")].append(max(f,dk)/f-1.0)
for k,v in sorted(bys.items()):
    if len(v)>=50: print(f"  {k:10s} n={len(v):5d}  uplift {st.mean(v)*100:+.2f}%")
