#!/usr/bin/env python3
"""TN-028 — confirm the rest/load leak, then re-measure with rounds in CHRONOLOGICAL order.

TML stamps one `tourney_date` on every match of an event, so "ORDER BY date" leaves matches WITHIN
a tournament in arbitrary order - a final can be processed before its own first round. Any feature
built from a running history then sees LATER ROUNDS of the same event, and a player only reaches a
later round by WINNING. That is direct look-ahead, and it explains both signs precisely:

    load_14   positive  - "recent matches" include rounds the player had to win to reach
    rest_days negative  - rest 0 means a same-event match was already processed, i.e. they advanced

FIX: sort by (date, round order) so a tournament is replayed in the sequence it was actually
played. If the effect is a leak it collapses; if it survives it was real.
"""
import math
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from datetime import date as DT
from pathlib import Path

import numpy as np

DB = Path(__file__).resolve().parent / "tennis_ace.sqlite"
EPS = 1e-9
RND = {"R128": 1, "R64": 2, "R32": 3, "R16": 4, "QF": 5, "SF": 6, "F": 7, "RR": 3, "BR": 6}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def ktml(n):
    p = [x for x in norm(n).split() if x]
    return "%s|%s" % (" ".join(p[1:]), p[0][:1]) if len(p) >= 2 else None


con = sqlite3.connect("file:%s?mode=ro" % DB, uri=True, timeout=60)
M = con.execute("""SELECT date, year, surface, player, opp, round, tourney FROM ace_pm
                   WHERE won=1 AND surface IS NOT NULL AND surface!=''""").fetchall()
oh = defaultdict(list)
for d, wk, lk, wo, lo in con.execute("SELECT date, wkey, lkey, w_odds, l_odds FROM odds_hist"):
    oh[(wk, lk)].append((d, wo, lo))
con.close()


def shin2(o1, o2):
    q = [1.0 / o1, 1.0 / o2]
    R = sum(q)
    lo, hi = 0.0, 0.99
    for _ in range(120):
        z = 0.5 * (lo + hi)
        s = sum((math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q)
        if s > 1.0:
            lo = z
        else:
            hi = z
    z = 0.5 * (lo + hi)
    p = [(math.sqrt(z * z + 4 * (1 - z) * x * x / R) - z) / (2 * (1 - z)) for x in q]
    return p[0] / sum(p)


def price(d, w, l):
    kw, kl = ktml(w), ktml(l)
    if not kw or not kl:
        return None
    for dd, wo, lo in oh.get((kw, kl), []):
        try:
            if abs((DT.fromisoformat(dd) - DT.fromisoformat(d)).days) <= 4:
                return shin2(wo, lo)
        except Exception:                                               # noqa: BLE001
            continue
    return None


def build(order_by_round):
    data = sorted(M, key=(lambda r: (r[0], RND.get(str(r[5]), 3)))
                  if order_by_round else (lambda r: r[0]))
    lastdate, recent = {}, defaultdict(list)
    rows = []
    for d, yr, surf, w, l, rnd, tny in data:
        p = price(d, w, l)
        if p is not None and 0.01 < p < 0.99:
            a, b = (w, l) if norm(w) < norm(l) else (l, w)
            y = 1.0 if a == w else 0.0
            p1 = p if a == w else 1 - p

            def rest(pl):
                return min((DT.fromisoformat(d) - DT.fromisoformat(lastdate[pl])).days, 30) \
                    if pl in lastdate else None

            def load(pl):
                return sum(1 for x in recent[pl]
                           if (DT.fromisoformat(d) - DT.fromisoformat(x)).days <= 14)
            ra, rb = rest(a), rest(b)
            rows.append((yr, p1, y,
                         (ra - rb) if (ra is not None and rb is not None) else None,
                         load(a) - load(b)))
        lastdate[w] = d
        lastdate[l] = d
        recent[w].append(d)
        recent[l].append(d)
    return rows


def test(rows, idx, name):
    tr = [(math.log(p / (1 - p)), r[idx], y) for _yr, p, y, *rest_ in
          [(r[0], r[1], r[2], r[3], r[4]) for r in rows if r[0] <= 2023 and r[idx] is not None]
          for r in [(_yr, p, y) + tuple(rest_)]][:0]  # placeholder, replaced below
    tr = [(math.log(r[1] / (1 - r[1])), r[idx], r[2]) for r in rows
          if r[0] <= 2023 and r[idx] is not None]
    te = [(math.log(r[1] / (1 - r[1])), r[idx], r[2]) for r in rows
          if r[0] >= 2024 and r[idx] is not None]
    if len(tr) < 500 or len(te) < 200:
        print("   %-28s too few" % name)
        return
    X = np.array([[1.0, x, z] for x, z, _ in tr])
    Y = np.array([y for _, _, y in tr])
    b = np.array([0.0, 1.0, 0.0])
    for _ in range(40):
        q = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        H = (X * (q * (1 - q) + 1e-9)[:, None]).T @ X
        try:
            step = np.linalg.solve(H, X.T @ (q - Y))
        except np.linalg.LinAlgError:
            break
        b = b - step
        if np.max(np.abs(step)) < 1e-9:
            break
    se = math.sqrt(max(np.linalg.pinv(H)[2][2], 0))
    XT = np.array([[1.0, x, z] for x, z, _ in te])
    YT = np.array([y for _, _, y in te])

    def nll(p):
        p = np.clip(p, EPS, 1 - EPS)
        return float(-(YT * np.log(p) + (1 - YT) * np.log(1 - p)).mean())
    d_ll = nll(1 / (1 + np.exp(-np.clip(XT @ b, -30, 30)))) - nll(1 / (1 + np.exp(-XT[:, 1])))
    print("   %-28s coef %+8.4f  t %+8.2f  OOS delta LL %+.5f%s"
          % (name, b[2], b[2] / se if se else 0, d_ll, "  <- helps" if d_ll < -1e-5 else ""))


for flag, lbl in ((False, "date only  (what I did - arbitrary order INSIDE a tournament)"),
                  (True, "date + ROUND  (chronological)")):
    rows = build(flag)
    rd = [r[3] for r in rows if r[3] is not None]
    ld = [r[4] for r in rows]
    print("\n%s" % lbl)
    print("   rows %d | mean rest_days %+.3f | mean load_14 %+.3f"
          % (len(rows), st.mean(rd), st.mean(ld)))
    test(rows, 3, "rest_days")
    test(rows, 4, "load_14")
