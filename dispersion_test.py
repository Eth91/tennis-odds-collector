#!/usr/bin/env python3
"""Why is the simulated cut line 1.5x too narrow, and which mechanism fixes it?

MEASURED DEFECT: field-relative 36-hole cut line covers 48.4% of a nominal 80% band, sd(z)=1.46.
The realised residual sd is 0.83 strokes against a simulated 0.49.

tau is ruled out already — it is common-mode and cancels exactly out of anything field-relative.
Two candidates remain, and they are testable against the same number:

  A  PLAYER-WEEK effect (what pga_ruler has, RHO=0.05): score = mean + week_p + eps_pr, with
     week_p ~ N(0, RHO*sig^2), eps ~ N(0, (1-RHO)*sig^2). Re-attributes variance, keeps the
     per-round total at sig^2. ⚠️ ARITHMETIC SAYS THIS CANNOT BE ENOUGH: 36-hole variance goes
     2*sig^2 -> (2+2*RHO)*sig^2, so even RHO=1 widens the cut line only sqrt(2)=1.41x, short of
     the 1.7x needed. Included anyway to confirm the bound empirically rather than assert it.

  B  PER-EVENT DISPERSION multiplier: sigma is scaled by S ~ lognormal(0, XI) once per event.
     Some weeks the field bunches, some it spreads. This is NOT a level shift, so it survives
     field-relativisation and can move the cut line relative to the field mean.

Scored the same way as before: interval coverage of the realised value in the simulated p10-p90,
and sd of the standardised residual. Target 0.80 and 1.00.
"""
import datetime as dt
import sqlite3
import sys
import time
from collections import defaultdict

import numpy as np

import pga_ruler as RU
import pga_sim as PS
import pga_sim_validate as V

NEV = int(sys.argv[1]) if len(sys.argv) > 1 else 60
NSIM = 4000
RHOS = [0.0, 0.05, 0.25, 0.60, 1.00]
XIS = [0.0, 0.05, 0.10, 0.15, 0.22]

events = V.load_events()
all_rows = RU.all_rows()
first = min(e["date"] for e in events)
burn = (dt.date.fromisoformat(str(first)[:10]) + dt.timedelta(days=270)).isoformat()
usable = [e for e in events if e["date"] >= burn and e["struct"] == "cut_R2"]
step = max(1, len(usable) // NEV)
usable = usable[::step][:NEV]
print("cut events: %d  sims %d" % (len(usable), NSIM), flush=True)

con = sqlite3.connect("file:%s?mode=ro" % RU.DB, uri=True, timeout=60)
cases = []
t0 = time.time()
for i, ev in enumerate(usable, 1):
    byp = defaultdict(dict)
    for p, r, s in con.execute("SELECT player, rnd, score FROM rounds WHERE event_id=?",
                               (ev["eid"],)):
        byp[p][int(r)] = float(s)
    r12 = {p: v for p, v in byp.items() if 1 in v and 2 in v}
    adv = {p: v[1] + v[2] for p, v in byp.items() if 3 in v and 1 in v and 2 in v}
    if len(r12) < 60 or not adv:
        continue
    R, _g = PS.ratings_asof(ev["date"], rows=V._train_rows(all_rows, ev["date"]))
    mus, sgs, rated = [], [], []
    for p in r12:
        r = PS.lookup(R, p)
        if r:
            mus.append(r[0]); sgs.append(r[1]); rated.append(p)
    if not rated:
        continue
    rs = set(rated)
    fm = sum(r12[p][1] + r12[p][2] for p in rated) / len(rated)
    adv_r = {p: v for p, v in adv.items() if p in rs}
    if not adv_r:
        continue
    actual = max(adv_r.values()) - fm      # cut line AND mean over the same rated field
    if len(mus) < 50:
        continue
    cn_full = RU.cut_rule(ev["name"], ev["date"], n_field=len(r12))
    if cn_full is None:
        continue
    # rescale the cut RANK to the rated subset: a top-65 cut in a 156-man field is not a
    # top-65 cut among the 120 we can rate, and drawing it at the wrong rank moves the line
    cn = max(5, int(round(cn_full * len(mus) / float(len(r12)))))
    if len(mus) <= cn:
        continue
    cases.append((np.array(mus), np.array(sgs), int(cn), float(actual)))
    if i % 15 == 0:
        print("   ... %d/%d (%.1f min)" % (i, len(usable), (time.time() - t0) / 60), flush=True)
con.close()
print("usable cut events: %d\n" % len(cases), flush=True)


def sim_cut(mu, sg, cn, rho, xi, seed):
    """36-hole cut line, field-relative, under a player-week effect and/or event dispersion."""
    rng = np.random.default_rng(seed)
    k = mu.size
    S = np.exp(rng.normal(0.0, xi, size=(NSIM, 1))) if xi > 0 else 1.0
    sg2 = sg[None, :] * S
    mu2 = mu[None, :] * S                       # spread scales the field, not just the noise
    wk = rng.normal(0, 1, (NSIM, k)) * sg2 * np.sqrt(rho) if rho > 0 else 0.0
    e1 = rng.normal(0, 1, (NSIM, k)) * sg2 * np.sqrt(1 - rho)
    e2 = rng.normal(0, 1, (NSIM, k)) * sg2 * np.sqrt(1 - rho)
    tot = 2 * mu2 + 2 * wk + e1 + e2
    tot = np.rint(tot)
    line = np.sort(tot, axis=1)[:, cn - 1]
    return line - tot.mean(axis=1)              # FIELD-RELATIVE, so nothing common-mode survives


def score(rho, xi):
    z, cov = [], []
    for j, (mu, sg, cn, act) in enumerate(cases):
        v = sim_cut(mu, sg, cn, rho, xi, 100 + j)
        m, s = float(v.mean()), float(v.std())
        if s <= 0:
            continue
        z.append((act - m) / s)
        cov.append(float(np.quantile(v, .10) <= act <= np.quantile(v, .90)))
    return float(np.mean(z)), float(np.std(z)), float(np.mean(cov)), len(z)


print("=" * 74)
print("A — PLAYER-WEEK EFFECT (rho).  target sd(z)=1.00, cover80=0.80")
print("=" * 74)
print("   %-8s %8s %8s %9s %6s" % ("rho", "bias", "sd(z)", "cover80", "n"))
for r in RHOS:
    b, s, c, n = score(r, 0.0)
    print("   %-8.2f %8.2f %8.2f %9.3f %6d" % (r, b, s, c, n))

print("\n" + "=" * 74)
print("B — PER-EVENT DISPERSION (xi), no player-week")
print("=" * 74)
print("   %-8s %8s %8s %9s %6s" % ("xi", "bias", "sd(z)", "cover80", "n"))
for x in XIS:
    b, s, c, n = score(0.0, x)
    print("   %-8.2f %8.2f %8.2f %9.3f %6d" % (x, b, s, c, n))

print("\n" + "=" * 74)
print("A+B — pga_ruler's rho=0.05 plus dispersion")
print("=" * 74)
print("   %-8s %8s %8s %9s %6s" % ("xi@rho.05", "bias", "sd(z)", "cover80", "n"))
for x in XIS:
    b, s, c, n = score(0.05, x)
    print("   %-8.2f %8.2f %8.2f %9.3f %6d" % (x, b, s, c, n))
