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

    if not best:
        print(f"shadow: 0 qualifying plays on {slate}")
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
