"""Verify the rank offsets: field sums preserved, win untouched, tail shrunk, favourites lifted."""
import pga_ruler as RU

R_raw, _ = RU.fit(asof="2026-08-13")
R = {RU.norm(k): v for k, v in R_raw.items()}
field = list(R_raw)[:150]
ok = True

new = RU.simulate(R, field, n_sims=8000, seed=11, cut_n=65, shape_slope=RU.shape_slopes("x"))

# 1. field totals must still be exact — the offsets re-solve an intercept to hold them
print("field totals (must be 1 / 5 / 10 / 20):")
for k, want in (("win", 1.0), ("top5", 5.0), ("top10", 10.0), ("top20", 20.0)):
    got = sum(v[k] for v in new.values())
    good = abs(got - want) < 0.02
    ok &= good
    print("   %-8s %8.4f  %s" % (k, got, "ok" if good else "FAIL"))

# 2. win must be untouched by the rank layer
import copy
raw = RU.simulate(R, field, n_sims=8000, seed=11, cut_n=65, shape_slope=RU.shape_slopes("x"))
o2 = copy.deepcopy(raw)
RU._recal_rank(o2, ("top5", "top10", "top20"))
dwin = max(abs(raw[p]["win"] - o2[p]["win"]) for p in raw)
print("\nwin max |delta| from the rank layer: %.12f  %s" % (dwin, "ok" if dwin == 0.0 else "FAIL"))
ok &= (dwin == 0.0)

# 3. direction: favourites up, tail down — the whole point
order = sorted(raw, key=lambda p: -raw[p]["win"])
for lbl, sl in (("rank 1", order[:1]), ("rank 2-5", order[1:5]),
                ("rank 16-40", order[15:40]), ("rank 41+", order[40:])):
    a = sum(raw[p]["top20"] for p in sl) / len(sl)
    b = sum(o2[p]["top20"] for p in sl) / len(sl)
    print("   %-11s top20 %.4f -> %.4f  (%+.4f)" % (lbl, a, b, b - a))
    if lbl == "rank 41+":
        ok &= (b < a)
    if lbl in ("rank 1", "rank 2-5"):
        ok &= (b > a)

print("\n%s" % ("PASS" if ok else "FAIL"))
raise SystemExit(0 if ok else 1)
