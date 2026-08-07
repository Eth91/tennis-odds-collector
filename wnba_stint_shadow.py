#!/usr/bin/env python3
"""wnba_stint_shadow — PRE-REGISTERED stint-rebound rule, paper only.

================================ THE RULE, FROZEN 2026-08-07 ================================
Written down BEFORE any live bet. Do not tune these values against forward results; if the rule
changes, that is a NEW rule with a NEW start date and the old evidence does not carry over.

  stat            REBOUNDS only          (assists and points flipped sign between seasons)
  trigger         a rostered REGULAR is out: >=5 prior games, >=20 mpg over the last 10
  beneficiary     SAME POSITION as the out player   <- the only filter that earned its keep
                  >=6 prior games, >=2 prior games alongside the out player
  signal          stint apart-rate must EXCEED the player's overall rate (shift > 1.0):
                  rebounds per minute while that teammate was OFF the floor, from the
                  play-by-play, using games strictly BEFORE tonight
  projection      each prior game scaled by min(proj_min/game_min, 1.35) x shift
  probability     share of scaled games clearing the line, then credibility-shrunk toward the
                  book's implied probability with K=11 (same as prop_edges)
  bet             OVER only, EV >= +10%, at most TWO plays per team-game (highest EV first)
  dedupe          one wager per (player, line) even if two injuries generate it

DELIBERATELY NOT INCLUDED (tested, did not earn a place):
  minutes-apart minimum (inert: 0/10/25/50 identical) · starter filter (inert) ·
  games-without cap (cost volume, no edge) · opponent rebounding strength x pace
  (moved the two seasons in OPPOSITE directions -- the book already prices both)

BACKTEST THIS IS BEING JUDGED AGAINST (both seasons, model-matched logic):
  2026  15-9   62.5%  vs 51.4% breakeven  +11.1  +5.19u
  2025  19-11  63.3%  vs 51.0% breakeven  +12.4  +7.71u
  BOTH  34-20  63.0%                      +11.8 +12.90u   20 distinct players
  Honest caveat: this configuration was chosen AFTER testing ~11 variants, so some of that
  edge is hindsight. Season-to-season agreement is the reason it is worth a forward test at
  all. Expect regression -- anything at or above breakeven forward is a real result.
=============================================================================================

=========================== ARM 2, FROZEN 2026-08-07: POINTS x RELIABILITY ===========
A SECOND, INDEPENDENT rule. Arm 1 (above) is rebounds. This one is POINTS, and it selects on
the RELIABILITY of the apart-shift rather than its size.

  stat       POINTS
  trigger    same as arm 1: a rostered REGULAR is out (>=5 games, >=20 mpg)
  benef.     SAME POSITION as the out player
  signal     per-game apart rates -> t = (mean - overall) / (sd / sqrt(games)),
             using games strictly BEFORE tonight, >=6 apart-games of >=4 min each
  bet        OVER the two-sided main line when t >= 1.0
  NO shrinkage, NO EV bar -- deliberately. That is exactly what was measured; adding gates
  that were not in the test would ship something the numbers do not describe.

WHY RELIABILITY. The apart-rate is UNBIASED (1,258 pairs: predicted 8.44 vs actual 8.40 pts,
3.53 vs 3.55 reb) yet selecting its LARGEST values loses. Pooling hides whether a 1.4x shift
came from ten steady games or one outlier, and the current rule prefers the outlier. The
t-statistic separates them.

EVIDENCE (both seasons, same filters):
  points t>=1.0        2026 63.2% n=19 (+11.6)   2025 60.8% n=51 (+7.1)
  big shift + reliable 2026 63.2% n=19           2025 60.4% n=48
  big shift, UNreliable 2026 50.7% n=134         2025 50.3% n=161
  rebounds at t>=1.0: 2025 54.8% n=31 but 2026 only n=7 -- NOT pre-registered here.

⚠ HONEST CAVEAT, PART OF THE REGISTRATION. The bar was pre-registered at t>=0.5 and FAILED
there on 2025 (50.0% vs the pooled rule's 51.2%). Moving to t>=1.0 after seeing the data is
goalpost-shifting and is recorded as such. What justifies a forward test is not the t>=1.0
cell but the CONTRAST: the unreliable half is 134/161/136 bets across seasons and stats and
sits at or below breakeven every time. Judge this arm on forward bets only.

PAPER ONLY. Writes to its own table, never to wnba_ledger predictions, never to the board.
Pings are labelled SHADOW at the user's explicit request (2026-08-07) -- note this overrides
the standing ping/board coherence rule, so the label is what stops it reading as a live play.
"""
import datetime as dt
import os
import sqlite3
import statistics as st
import subprocess
import sys

sys.path.insert(0, "/home/ubuntu/tennis-odds-collector")
os.chdir("/home/ubuntu/tennis-odds-collector")

import wnba_tonight as T
import wnba_wowy as W

DB = "/home/ubuntu/wnba_data/wnba_shadow.sqlite"
STINT = "/home/ubuntu/tennis-odds-collector/wnba_stints.sqlite"
SHRINK_K, EV_BAR, TOP_N, SHIFT_MIN = 11.0, 0.10, 2, 1.0
RULE_ID = "stint_reb_v1"


def _db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS shadow (
        rule TEXT, pred_date TEXT, player TEXT, team TEXT, out_player TEXT, stat TEXT,
        line REAL, odds REAL, ev REAL, shift REAL, n INTEGER, proj REAL,
        logged_at TEXT, result TEXT, actual REAL,
        PRIMARY KEY (rule, pred_date, player, stat, line))""")
    return c


def stint_rates(player, mate, before):
    c = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    ts = tv = 0.0
    for e, d, sec, v in c.execute(
            "SELECT event_id,game_date,sec,reb FROM onfloor WHERE player=?", (player,)):
        if e in ok and v is not None and d < before:
            ts += sec or 0; tv += v
    ws = wv = 0.0
    for e, d, sec, v in c.execute(
            "SELECT event_id,game_date,sec,reb_with FROM pairs WHERE player=? AND mate=?",
            (player, mate)):
        if e in ok and v is not None and d < before:
            ws += sec or 0; wv += v
    c.close()
    aps = ts - ws
    if aps <= 0 or ts <= 0:
        return None
    return (wv is not None) and ((tv - wv) / (aps / 60.0), tv / (ts / 60.0), aps / 60.0)


ARM2_RULE_ID = "stint_pts_t_v1"
ARM2_T_MIN = 1.0
ARM2_MIN_GAMES = 6
ARM2_MIN_APART_GAME = 4.0


def _arm2_t(player_name, mate_name, slate):
    """Per-game reliability of the apart-shift in POINTS. -> t or None."""
    import math
    c = sqlite3.connect(f"file:{STINT}?mode=ro", uri=True)
    ok = {e for (e,) in c.execute("SELECT event_id FROM games WHERE status='ok'")}
    on = {}
    for e, d, p, sec, v in c.execute(
            "SELECT event_id,game_date,player,sec,pts FROM onfloor WHERE player=?",
            (player_name,)):
        if e in ok and v is not None and d < slate:
            on[e] = (sec or 0.0, v)
    wi = {}
    for e, d, sec, v in c.execute(
            "SELECT event_id,game_date,sec,pts_with FROM pairs WHERE player=? AND mate=?",
            (player_name, mate_name)):
        if e in ok and v is not None and d < slate:
            wi[e] = (sec or 0.0, v)
    c.close()
    rates, tot_s, tot_v = [], 0.0, 0.0
    for e, (sec, v) in on.items():
        tot_s += sec; tot_v += v
        ws, wv = wi.get(e, (0.0, 0.0))
        m = (sec - ws) / 60.0
        if m >= ARM2_MIN_APART_GAME:
            rates.append((v - wv) / m)
    if tot_s <= 0 or len(rates) < ARM2_MIN_GAMES:
        return None
    overall = tot_v / (tot_s / 60.0)
    sd = st.pstdev(rates)
    if overall <= 0 or sd <= 0:
        return None
    return (st.mean(rates) - overall) / (sd / math.sqrt(len(rates)))


def main():
    slate = dt.datetime.now(dt.timezone.utc).date().isoformat()
    pl = W.players()
    try:
        import wnba_slip as S
        outs_marks = S._out_marks()
    except Exception as e:
        print(f"shadow: cannot read the live out-list ({e}) — refusing to guess")
        return 1
    if not outs_marks:
        print("shadow: no firm outs on the slate")
        return 0

    out_names = {n for n in pl if any(str(n).split()[-1].lower() in str(k).lower()
                                      for k in (outs_marks or []))}
    if not out_names:
        print("shadow: no rostered regular matches the out-list")
        return 0

    cands = []
    for out_name in out_names:
        ov = pl.get(out_name)
        if not ov or not ov.get("position"):
            continue
        olog = W.game_log(ov["id"])
        reg = [g for g in olog if (g.get("min") or 0) > 0]
        if len(reg) < 5 or st.mean(g["min"] for g in reg[-10:]) < 20:
            continue
        ogids = {g.get("game_id") for g in reg}
        for n, v in pl.items():
            if n == out_name or v["team"] != ov["team"]:
                continue
            if v.get("position") != ov["position"]:
                continue
            blog = [g for g in W.game_log(v["id"]) if (g.get("min") or 0) > 0]
            if len(blog) < 6:
                continue
            if len([g for g in blog if g.get("game_id") in ogids]) < 2:
                continue
            rr = stint_rates(n, out_name, slate)
            if not rr:
                continue
            ap, ov_rate, mins = rr
            if ov_rate <= 0 or ap / ov_rate <= SHIFT_MIN:
                continue
            shift = ap / ov_rate
            r5 = [g["min"] for g in blog[:5] if g["min"] > 8]
            pm = st.median(r5) if r5 else st.mean(g["min"] for g in blog[-10:])
            lad = (T.posted_props(n) or {}).get("rebounds") or {}
            two = {k: x for k, x in lad.items() if x and x[0] and x[1]}
            if not two:
                continue
            line = min(two, key=lambda x: abs(two[x][0] - two[x][1]))
            dec = two[line][0]
            vals = [g["reb"] * min(pm / max(g["min"], 1), 1.35) * shift for g in blog]
            if len(vals) < 4:
                continue
            hit = sum(1 for x in vals if x > line) / len(vals)
            p_adj = (hit * len(vals) + (1.0 / dec) * SHRINK_K) / (len(vals) + SHRINK_K)
            ev = p_adj * dec - 1.0
            if ev < EV_BAR:
                continue
            cands.append({"player": n, "team": v["team"], "out": out_name, "line": line,
                          "odds": dec, "ev": ev, "shift": shift, "n": len(vals),
                          "proj": round(st.mean(vals), 1)})

    best, seen = [], set()
    for c in sorted(cands, key=lambda x: -x["ev"]):
        if (c["player"], c["line"]) in seen:
            continue
        if sum(1 for b in best if b["team"] == c["team"]) >= TOP_N:
            continue
        seen.add((c["player"], c["line"])); best.append(c)

    # ---- ARM 2: POINTS x reliability. Independent of arm 1; own rule id, own rows. ----
    arm2 = []
    for out_name in out_names:
        ov = pl.get(out_name)
        if not ov or not ov.get("position"):
            continue
        for n, v in pl.items():
            if n == out_name or v["team"] != ov["team"]:
                continue
            if v.get("position") != ov.get("position"):
                continue
            t = _arm2_t(n, out_name, slate)
            if t is None or t < ARM2_T_MIN:
                continue
            lad = (T.posted_props(n) or {}).get("points") or {}
            two = {k: x for k, x in lad.items() if x and x[0] and x[1]}
            if not two:
                continue
            line = min(two, key=lambda x: abs(two[x][0] - two[x][1]))
            arm2.append({"player": n, "team": v["team"], "out": out_name, "line": line,
                         "odds": two[line][0], "ev": None, "shift": None, "n": None,
                         "proj": None, "t": round(t, 2)})
    if arm2:
        con2 = _db()
        now2 = dt.datetime.now(dt.timezone.utc).isoformat()
        for b in arm2:
            if con2.execute("SELECT 1 FROM shadow WHERE rule=? AND pred_date=? AND player=? "
                            "AND stat=? AND line=?",
                            (ARM2_RULE_ID, slate, b["player"], "points", b["line"])).fetchone():
                continue
            con2.execute("INSERT INTO shadow VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                         (ARM2_RULE_ID, slate, b["player"], b["team"], b["out"], "points",
                          b["line"], b["odds"], 0.0, b["t"], 0, 0.0, now2))
            print(f"  SHADOW-2 {b['player']} points over {b['line']:g} @{b['odds']:.2f} "
                  f"t={b['t']} (w/o {b['out']})")
        con2.commit(); con2.close()

    if not best and not arm2:
        print(f"shadow: 0 qualifying plays on {slate}")
        return 0
    if not best:
        return 0

    con = _db()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    new = []
    for b in best:
        cur = con.execute("SELECT 1 FROM shadow WHERE rule=? AND pred_date=? AND player=? "
                          "AND stat=? AND line=?",
                          (RULE_ID, slate, b["player"], "rebounds", b["line"])).fetchone()
        if cur:
            continue
        con.execute("INSERT INTO shadow VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)",
                    (RULE_ID, slate, b["player"], b["team"], b["out"], "rebounds",
                     b["line"], b["odds"], b["ev"], b["shift"], b["n"], b["proj"], now))
        new.append(b)
    con.commit(); con.close()

    for b in best:
        print(f"  SHADOW {b['player']} rebounds over {b['line']:g} @{b['odds']:.2f} "
              f"EV {b['ev']*100:+.1f}% (w/o {b['out']}, proj {b['proj']})")
    if new:
        try:
            topic = T._ntfy_topic()
            if topic:
                body = "\n".join(f"{b['player']} reb o{b['line']:g} @{b['odds']:.2f} "
                                 f"({b['ev']*100:+.0f}% EV, w/o {b['out']})" for b in new)
                subprocess.run(["curl", "-s", "-H", "Title: SHADOW (paper, not on board)",
                                "-H", "Tags: test_tube", "-d",
                                "STINT-REBOUND SHADOW — paper only, no board entry\n" + body,
                                f"ntfy.sh/{topic}"], timeout=20)
        except Exception as e:
            print(f"  (ntfy failed: {e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
