"""Is the birdie model's player-to-player SPREAD calibrated, or just its level?

Section 6 of the audit anchors and checks the MEAN P(over) against the mean fair price. A model
can match the mean exactly and still be badly wrong if its spread across players is too wide:
it would then price high-rate players too high and low-rate players too low, flagging OVERS on
one tail and UNDERS on the other. That produces a perfectly balanced 5-over/5-under split — the
very pattern I called "healthy two-sidedness" after fixing the vig anchor.

So: compare the sd of our P(over) across the posted lines to the sd of the DEVIGGED market P(over)
on the same lines, and regress ours on theirs. A slope above 1 means we are over-dispersed and the
tail flags are artifacts of spread rather than knowledge.
"""
import re
import sqlite3
import statistics as st

import pga_birdies as B
import pga_context as C
import pga_field as PF
import pga_ruler as RU

evn = PF.event().get("name") or ""
cf, _ = C.course_factor(evn)
la, lo = PF.coords()
wind = C.live_wind_stat(la, lo) if la is not None else None
tid = B.tid_for_name(evn)
mix = B.mix_for(tid) if tid else B.DEFAULT_MIX
BR, _fr = B.rates(course_factor=cf, wind_kmh=wind)
BRn = {RU.norm(k): v for k, v in BR.items()}

con = sqlite3.connect("golf_lines.sqlite")
ts = con.execute("SELECT MAX(collected_at) FROM golf_lines WHERE mtype LIKE '%BIRD%'").fetchone()[0]
rows = con.execute("SELECT market, runner, odds FROM golf_lines WHERE mtype LIKE '%BIRD%' "
                   "AND collected_at=?", (ts,)).fetchall()
con.close()

q = {}
for mkt, run, od in rows:
    pm = re.match(r"(.+?)\s+Total Birdies or Better", mkt)
    sm = re.search(r"(Over|Under)\s+([\d.]+)", run)
    if pm and sm:
        q.setdefault((pm.group(1).strip(), float(sm.group(2))), {})[sm.group(1).lower()] = od

# LAM exactly as e3 sets it: anchored to the mean DEVIGGED fair over
pairs = []
for (pl, ln), v in q.items():
    if "over" not in v or "under" not in v:
        continue
    rr = BRn.get(RU.norm(pl))
    if not rr:
        continue
    io_, iu = 1 / v["over"], 1 / v["under"]
    pairs.append((pl, ln, rr, io_ / (io_ + iu), v["over"]))
print("two-sided lines with a rated player: %d" % len(pairs))
if len(pairs) < 8:
    raise SystemExit("too few")

tgt = st.mean(p[3] for p in pairs)
lo_, hi_ = 0.5, 1.6
for _ in range(40):
    LAM = (lo_ + hi_) / 2
    m = st.mean(B.p_x_or_more({k: min(x * LAM, .95) for k, x in rr.items()}, int(ln + .5), mix)
                for _pl, ln, rr, _f, _o in pairs)
    if m > tgt:
        hi_ = LAM
    else:
        lo_ = LAM

ours, fair = [], []
for _pl, ln, rr, f, _o in pairs:
    ours.append(B.p_x_or_more({k: min(x * LAM, .95) for k, x in rr.items()}, int(ln + .5), mix))
    fair.append(f)

print("LAM=%.4f  (level matched by construction)" % LAM)
print("  mean  ours %.4f | market fair %.4f   (gap %+.2f pts)"
      % (st.mean(ours), st.mean(fair), 100 * (st.mean(ours) - st.mean(fair))))
print("  SPREAD (sd across players):")
print("        ours %.4f | market fair %.4f   -> ratio %.2fx"
      % (st.pstdev(ours), st.pstdev(fair), st.pstdev(ours) / max(st.pstdev(fair), 1e-9)))
mx, my = st.mean(fair), st.mean(ours)
den = sum((x - mx) ** 2 for x in fair)
slope = sum((x - mx) * (y - my) for x, y in zip(fair, ours)) / den if den else 0
sx, sy = st.pstdev(fair), st.pstdev(ours)
r = (sum((x - mx) * (y - my) for x, y in zip(fair, ours)) / len(fair) / (sx * sy)) if sx and sy else 0
print("  regression of OURS on MARKET FAIR: slope %+.3f  r %+.3f" % (slope, r))
print()
if slope > 1.25:
    print("  OVER-DISPERSED: slope %.2f means we amplify the market's player differences." % slope)
    print("  The balanced over/under flag split is then a SPREAD artefact, not knowledge —")
    print("  we flag the high tail as overs and the low tail as unders. Shrinking our")
    print("  player-relative rates toward the field by 1/slope would remove it.")
elif slope < 0.75:
    print("  UNDER-DISPERSED: we compress player differences the market believes in.")
else:
    print("  DISPERSION OK: our player spread tracks the market's (slope %.2f)." % slope)
print("  r=%.2f is the more important number: it says how much of the market's player-to-player" % r)
print("  variation we reproduce at all. Low r with matched sd = we disagree at random.")
