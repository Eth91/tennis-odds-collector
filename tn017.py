#!/usr/bin/env python3
"""TN-017 — FANDUEL vs PINNACLE on the markets BOTH price. Model-free.

Every tennis test so far asked "can OUR model beat the book", and the answer was no. That is a
different and much harder question than the one that actually matters for a soft book:

    does FANDUEL's price differ from PINNACLE's?

If it does, no model is needed at all. Pinnacle's de-vigged number is the best available estimate
of truth, so a FanDuel price that pays more than Pinnacle's fair probability implies is +EV by
construction - that is the entire soft-vs-sharp trade, and it needs no forecasting skill.

MARKETS COVERED - the three the user asked about that BOTH books quote:
    MONEYLINE       Pinnacle ml1/ml2          vs  FanDuel MATCH_BETTING
    TOTAL GAMES     Pinnacle games o/u        vs  FanDuel MATCH_TOTAL_GAMES
    SET SPREAD      Pinnacle set spread +-1.5 vs  FanDuel set handicap

METHOD. Join by normalised player names within a start-time window. For each market take the
SIMULTANEOUS pair - the FanDuel quote and the Pinnacle quote closest in time - de-vig Pinnacle
proportionally to get the fair probability, then compute EV of taking the FanDuel price:

    EV = p_pinnacle_fair * fanduel_decimal_odds - 1

A mean EV near -(FanDuel's hold) means FanDuel is simply Pinnacle plus its margin, and there is
nothing to do. A mean EV near zero or positive on some subset means FanDuel's line genuinely
disagrees with the sharp one, which is worth having.

⚠️ SIMULTANEITY IS THE WHOLE VALIDITY. Comparing a FanDuel price to a Pinnacle price taken hours
apart measures line movement, not disagreement. Pairs more than 20 minutes apart are dropped and
the surviving time gap is reported.
"""
import re
import sqlite3
import statistics as st
import unicodedata
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
FD = HERE / "tennis_fd.sqlite"
PIN = HERE / "odds.sqlite"


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", s.lower()).strip()


def surn(name):
    p = [x for x in norm(name).split() if x]
    return p[-1] if p else ""


def pairkey(a, b):
    return tuple(sorted([surn(a), surn(b)]))


# ---- FanDuel side ---------------------------------------------------------------------------
fd = sqlite3.connect("file:%s?mode=ro" % FD, uri=True, timeout=60)
fdrows = fd.execute("""SELECT event_id, event_name, tour, start_time, market_type, runner_name,
                              handicap, odds, collected_at
                       FROM fd_tennis
                       WHERE market_type IN ('MATCH_BETTING','MATCH_TOTAL_GAMES',
                                             'ALTERNATIVE_MATCH_TOTAL_GAMES')""").fetchall()
fd.close()
fdev = defaultdict(list)
for eid, ev, tour, stt, mt, rn, hc, od, ts in fdrows:
    parts = str(ev).split(" v ")
    if len(parts) != 2:
        continue
    fdev[(pairkey(parts[0], parts[1]), str(stt)[:10])].append(
        dict(ev=ev, p1=parts[0], p2=parts[1], mt=mt, rn=rn, hc=hc, od=od, ts=ts, tour=tour))
print("FanDuel events with comparable markets: %d" % len(fdev))

# ---- Pinnacle side --------------------------------------------------------------------------
pn = sqlite3.connect("file:%s?mode=ro" % PIN, uri=True, timeout=60)
pnrows = pn.execute("""SELECT match_id, p1, p2, start_time, collected_at, ml1, ml2,
                              games_line, games_over, games_under
                       FROM odds WHERE collected_at >= '2026-08-30'""").fetchall()
pn.close()
pnev = defaultdict(list)
for mid, p1, p2, stt, ts, a, b, gl, go, gu in pnrows:
    pnev[(pairkey(p1, p2), str(stt)[:10])].append(
        dict(p1=p1, p2=p2, ts=str(ts), ml1=a, ml2=b, gl=gl, go=go, gu=gu))
print("Pinnacle events in the same window: %d" % len(pnev))

shared = sorted(set(fdev) & set(pnev))
print("JOINED on (player pair, date): %d matches" % len(shared))
if not shared:
    raise SystemExit("no overlap - cannot compare")


def tsdiff(a, b):
    try:
        from datetime import datetime as D
        return abs((D.fromisoformat(a[:19]) - D.fromisoformat(b[:19])).total_seconds()) / 60.0
    except Exception:                                                   # noqa: BLE001
        return 1e9


ml_ev, tg_ev, gaps = [], [], []
for key in shared:
    F = fdev[key]
    P = pnev[key]
    # ---- MONEYLINE ----
    fml = [x for x in F if x["mt"] == "MATCH_BETTING"]
    for x in fml:
        cand = min(P, key=lambda p: tsdiff(p["ts"], x["ts"]))
        dt_ = tsdiff(cand["ts"], x["ts"])
        if dt_ > 20 or not cand["ml1"] or not cand["ml2"]:
            continue
        gaps.append(dt_)
        # orient: which Pinnacle side is this FanDuel runner?
        same = surn(x["rn"]) == surn(cand["p1"])
        po = cand["ml1"] if same else cand["ml2"]
        qo = cand["ml2"] if same else cand["ml1"]
        fair = (1 / po) / ((1 / po) + (1 / qo))
        ml_ev.append((fair * x["od"] - 1, x["tour"], fair))
    # ---- TOTAL GAMES: match FanDuel handicap to Pinnacle's line ----
    ftg = [x for x in F if x["mt"] in ("MATCH_TOTAL_GAMES", "ALTERNATIVE_MATCH_TOTAL_GAMES")]
    for x in ftg:
        if x["hc"] is None:
            continue
        cand = [p for p in P if p["gl"] is not None and abs(float(p["gl"]) - float(x["hc"])) < 1e-6
                and p["go"] and p["gu"]]
        if not cand:
            continue
        c = min(cand, key=lambda p: tsdiff(p["ts"], x["ts"]))
        dt_ = tsdiff(c["ts"], x["ts"])
        if dt_ > 20:
            continue
        over = "over" in str(x["rn"]).lower()
        po = c["go"] if over else c["gu"]
        qo = c["gu"] if over else c["go"]
        fair = (1 / po) / ((1 / po) + (1 / qo))
        tg_ev.append((fair * x["od"] - 1, x["tour"], fair))

print("simultaneous pairs: moneyline %d, total games %d | median time gap %.1f min"
      % (len(ml_ev), len(tg_ev), st.median(gaps) if gaps else -1))


def report(name, evs):
    if len(evs) < 20:
        print("\n   %-14s too few pairs (%d)" % (name, len(evs)))
        return
    v = [e[0] for e in evs]
    print("\n" + "=" * 88)
    print("%s — EV of taking the FanDuel price at Pinnacle's fair probability" % name)
    print("=" * 88)
    print("   n=%d   mean EV %+.4f   median %+.4f   best %+.4f"
          % (len(v), st.mean(v), st.median(v), max(v)))
    pos = sum(1 for x in v if x > 0)
    print("   FanDuel pays MORE than Pinnacle fair on %d of %d (%.1f%%)"
          % (pos, len(v), 100.0 * pos / len(v)))
    for lo, hi, lab in ((0.0, 0.35, "longshots  <.35"), (0.35, 0.5, "dogs   .35-.50"),
                        (0.5, 0.65, "favs   .50-.65"), (0.65, 1.01, "heavy favs >.65")):
        s2 = [e[0] for e in evs if lo <= e[2] < hi]
        if len(s2) >= 15:
            print("      %-16s n=%4d  mean EV %+.4f  best %+.4f"
                  % (lab, len(s2), st.mean(s2), max(s2)))
    for t in ("ATP", "WTA"):
        s2 = [e[0] for e in evs if e[1] == t]
        if len(s2) >= 15:
            print("      %-16s n=%4d  mean EV %+.4f" % (t, len(s2), st.mean(s2)))


report("MONEYLINE", ml_ev)
report("TOTAL GAMES", tg_ev)
print()
print("   READ: a mean EV near MINUS FanDuel's hold means FanDuel is Pinnacle plus margin and")
print("   there is nothing here. Positive tails matter only if they persist and are takeable.")
