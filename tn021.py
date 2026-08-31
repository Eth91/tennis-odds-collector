#!/usr/bin/env python3
"""TN-021 — the three untested markets: TOTAL GAMES, GAME HANDICAP, SET WINNERS. All Shin-devigged.

TN-019 established that proportional de-vigging manufactures a longshot edge, so every comparison
here uses SHIN from the start rather than discovering the artifact a second time.

TOTAL GAMES and GAME HANDICAP are direct: both books quote them, so join on the identical line and
compare. This is only possible now that the FanDuel line is parsed out of the runner name.

SET WINNERS need a derived reference, because Pinnacle does not quote them. For best-of-3 its three
markets pin the whole set-score distribution down:

    M = P(A wins match)          from the moneyline
    S = P(straight sets)         from the set total at 2.5
    a = P(A wins 2-0)            from the set spread at 1.5

With outcomes {A 2-0, A 2-1, B 2-1, B 2-0} = {a, b, c, d}: M = a+b, S = a+d, a+b+c+d = 1.
A player who wins 2-1 took exactly one of the first two sets, so
    P(A wins set 1) = a*1 + (b+c)*0.5 + d*0 = a + (1-S)/2
since b+c = 1-S. Every term comes from a sharp quote; no model is involved.
"""
import math
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from datetime import datetime as D
from pathlib import Path

HERE = Path(__file__).resolve().parent


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def surn(n):
    p = [x for x in norm(n).split() if x]
    return p[-1] if p else ""


def pk(a, b):
    return tuple(sorted([surn(a), surn(b)]))


def tsd(a, b):
    try:
        return abs((D.fromisoformat(a[:19]) - D.fromisoformat(b[:19])).total_seconds()) / 60.0
    except Exception:                                                   # noqa: BLE001
        return 1e9


def shin2(o1, o2):
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(160):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q]
    t = sum(p)
    return p[0] / t, p[1] / t


fd = sqlite3.connect("file:%s?mode=ro" % (HERE / "tennis_fd.sqlite"), uri=True, timeout=60)
pn = sqlite3.connect("file:%s?mode=ro" % (HERE / "odds.sqlite"), uri=True, timeout=60)
F = fd.execute("""SELECT event_name, tour, best_of, start_time, market_type, runner_name,
                         line, side, odds, collected_at FROM fd_tennis""").fetchall()
Praw = pn.execute("""SELECT p1, p2, start_time, collected_at, ml1, ml2, set_total_line, set_over,
                            set_under, set_spread, spr_home, spr_away, games_line, games_over,
                            games_under, games_spread, gspr_home, gspr_away
                     FROM odds WHERE collected_at >= '2026-08-29'""").fetchall()
fd.close()
pn.close()
P = defaultdict(list)
for r in Praw:
    P[(pk(r[0], r[1]), str(r[2])[:10])].append(r)
FE = defaultdict(list)
for r in F:
    parts = str(r[0]).split(" v ")
    if len(parts) == 2:
        FE[(pk(parts[0], parts[1]), str(r[3])[:10])].append(r + (parts[0], parts[1]))
shared = sorted(set(FE) & set(P))
print("matches joined: %d" % len(shared))

tg, gh, sw = [], [], []
for key in shared:
    for r in FE[key]:
        (ev, tour, bo, stt, mt, rn, line, side, od, ts, pA, pB) = r
        cands = P[key]
        c = min(cands, key=lambda x: tsd(str(x[3]), ts))
        if tsd(str(c[3]), ts) > 25:
            continue
        (cp1, cp2, cstt, cts, ml1, ml2, stl, so, su, ssp, sph, spa,
         gl, go, gu, gsp, gh_h, gh_a) = c
        # ---------- TOTAL GAMES ----------
        if mt in ("MATCH_TOTAL_GAMES", "ALTERNATIVE_MATCH_TOTAL_GAMES") and line and gl \
                and go and gu and abs(float(gl) - float(line)) < 1e-6 and side in ("over", "under"):
            f_over, f_under = shin2(go, gu)
            fair = f_over if side == "over" else f_under
            tg.append((fair * od - 1, fair, tour))
        # ---------- GAME HANDICAP ----------
        if mt in ("ALTERNATIVE_MATCH_GAME_HANDICAP", "MAIN_SET_GAME_HANDICAP") and line is not None \
                and gsp is not None and gh_h and gh_a:
            same = surn(rn) == surn(cp1)
            pin_line = float(gsp) if same else -float(gsp)
            if abs(pin_line - float(line)) < 1e-6:
                a, b = shin2(gh_h, gh_a)
                fair = a if same else b
                gh.append((fair * od - 1, fair, tour))
        # ---------- SET WINNERS (best-of-3 only) ----------
        if mt == "TO_WIN_1ST_SET" and int(bo or 3) == 3 and ml1 and ml2 and so and su \
                and sph and spa and stl and abs(float(stl) - 2.5) < 1e-6:
            m1, m2 = shin2(ml1, ml2)
            s_un, s_ov = shin2(su, so)          # under 2.5 = STRAIGHTS
            a_h, a_a = shin2(sph, spa)          # spread -1.5 -> P(that player wins 2-0)
            same = surn(rn) == surn(cp1)
            M = m1 if same else m2
            a = a_h if same else a_a
            S = s_un
            fair = a + (1.0 - S) / 2.0
            if 0.02 < fair < 0.98:
                sw.append((fair * od - 1, fair, tour))


def report(name, v, hold_note):
    if len(v) < 15:
        print("\n   %-16s too few pairs (%d)" % (name, len(v)))
        return
    e = [x[0] for x in v]
    pos = [x for x in e if x > 0]
    print("\n" + "=" * 86)
    print("%s   (%s)" % (name, hold_note))
    print("=" * 86)
    print("   n=%d   mean EV %+.4f   median %+.4f   max %+.4f" % (len(e), st.mean(e), st.median(e), max(e)))
    print("   +EV quotes: %d (%.1f%%)   mean +EV %.4f"
          % (len(pos), 100.0 * len(pos) / len(e), st.mean(pos) if pos else 0.0))
    for lo, hi, lab in ((0.0, 0.3, "long  <.30"), (0.3, 0.5, "dog .30-.50"),
                        (0.5, 0.7, "fav .50-.70"), (0.7, 1.01, "heavy >.70")):
        s2 = [x[0] for x in v if lo <= x[1] < hi]
        if len(s2) >= 10:
            print("      %-12s n=%4d  mean EV %+.4f  max %+.4f" % (lab, len(s2), st.mean(s2), max(s2)))


report("TOTAL GAMES", tg, "FanDuel hold 6.5%")
report("GAME HANDICAP", gh, "FanDuel hold ~10%")
report("SET WINNERS (1st set, bo3)", sw, "FanDuel hold 4.7% - cheapest FD tennis market")
print()
print("   All references are SHIN-devigged Pinnacle. A mean EV near minus FanDuel's hold means")
print("   FanDuel is simply Pinnacle plus margin and there is nothing to take.")
