"""Direction check: a hot R1 must shift a player UP, a cold R1 DOWN. A sign error here would be
invisible in the flag count and catastrophic in the prices."""
import pga_birdies as B

tid = B.tid_for_name("PGA Rocket Classic 2026")
live = B.live_rounds(tid, "PGA Rocket Classic 2026")
usable = {p: (h, b) for p, (h, b) in live.items() if h >= B.FORM_MIN_HOLES}
th = sum(h for h, _ in usable.values()); tb = sum(b for _, b in usable.values())
field = tb / th
print("  field R1: %.4f birdies/hole over %d holes (%d players)" % (field, th, len(usable)))

before, _ = B.rates(course_factor=1.045, wind_kmh=18.9, course_name="PGA Rocket Classic 2026")
after, _ = B.rates(course_factor=1.045, wind_kmh=18.9, course_name="PGA Rocket Classic 2026",
                   live_tid=tid, live_tname="PGA Rocket Classic 2026")

rankable = sorted(usable.items(), key=lambda kv: -(kv[1][1] / kv[1][0]))
print("\n  %-24s %5s %6s %9s %9s %8s" % ("player", "R1 b", "rate", "before", "after", "delta"))
for pl, (h, b) in rankable[:5] + rankable[-5:]:
    if pl not in before or pl not in after:
        continue
    bb = sum(before[pl].values()) / len(before[pl])
    aa = sum(after[pl].values()) / len(after[pl])
    print("  %-24s %5d %6.3f %9.4f %9.4f %+8.4f%s"
          % (pl[:24], b, b / h, bb, aa, aa - bb,
             "   <- hot" if b / h > field else "   <- cold"))

hot = [p for p, (h, b) in usable.items() if b / h > field and p in before]
cold = [p for p, (h, b) in usable.items() if b / h < field and p in before]
def mean_delta(g):
    d = [sum(after[p].values()) / len(after[p]) - sum(before[p].values()) / len(before[p]) for p in g]
    return sum(d) / len(d) if d else 0
print("\n  mean shift, HOT players  (%3d): %+.5f  <- must be POSITIVE" % (len(hot), mean_delta(hot)))
print("  mean shift, COLD players (%3d): %+.5f  <- must be NEGATIVE" % (len(cold), mean_delta(cold)))
ok = mean_delta(hot) > 0 > mean_delta(cold)
print("\n  DIRECTION: %s" % ("correct" if ok else "*** WRONG — sign error, do not ship ***"))
