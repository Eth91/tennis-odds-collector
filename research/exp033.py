"""EXP-033 THE OPENING-PRICE TEST. The most distinctive fact found so far is EXP-028's: 46.6% of
flags happen BEFORE any price exists for that player-stat. That is not a stale book -- it is a
market that has not opened. Repricing cannot be the mechanism there. The testable question is:

    when the line finally opens, is the opener ALREADY correct, or does it drift afterwards?

If flagged players' openers drift toward the over MORE than non-flagged players' openers on the
same days, the model knows something the opening price does not, and the execution window is AT
POSTING rather than after news.

BASELINE IS MANDATORY (§26). Openers drift generally as game time approaches -- EXP-030 measured
+0.65pp of pure drift in its placebo. So flagged drift is compared against non-flagged drift on
the SAME days at the SAME rungs, not against zero.

Sign: POSITIVE = over got more expensive after opening = market moved TOWARD the model."""
import sqlite3, datetime as dt, statistics as st, math
from collections import defaultdict
tick = sqlite3.connect("file:research/tick_archive.sqlite?mode=ro", uri=True, timeout=900)
days = [r[0] for r in tick.execute("SELECT DISTINCT d FROM obs ORDER BY d")]
clv = sqlite3.connect("file:wnba_clv.sqlite?mode=ro", uri=True, timeout=30)
names = {}
for (n,) in tick.execute("SELECT DISTINCT player FROM obs"): names.setdefault(str(n).lower(), n)
def resolve(p):
    k = str(p).lower()
    return names.get(k) or next((v for kk, v in names.items() if k and (k in kk or kk in k)), None)
flag = {}
for date, player, stat, fline, fat in clv.execute(
        "SELECT date,player,stat,flag_line,flagged_at FROM clv WHERE flagged_at IS NOT NULL "
        "AND flag_line IS NOT NULL AND date BETWEEN ? AND ?", (days[0], days[-1])):
    P = resolve(player)
    if P: flag[(date, P, stat, float(fline))] = str(fat)
print(f"{len(flag)} flagged (day,player,stat,line) keys resolved into the archive")
def p_of(o):
    o = float(o); return 1.0/o if o > 1.0 else None
fl_drift, nf_drift = [], []
fl_pre, nf_pre = [], []      # openers where the flag PRECEDED the opener (the 46.6% case)
for d in days:
    ser = defaultdict(list)
    for player, stat, line, ca, odds in tick.execute(
            "SELECT player, stat, line, collected_at, odds FROM obs WHERE d=? AND side='over' "
            "AND book='fd' ORDER BY player, stat, line, collected_at", (d,)):
        v = p_of(odds)
        if v is not None: ser[(player, stat, float(line))].append((str(ca), v))
    for (player, stat, line), s in ser.items():
        if len(s) < 8: continue
        opener, close = s[0][1], s[-1][1]
        drift = close - opener
        k = (d, player, stat, line)
        if k in flag:
            fl_drift.append(drift)
            if flag[k] < s[0][0]:            # flagged BEFORE the line opened
                fl_pre.append(drift)
        else:
            nf_drift.append(drift)
    print(f"  {d}: flagged {len(fl_drift)} / non-flagged {len(nf_drift)} rungs", flush=True)
def rep(v, lab):
    if len(v) < 10: print(f"  {lab:34s} thin (n={len(v)})"); return None
    print(f"  {lab:34s} n={len(v):5d}  mean {st.mean(v)*100:+6.2f}pp  median {st.median(v)*100:+6.2f}pp")
    return v
print("\n=== OPENER -> LAST PRE-GAME DRIFT (implied prob) ===")
a = rep(fl_drift, "FLAGGED rungs"); b = rep(nf_drift, "NON-FLAGGED rungs (baseline)")
c = rep(fl_pre, "FLAGGED **before** line opened")
if a and b:
    m1, m2 = st.mean(a), st.mean(b)
    se = math.sqrt(st.pvariance(a)/len(a) + st.pvariance(b)/len(b)) or 1e-12
    print(f"\n  flagged - baseline: {(m1-m2)*100:+.3f}pp   t = {(m1-m2)/se:+.2f}")
    print(f"  -> {'FLAGGED RUNGS DRIFT MORE' if abs((m1-m2)/se) > 2 else 'no drift difference: the opener already reflects it'}")
if c and b:
    m1, m2 = st.mean(c), st.mean(b)
    se = math.sqrt(st.pvariance(c)/len(c) + st.pvariance(b)/len(b)) or 1e-12
    print(f"  flagged-before-open - baseline: {(m1-m2)*100:+.3f}pp   t = {(m1-m2)/se:+.2f}   n={len(c)}")
    print("  ^ this is the 46.6% cohort: the model knew before the market existed.")
