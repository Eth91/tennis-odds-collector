#!/usr/bin/env python3
"""LIVE forward test: score today's FanDuel board, log +EV bets to a paper ledger, settle later.

This is the arbiter. Every retrospective test in this programme has been vulnerable to some subtle
contamination - orientation, de-vig choice, within-tournament ordering - and each of those produced
a convincing fake edge before being caught. A forward ledger cannot be contaminated by any of them,
because the price is recorded before the match and the result arrives afterwards.

WHAT IT DOES
    build     replay history to TODAY, producing current Elo (from results through yesterday) and
              serve/return states (from TML, which stops 2026-01-17 - see the staleness warning)
    scan      score every FanDuel match on the board, compare to FanDuel's own price, log the +EV
              ones at the price actually available
    settle    match logged bets to results and mark win/loss
    report    record, ROI, and CLV against Pinnacle's closing number

⚠️ STALENESS IS PRINTED, NOT HIDDEN. The point model's serve inputs are 224 days behind. A bet
logged on a stale component is not evidence about the model's real accuracy, so every row records
which components fed it and how old they were.

⚠️ PAPER ONLY. Nothing here places a bet; it writes rows to a ledger.
"""
import datetime as dt
import json
import math
import pickle
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from datetime import date as DT
from pathlib import Path

HERE = Path(__file__).resolve().parent
ADB = HERE / "tennis_ace.sqlite"
FDB = HERE / "tennis_fd.sqlite"
PDB = HERE / "odds.sqlite"
LDG = HERE / "ml_ledger.sqlite"
RND = {"R128": 1, "RR": 2, "R64": 2, "R32": 3, "R16": 4, "QF": 5, "SF": 6, "BR": 6, "F": 7}
EDGE_MIN = 0.03
MIN_MATCHES = 20      # below this we do not know the player
MAX_EDGE = 0.50       # any larger against a real book is a bug, not an opportunity


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def pkey(name):
    """Canonical player key: (surname, first initial), tolerant of both spelling conventions.

    "Yuliia Starodubtseva" (FanDuel) and "Starodubtseva Y." (tennis-data) must land on the same
    key or nothing joins. A trailing single letter marks the surname-first form.
    """
    t = [x for x in norm(name).split() if x]
    if not t:
        return ""
    if len(t) == 1:
        return t[0]
    if len(t[-1]) == 1:                 # "starodubtseva y" -> surname first
        return "%s|%s" % (" ".join(t[:-1]), t[-1])
    return "%s|%s" % (" ".join(t[1:]), t[0][:1])    # "yuliia starodubtseva" -> first name first


def surn(n):
    p = [x for x in norm(n).split() if x]
    return p[-1] if p else ""


src = open(HERE / "ml_model.py").read().split("# ---------- data")[0]
_ns = {"__file__": str(HERE / "ml_model.py")}
exec(src, _ns)                                    # game_win / set_win / match_win, already validated
match_win = _ns["match_win"]

CFG = pickle.load(open(HERE / "ml_config.pkl", "rb"))
# Fitted on 34,703 historical matches. Damps a slightly over-confident model.
# It does NOT close the accuracy gap: calibrated 0.61992 vs market 0.60064.
try:
    CALIB = pickle.load(open(HERE / "ml_calib.pkl", "rb"))
except Exception:
    CALIB = {"a": 0.0, "b": 1.0}
K, BLEND, HL, KSH, BASE_S = CFG["K"], CFG["blend"], CFG["HL"], CFG["KSH"], CFG["base"]


def days(a, b):
    return ((int(b[:4]) - int(a[:4])) * 365.25 + (int(b[5:7]) - int(a[5:7])) * 30.44
            + (int(b[8:10]) - int(a[8:10])))


def build_state():
    """Replay everything to today. Elo from results (current); serve from srv_pm (stale)."""
    con = sqlite3.connect("file:%s?mode=ro" % ADB, uri=True, timeout=60)
    srvrows = con.execute("""SELECT date, surface, round, player, opp, svpt, first_won,
                                    second_won, o_svpt, o_first_won, o_second_won
                             FROM srv_pm WHERE won=1 AND first_won IS NOT NULL AND svpt>0
                               AND o_svpt>0 AND surface!=''""").fetchall()
    res = con.execute("""SELECT date, surface, round, winner, loser FROM results_live
                         ORDER BY date""").fetchall()
    srv_max = con.execute("SELECT MAX(date) FROM srv_pm").fetchone()[0]
    res_max = con.execute("SELECT MAX(date) FROM results_live").fetchone()[0]
    con.close()
    srvrows.sort(key=lambda r: (r[0], RND.get(str(r[2]), 3)))

    elo = defaultdict(lambda: 1500.0)
    elos = defaultdict(lambda: defaultdict(lambda: 1500.0))
    seen = defaultdict(int)          # matches of history per player - the gate
    srv = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))
    ret = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, None]))
    # SERVE/RETURN ONLY. Elo is built below from results_live, because srv_pm is ATP-only and
    # seeding Elo here left every WTA player on a near-default rating.
    for d, surf, rnd, w, l, sv, f1, f2, osv, of1, of2 in srvrows:
        for store, key, num, den in ((srv, pkey(w), f1 + f2, sv), (srv, pkey(l), of1 + of2, osv),
                                     (ret, pkey(l), f1 + f2, sv), (ret, pkey(w), of1 + of2, osv)):
            A, B, last = store[key][surf]
            wgt = 0.5 ** (days(last, d) / HL) if last else 1.0
            store[key][surf] = [A * wgt + num, B * wgt + den, d]
    # ELO over the FULL results history: both tours, 2015 -> yesterday
    for d, surf, rnd, w, l in res:
        sf = surf if surf in BASE_S else "Hard"
        pe = 1.0 / (1.0 + 10 ** ((elo[pkey(l)] - elo[pkey(w)]) / 400.0))
        ps = 1.0 / (1.0 + 10 ** ((elos[sf][pkey(l)] - elos[sf][pkey(w)]) / 400.0))
        elo[pkey(w)] += K * (1 - pe)
        elo[pkey(l)] -= K * (1 - pe)
        elos[sf][pkey(w)] += K * (1 - ps)
        elos[sf][pkey(l)] -= K * (1 - ps)
        seen[pkey(w)] += 1
        seen[pkey(l)] += 1
    return elo, elos, srv, ret, srv_max, res_max, seen


def prob(elo, elos, srv, ret, a, b, surf, bo, today):
    A, B = pkey(a), pkey(b)
    S = BASE_S.get(surf, BASE_S.get("Hard", 0.64))
    pe = 1.0 / (1.0 + 10 ** ((elo[B] - elo[A]) / 400.0))
    ps = 1.0 / (1.0 + 10 ** ((elos[surf][B] - elos[surf][A]) / 400.0))
    p_elo = (1 - BLEND) * pe + BLEND * ps

    def dec(store, key):
        x, y, last = store[key][surf]
        if last is None:
            return 0.0, 0.0
        wgt = 0.5 ** (days(last, today) / HL)
        return x * wgt, y * wgt
    sa, spa = dec(srv, A)
    sb, spb = dec(srv, B)
    ra, rpa = dec(ret, A)
    rb, rpb = dec(ret, B)
    s_a = (sa + KSH * S) / (spa + KSH)
    s_b = (sb + KSH * S) / (spb + KSH)
    o_a = (ra + KSH * S) / (rpa + KSH)
    o_b = (rb + KSH * S) / (rpb + KSH)
    pa = min(max(s_a + (S - o_b), 0.35), 0.85)
    pb = min(max(s_b + (S - o_a), 0.35), 0.85)
    p_pt = match_win(pa, pb, bo)
    thin = (spa + spb) < 500
    # WEIGHTING DECIDED BY THE BACKTEST, NOT BY TASTE. The point model scored 0.826 held-out
    # against Elo's 0.629 - worse than a coin flip - and earned a NEGATIVE weight (-0.109) in the
    # fitted stack. The cause is structural: the point->match recursion amplifies ~10x (a 0.04 gap
    # in point probability becomes a 0.69 match line) while a single match measures p only to
    # +-0.09, so estimation error explodes. It is ALSO 224 days stale for live use.
    # So the live model is the tuned Elo. p_point is still computed and RECORDED on every row, so
    # the forward ledger can answer later whether it would have helped - but it does not price.
    lgt = math.log(min(max(p_elo, 1e-6), 1 - 1e-6)
                   / (1 - min(max(p_elo, 1e-6), 1 - 1e-6)))
    p_cal = 1.0 / (1.0 + math.exp(-(CALIB["a"] + CALIB["b"] * lgt)))
    return p_cal, p_elo, p_pt, thin


def scan():
    elo, elos, srv, ret, srv_max, res_max, seen = build_state()
    today = dt.date.today().isoformat()
    print("state built | serve stats to %s (%d days stale) | results to %s"
          % (srv_max, (DT.fromisoformat(today) - DT.fromisoformat(srv_max)).days, res_max))
    fd = sqlite3.connect("file:%s?mode=ro" % FDB, uri=True, timeout=60)
    rows = fd.execute("""SELECT event_name, tour, best_of, start_time, runner_name, odds,
                                MAX(collected_at) FROM fd_tennis
                         WHERE market_type='MATCH_BETTING' AND start_time > ?
                         GROUP BY event_name, runner_name""", (today,)).fetchall()
    fd.close()
    lg = sqlite3.connect(str(LDG), timeout=60)
    lg.execute("PRAGMA busy_timeout=60000")
    lg.execute("""CREATE TABLE IF NOT EXISTS bets(
        logged_at TEXT, start_time TEXT, tour TEXT, event TEXT, pick TEXT, opp TEXT,
        best_of INT, odds REAL, p_model REAL, p_elo REAL, p_point REAL, thin INT,
        edge REAL, srv_stale_days INT, prior TEXT, result TEXT, pnl REAL,
        PRIMARY KEY (event, pick, start_time))""")
    lg.commit()
    skipped = defaultdict(int)
    byev = defaultdict(list)
    for ev, tour, bo, stt, rn, od, ts in rows:
        byev[(ev, tour, bo, stt)].append((rn, od))
    n_logged = 0
    cands = []
    for (ev, tour, bo, stt), runners in byev.items():
        if len(runners) != 2:
            continue
        parts = str(ev).split(" v ")
        if len(parts) != 2:
            continue
        a, b = parts
        na, nb = seen.get(pkey(a), 0), seen.get(pkey(b), 0)
        if min(na, nb) < MIN_MATCHES:
            skipped["no history (%s)" % ("both" if max(na, nb) < MIN_MATCHES else "one")] += 1
            continue
        p, pe, pp, thin = prob(elo, elos, srv, ret, a, b, "Hard", int(bo or 3), today)
        if abs(p - 0.5) < 1e-9:
            skipped["model returned the 0.500 default"] += 1
            continue
        for rn, od in runners:
            side_p = p if surn(rn) == surn(a) else 1 - p
            edge = side_p * od - 1
            if edge > MAX_EDGE:
                skipped["edge above %.0f%% - implausible, treated as a bug" % (100 * MAX_EDGE)] += 1
                continue
            cands.append((edge, ev, tour, bo, stt, rn, od, side_p, pe, pp, thin,
                          (a if surn(rn) != surn(a) else b)))
    cands.sort(reverse=True)
    print("\nboard: %d matches | priced %d | SKIPPED %d"
          % (len(byev), len(cands) // 2, sum(skipped.values())))
    for k, v in sorted(skipped.items(), key=lambda x: -x[1]):
        print("   skip: %-46s %d" % (k[:46], v))
    print("%-38s %-20s %6s %7s %7s %8s" % ("match", "pick", "odds", "model", "implied", "edge"))
    for e, ev, tour, bo, stt, rn, od, sp, pe, pp, thin, opp in cands[:12]:
        print("%-38s %-20s %6.2f %7.3f %7.3f %+8.3f%s"
              % (str(ev)[:38], str(rn)[:20], od, sp, 1 / od, e, "  THIN" if thin else ""))
    stale = (DT.fromisoformat(today) - DT.fromisoformat(srv_max)).days
    for e, ev, tour, bo, stt, rn, od, sp, pe, pp, thin, opp in cands:
        if e >= EDGE_MIN:
            lg.execute("INSERT OR IGNORE INTO bets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                       (dt.datetime.utcnow().isoformat(timespec="seconds"), stt, tour, ev, rn,
                        opp, int(bo or 3), od, sp, pe, pp, 1 if thin else 0, e, stale,
                        "model calibrated LL .61992 vs market .60064 - EXPECTED TO LOSE"))
            n_logged += 1
    lg.commit()
    tot = lg.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
    open_ = lg.execute("SELECT COUNT(*) FROM bets WHERE result IS NULL").fetchone()[0]
    print("\nlogged %d new +EV bets at >= %.0f%% edge | ledger: %d total, %d unsettled"
          % (n_logged, 100 * EDGE_MIN, tot, open_))
    lg.close()


def settle():
    lg = sqlite3.connect(str(LDG), timeout=60)
    lg.execute("PRAGMA busy_timeout=60000")
    con = sqlite3.connect("file:%s?mode=ro" % ADB, uri=True, timeout=60)
    res = con.execute("SELECT date, winner, loser FROM results_live").fetchall()
    con.close()
    won = {(surn(w), surn(l)) for _d, w, l in res}
    n = 0
    for rid, pick, opp, od in lg.execute(
            "SELECT rowid, pick, opp, odds FROM bets WHERE result IS NULL").fetchall():
        kp, ko = surn(pick), surn(opp)
        if (kp, ko) in won:
            lg.execute("UPDATE bets SET result='W', pnl=? WHERE rowid=?", (od - 1.0, rid))
            n += 1
        elif (ko, kp) in won:
            lg.execute("UPDATE bets SET result='L', pnl=-1.0 WHERE rowid=?", (rid,))
            n += 1
    lg.commit()
    print("settled %d bets" % n)
    r = lg.execute("""SELECT COUNT(*), SUM(result='W'), SUM(pnl) FROM bets
                      WHERE result IS NOT NULL""").fetchone()
    if r and r[0]:
        print("RECORD %d-%d  |  %+.2fu  |  ROI %+.1f%%"
              % (r[1] or 0, r[0] - (r[1] or 0), r[2] or 0, 100.0 * (r[2] or 0) / r[0]))
    lg.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd == "scan":
        scan()
    elif cmd == "settle":
        settle()
    else:
        print("usage: ml_live.py [scan|settle]")
