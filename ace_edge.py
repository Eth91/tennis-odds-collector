#!/usr/bin/env python3
"""TN-015 — is there any reason to believe the ace ladders are BEATABLE? Measure, do not assume.

The case FOR an edge is structural: Pinnacle does not price aces, so FanDuel has no sharp line to
copy and must price from its own model, and ace rate is a high-signal stable stat we can model.
The case AGAINST is also structural and, I think, stronger: the market is ONE-SIDED - overs only -
which is the signature of a recreational product, and recreational one-sided props are normally
shaded toward the side punters like. You cannot take the other side of a shade.

Only one of those is testable without waiting months, and it is the important one:

    WHAT DOES FANDUEL ACTUALLY THINK, and is it plausible?

The ladder implies a survival curve. Turning each rung into 1/odds gives P(>=k) INCLUDING vig, so
those numbers must sum-of-evidence HIGHER than truth by the margin. Comparing FanDuel's implied
curve against a model curve therefore has a known sign: FanDuel should sit above. The question is
BY HOW MUCH, and whether the excess is a plausible vig or a shade too big to beat.

MODEL CURVE: aces are overdispersed counts, so a negative binomial is fitted on history - mean
from the ace model, dispersion r estimated from how actual variance exceeds the mean.

An honest read has three outcomes:
    FanDuel far above the model    -> overs are shaded, no edge, and the one-sided format means
                                      there is nothing to do about it
    FanDuel close to the model     -> the margin is thin and an edge depends entirely on whether
                                      our mean beats theirs, which cannot be known yet
    FanDuel BELOW the model        -> genuinely mispriced overs, worth pursuing
"""
import json
import math
import re
import sqlite3
import statistics as st
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADB = HERE / "tennis_ace.sqlite"
FDB = HERE / "tennis_fd.sqlite"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def surname_key(name):
    p = [x for x in norm(name).split() if x]
    return p[-1] if p else None


# ---- 1. dispersion of ace counts, from history ----------------------------------------------
con = sqlite3.connect("file:%s?mode=ro" % ADB, uri=True, timeout=60)
hist = con.execute("SELECT player, surface, aces, svpt, sv_gms, year FROM ace_pm "
                   "WHERE svpt>0 AND year>=2022").fetchall()
pl_ace = defaultdict(list)
for pl, surf, a, sp, gm, yr in hist:
    pl_ace[norm(pl)].append(a)
con.close()

# NB dispersion: pool players with enough matches, Var = mu + mu^2/r
rs = []
for pl, v in pl_ace.items():
    if len(v) >= 25:
        mu = st.mean(v)
        var = st.pvariance(v)
        if var > mu > 0.5:
            rs.append(mu * mu / (var - mu))
R_DISP = st.median(rs) if rs else 4.0
print("negative-binomial dispersion r fitted on %d players with >=25 matches: r = %.2f"
      % (len(rs), R_DISP))
print("   (r -> infinity would be Poisson; a finite r means ace counts are OVERDISPERSED,")
print("    which is why a Poisson tail would understate the big-serving upside.)")


def nb_sf(k, mu, r):
    """P(X >= k) for a negative binomial with mean mu and dispersion r."""
    if mu <= 0:
        return 0.0
    p = r / (r + mu)
    # P(X = i) recursively, then survival
    pmf = p ** r
    cdf = pmf
    for i in range(1, int(k)):
        pmf *= (r + i - 1) / i * (1 - p)
        cdf += pmf
    return max(0.0, min(1.0, 1.0 - cdf))


# ---- 2. player ace means, as-of, from recent history -----------------------------------------
pl_mu = {}
for pl, v in pl_ace.items():
    if len(v) >= 10:
        pl_mu[pl] = st.mean(v)
print("players with a usable recent ace mean: %d" % len(pl_mu))

# ---- 3. FanDuel ladders currently on the board ------------------------------------------------
fd = sqlite3.connect("file:%s?mode=ro" % FDB, uri=True, timeout=60)
rows = fd.execute("""SELECT event_id, event_name, tour, best_of, market_type, market_name,
                            runner_name, odds, collected_at
                     FROM fd_tennis WHERE market_type IN ('PLAYER_A_ACES','PLAYER_B_ACES')""").fetchall()
fd.close()
lad = defaultdict(dict)
meta = {}
for eid, ev, tour, bo, mt, mname, rname, odds, ts in rows:
    m = re.match(r"^\s*(\d+)\+", str(rname))
    if not m:
        continue
    key = (eid, mt)
    lad[key][int(m.group(1))] = float(odds)
    meta[key] = (str(mname), tour, bo, ev)
print("ace ladders on the board: %d" % len(lad))

print()
print("=" * 96)
print("FANDUEL IMPLIED P(>=k)  vs  a negative-binomial model on the player's recent ace mean")
print("=" * 96)
gaps = defaultdict(list)
shown = 0
for key, rungs in sorted(lad.items()):
    mname, tour, bo, ev = meta[key]
    who = re.sub(r"\s+Aces\s*$", "", mname).strip()
    mu_h = pl_mu.get(norm(who))
    if mu_h is None:
        k2 = surname_key(who)
        cand = [v for k, v in pl_mu.items() if surname_key(k) == k2]
        mu_h = cand[0] if len(cand) == 1 else None
    if mu_h is None:
        continue
    # ATP best-of-5 plays ~55% more service games than the bo3 history is built from
    mu = mu_h * (1.45 if bo == 5 else 1.0)
    line = []
    for k in sorted(rungs):
        imp = 1.0 / rungs[k]
        mod = nb_sf(k, mu, R_DISP)
        gaps[k].append(imp - mod)
        line.append("%d+: FD %.3f mdl %.3f" % (k, imp, mod))
    if shown < 6:
        print("   %-26s (%s bo%s) mu=%.1f" % (who[:26], tour, bo, mu))
        print("      " + " | ".join(line[:5]))
        shown += 1

print()
print("   %-8s %8s %10s %10s" % ("rung", "n", "mean gap", "median"))
allg = []
for k in sorted(gaps):
    v = gaps[k]
    if len(v) >= 5:
        print("   %-8s %8d %+10.4f %+10.4f" % ("%d+" % k, len(v), st.mean(v), st.median(v)))
        allg += v
if allg:
    print()
    print("   OVERALL mean gap (FanDuel implied minus model) = %+.4f over %d rungs"
          % (st.mean(allg), len(allg)))
    print()
    print("   A positive gap is EXPECTED - FanDuel's implied probabilities contain the vig, so")
    print("   they must exceed any unbiased estimate. The question is the SIZE.")
    g = st.mean(allg)
    if g > 0.12:
        print("   -> %+.3f is far more than a plausible margin: the overs look SHADED, and a"
              % g)
        print("      one-sided market gives no way to take the other side of a shade.")
    elif g > 0.04:
        print("   -> %+.3f is in the range of a normal-to-rich margin. An edge would depend"
              % g)
        print("      entirely on our mean beating theirs, which is not yet knowable.")
    else:
        print("   -> %+.3f is thin. Worth pursuing." % g)
