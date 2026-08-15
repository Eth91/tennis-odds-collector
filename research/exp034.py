"""EXP-034 §40/§19 AUDIT of EXP-033's t=+4.34. The finding is that flagged rungs drift toward the
over by +1.42pp more than non-flagged rungs. Before believing it, three specific kill-shots:

1. ⚠️ MEAN REVERSION (the §19 leakage). The flag FIRES ON A FAVOURABLE PRICE (EV >= threshold).
   If a cheap over is cheap partly by noise, it drifts back up regardless of any model insight.
   That would reproduce the entire effect with zero information. DECISIVE TEST: does the OPENING
   PRICE LEVEL alone predict drift, and do flagged rungs sit at systematically cheaper openers?
2. RUNG POSITION. Flagged rungs are chosen; non-flagged include the whole alt ladder. If low rungs
   drift up and high rungs drift down, and flagging concentrates low, that is the ladder, not skill.
3. MEDIAN IS +0.00pp ON BOTH SIDES. Most rungs never move; the mean gap comes from a minority.
   A handful of large moves can carry a t of 4.

If (1) explains it, EXP-033 is VOID under §19 and must not be interpreted."""
import sqlite3, statistics as st, math
from collections import defaultdict
tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=900)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
names = {}
for (n,) in tick.execute("SELECT DISTINCT player FROM obs"): names.setdefault(str(n).lower(), n)
def resolve(p):
    k = str(p).lower()
    return names.get(k) or next((v for kk, v in names.items() if k and (k in kk or kk in k)), None)
flag = set()
for date, player, stat, fline in clv.execute(
        "SELECT date,player,stat,flag_line FROM clv WHERE flagged_at IS NOT NULL AND flag_line "
        "IS NOT NULL AND date BETWEEN ? AND ?", (days[0], days[-1])):
    P = resolve(player)
    if P: flag.add((date, P, stat, float(fline)))
def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None
rec = []
for d in days:
    ser = defaultdict(list)
    for player, stat, line, ca, odds in tick.execute(
            "SELECT player, stat, line, collected_at, odds FROM obs WHERE d=? AND side='over' "
            "AND book='fd' ORDER BY player, stat, line, collected_at", (d,)):
        v = p_of(odds)
        if v is not None: ser[(player, stat, float(line))].append(v)
    for (player, stat, line), s in ser.items():
        if len(s) < 8: continue
        rec.append({"d": d, "stat": stat, "line": line, "open": s[0], "drift": s[-1] - s[0],
                    "flag": (d, player, stat, line) in flag})
print(f"{len(rec)} rungs; flagged {sum(1 for r in rec if r['flag'])}\n")
F = [r for r in rec if r["flag"]]; N = [r for r in rec if not r["flag"]]
def tt(a, b):
    if len(a) < 8 or len(b) < 8: return None, None
    m = st.mean(a) - st.mean(b)
    se = math.sqrt(st.pvariance(a)/len(a) + st.pvariance(b)/len(b)) or 1e-12
    return m, m/se
print("=== 1. MEAN REVERSION: does the OPENING PRICE alone predict drift? ===")
print(f"  flagged openers  : mean implied prob {st.mean([r['open'] for r in F]):.4f}")
print(f"  non-flagged      : mean implied prob {st.mean([r['open'] for r in N]):.4f}")
qs = sorted(r["open"] for r in rec)
cuts = [qs[len(qs)*i//5] for i in range(1, 5)]
print(f"  drift by opening-price quintile (ALL rungs, flagged or not):")
for i in range(5):
    lo = cuts[i-1] if i else -1; hi = cuts[i] if i < 4 else 2
    sel = [r["drift"] for r in rec if lo < r["open"] <= hi]
    if len(sel) >= 30:
        print(f"    Q{i+1} open<={hi:.3f}: n={len(sel):5d}  drift {st.mean(sel)*100:+6.2f}pp")
print("  ^ a strong monotone gradient here means CHEAP OVERS DRIFT UP regardless of the model.")
print("\n=== 2. WITHIN opening-price quintile, is flagged still better? (the decisive control) ===")
surv = []
for i in range(5):
    lo = cuts[i-1] if i else -1; hi = cuts[i] if i < 4 else 2
    a = [r["drift"] for r in F if lo < r["open"] <= hi]
    b = [r["drift"] for r in N if lo < r["open"] <= hi]
    m, t = tt(a, b)
    if m is None: print(f"    Q{i+1}: thin (flagged n={len(a)})"); continue
    surv.append(t)
    print(f"    Q{i+1}: flagged n={len(a):4d} {st.mean(a)*100:+6.2f}pp  vs  base n={len(b):5d} "
          f"{st.mean(b)*100:+6.2f}pp   diff {m*100:+6.2f}pp  t={t:+5.2f}")
if surv:
    print(f"  -> positive in {sum(1 for t in surv if t>0)}/{len(surv)} quintiles; "
          f"max |t| {max(abs(t) for t in surv):.2f}")
print("\n=== 3. WITHIN stat+line-level, is flagged still better? (rung-position control) ===")
for stat in ("points", "rebounds", "assists"):
    for lab, f in (("low<=5.5", lambda L: L <= 5.5), ("mid", lambda L: 5.5 < L <= 10.5),
                   ("high", lambda L: L > 10.5)):
        a = [r["drift"] for r in F if r["stat"] == stat and f(r["line"])]
        b = [r["drift"] for r in N if r["stat"] == stat and f(r["line"])]
        m, t = tt(a, b)
        if m is not None and len(a) >= 15:
            print(f"    {stat:9s} {lab:9s} flagged n={len(a):4d}  diff {m*100:+6.2f}pp  t={t:+5.2f}")
print("\n=== 4. IS IT A FEW BIG MOVES? ===")
fd = sorted((r["drift"] for r in F), reverse=True)
print(f"  flagged: {sum(1 for x in fd if abs(x)<1e-9)}/{len(fd)} never moved; "
      f"top-5 drifts {[f'{x*100:+.1f}' for x in fd[:5]]}")
trim = fd[5:-5] if len(fd) > 20 else fd
nb = sorted(r["drift"] for r in N)
ntrim = nb[5:-5]
m, t = tt(trim, ntrim)
print(f"  after trimming 5 largest AND 5 smallest from each side: diff {m*100:+.3f}pp  t={t:+.2f}"
      if m is not None else "  trim: thin")
