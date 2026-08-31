"""WHERE ARE WE IN THE INFORMATION RACE? For each flagged bet, how much of the market's
open→close move had ALREADY happened by the time we flagged?

  captured = (price_at_flag - price_at_open) / (price_at_close - price_at_open)

  ~0  => we flag BEFORE the market moves      -> we are genuinely early; the gap is ours
  ~1  => the move is already done when we flag -> we are late, buying an adjusted price
  >1  => we flag past the eventual close       -> we overpay and it comes back

Measured in implied probability. Only rungs with a real open, a flag-time price and a close.
"""
import sqlite3, datetime as dt, statistics as st, bisect
tick = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/research/tick_archive.sqlite?mode=ro",
                       uri=True, timeout=300)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
names = {}
for (n,) in tick.execute("SELECT DISTINCT player FROM obs"): names.setdefault(str(n).lower(), n)
def res(p):
    k = str(p).lower()
    return names.get(k) or next((v for kk, v in names.items() if k and (k in kk or kk in k)), None)
clv = sqlite3.connect("file:/home/ubuntu/tennis-odds-collector/wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
ev = clv.execute("SELECT date,player,stat,flag_line,flagged_at FROM clv WHERE flagged_at IS NOT NULL "
                 "AND flag_line IS NOT NULL AND date BETWEEN ? AND ?", (days[0], days[-1])).fetchall()
def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None
caps, moves = [], []
for date, player, stat, fline, fat in ev:
    P = res(player)
    if not P: continue
    s = tick.execute("SELECT collected_at, odds FROM obs WHERE d=? AND player=? AND stat=? AND line=? "
                     "AND side='over' AND book='fd' ORDER BY collected_at",
                     (date, P, stat, float(fline))).fetchall()
    if len(s) < 6: continue
    ts = [dt.datetime.fromisoformat(str(x[0])) for x in s]
    pr = [p_of(x[1]) for x in s]
    T = dt.datetime.fromisoformat(str(fat))
    k = bisect.bisect_left(ts, T)
    if k == 0 or k >= len(ts): continue          # need a price before AND after the flag
    o, f, c = pr[0], pr[k-1], pr[-1]
    if None in (o, f, c): continue
    total = c - o
    if abs(total) < 0.005: continue              # no meaningful move to attribute
    caps.append((f - o) / total)
    moves.append(total)
print(f"flagged rungs with a full open→flag→close series: {len(caps)}")
if caps:
    caps.sort()
    n = len(caps)
    def q(p): return caps[min(int(n*p), n-1)]
    print(f"\nSHARE OF THE OPEN→CLOSE MOVE ALREADY DONE WHEN WE FLAGGED:")
    print(f"  median {st.median(caps)*100:6.1f}%   p25 {q(.25)*100:6.1f}%   p75 {q(.75)*100:6.1f}%")
    print(f"  flagged BEFORE any of the move (<=0):      {sum(1 for x in caps if x <= 0)}/{n}"
          f" = {sum(1 for x in caps if x <= 0)/n*100:.0f}%")
    print(f"  flagged before HALF the move (<0.5):       {sum(1 for x in caps if x < 0.5)}/{n}"
          f" = {sum(1 for x in caps if x < 0.5)/n*100:.0f}%")
    print(f"  flagged AFTER the move was done (>=1):     {sum(1 for x in caps if x >= 1)}/{n}"
          f" = {sum(1 for x in caps if x >= 1)/n*100:.0f}%")
    print(f"\n  mean |open→close| move: {st.mean([abs(m) for m in moves])*100:.2f}pp implied prob")
    print("\n  READ: a low share = we are EARLY and the gap is real. A high share = the price we")
    print("        take has already absorbed the news, and speed is not what we are being paid for.")
