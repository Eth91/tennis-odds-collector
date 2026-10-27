#!/usr/bin/env python3
"""ROLE_OPEN live (NBA_ROLE1_PREREG.md, NBA_SXS_PREREG.md amendment 2): every minute, find props a book has just
opened (first seen with a two-sided main rung), run the same decision the side-by-side replays
(nba_role.role_eval), log it to nba_role.sqlite and ping the phone, labeled shadow, when it fires.
It reads nba_lines' `board` (the current pre-game board, replaced every poll, a few thousand rows), not the change log,
so a minute's work stays small all season.

    python3 nba_role_open.py --process      # cron, every minute (the first run only marks what is already open)
"""
from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
from pathlib import Path

import nba_proj_data as PD
import nba_proj_eval as E
import nba_replay as RP
import nba_research as R
import nba_ratio as RATIO
import nba_role as ROLE

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_role.sqlite"
TOO_LATE_MIN = 5
OUTS = ("Out", "Doubtful")
BOOK = {"fd": "FD", "dk": "DK"}
ABBR = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes": "3PM"}
DDL = ["CREATE TABLE IF NOT EXISTS opened (gid TEXT, pid INTEGER, market TEXT, book TEXT, opened_at TEXT, "
       "PRIMARY KEY (gid, pid, market, book))",
       "CREATE TABLE IF NOT EXISTS signals (gid TEXT, pid INTEGER, market TEXT, side TEXT, book TEXT, line REAL, price REAL, "
       "ev REAL, p REAL, mu REAL, out_pids TEXT, date TEXT, team TEXT, player TEXT, logged_at TEXT, pinged INTEGER, "
       "PRIMARY KEY (gid, pid, market, side))",
       "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
       "CREATE TABLE IF NOT EXISTS ratio_signals (rule TEXT, gid TEXT, pid INTEGER, market TEXT, book TEXT, line REAL, "
       "price REAL, volume REAL, date TEXT, player TEXT, logged_at TEXT, pinged INTEGER, PRIMARY KEY (rule, gid, pid, market))"]
PINGED_RATIOS = ("RATIO_PA28",)                          # NBA_RATIO_PREREG.md amendment 3: the ratio rules that ping


def current_boards(q):
    """{(gid, pid, market, book): (board, tip, player, collected_at)} from nba_lines' current board."""
    out = {}
    for book, at, gid, tip, pid, player, stat, line, side, odds in q.execute(
            "SELECT book, collected_at, gid, tip_utc, pid, player, stat, line, side, odds FROM board WHERE pid IS NOT NULL "
            "AND book IN ('fd', 'dk') AND stat IN ('points', 'rebounds', 'assists', 'threes') AND odds IS NOT NULL"):
        k = (gid, pid, stat, book)
        b, _t, _p, last = out.get(k, ({}, tip, player, at))
        b[(round(float(line), 1), side)] = odds
        out[k] = (b, tip, player, max(last, at))
    return out


def statuses(n, date, now):
    """{pid: (team, latest status, player)} from the official reports published by `now` for the date."""
    out = {}
    if n is None:
        return out
    for pub, team, pid, st, nm in n.execute("SELECT published_at, team, pid, status, player FROM snapshots WHERE game_date = ? "
                                            "AND pid IS NOT NULL ORDER BY published_at", (date,)):
        if RP.iso(pub) <= now:
            out[int(pid)] = (team, st, nm)
    return out


def body(e, team, player, market, line, book, xs):
    from nba_ping import american
    return (f"🟢 ROLE {team} {player} {ABBR[market]} {e['side'][0]}{line:g} {american(e['price'])} {BOOK[book]} "
            f"· EV {e['ev']:.0%} · {', '.join(xs)} out · shadow")


def ratio_body(rule, player, market, line, price, book, vol):
    from nba_ping import american
    return (f"🟣 PA28 {player} {ABBR[market]} o{line:g} {american(price)} {BOOK[book]} "
            f"· pot. ast {vol:.1f} ({vol / line:.1f}x) · shadow")


def process(now=None, lines_db=HERE / "nba_lines.sqlite", news_db=HERE / "nba_news.sqlite", matchup_db=HERE / "nba_matchup.sqlite",
            gamelogs_db=HERE / "nba_gamelogs.sqlite", tracking_db=HERE / "nba_tracking.sqlite", db=DB, sender=None):
    import nba_ping as PING
    sender = sender or PING.send
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    con = sqlite3.connect(db)
    for s_ in DDL:
        con.execute(s_)
    q, n = PD._ro(lines_db), PD._ro(news_db)
    first_run = con.execute("SELECT value FROM meta WHERE key = 'installed'").fetchone() is None
    keys = current_boards(q)
    done = {(g, p, m, b) for g, p, m, b in con.execute("SELECT gid, pid, market, book FROM opened")}
    rds, rts, stat_cache, fired = {}, {}, {}, 0
    for (gid, pid, market, book), (board, tip, player, seen) in sorted(keys.items()):
        if (gid, pid, market, book) in done or seen > now:
            continue
        m = R.main_of(board)
        if not m:
            continue
        con.execute("INSERT OR IGNORE INTO opened VALUES (?, ?, ?, ?, ?)", (gid, pid, market, book, seen))
        if first_run or not tip or RP.iso(tip) <= (dt.datetime.fromisoformat(now) + dt.timedelta(minutes=TOO_LATE_MIN)).isoformat():
            continue                                     # install: mark what is already open; never act near or after tip
        date = E._et_date(tip)
        season = ROLE.season_of(date)
        for rule in PINGED_RATIOS:                       # the same decision the side-by-side's RATIO_PA28 replays
            if RATIO.FORWARD[rule][0] != market:
                continue
            rt = rts.get(season) or rts.setdefault(season, RATIO.RatioData(matchup_db, tracking_db, season))
            if RATIO.ratio_eval(rt, RATIO.FORWARD[rule], pid, date, market, m[0]):
                vol = rt.volume(pid, date)[RATIO.FORWARD[rule][1]]
                cur = con.execute("INSERT OR IGNORE INTO ratio_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (rule, gid, pid, market, book, m[0], m[1], round(vol, 2), date, player, now, 0))
                if cur.rowcount:
                    ok = sender(ratio_body(rule, player, market, m[0], m[1], book, vol))
                    con.execute("UPDATE ratio_signals SET pinged = ? WHERE rule = ? AND gid = ? AND pid = ? AND market = ?",
                                (1 if ok else 0, rule, gid, pid, market))
                    fired += 1
        rd = rds.get(season) or rds.setdefault(season, ROLE.RoleData(matchup_db, gamelogs_db, season))
        team = rd.team_of(pid, date)
        if team is None:
            continue
        st = stat_cache.get(date) or stat_cache.setdefault(date, statuses(n, date, now))
        out_now = {x for x, (tm, s_, _nm) in st.items() if tm == team and s_ in OUTS}
        if not out_now:
            continue
        for e in ROLE.role_eval(rd, date, team, pid, market, m[0], m[1], m[2], out_now):
            xs = [st[x][2] or str(x) for x in sorted(e["spots"])]
            cur = con.execute("INSERT OR IGNORE INTO signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                              (gid, pid, market, e["side"], book, m[0], e["price"], round(e["ev"], 4), round(e["p"], 4),
                               round(e["mu"], 2), ",".join(map(str, sorted(e["spots"]))), date, team, player, now, 0))
            if cur.rowcount:
                ok = sender(body(e, team, player, market, m[0], book, xs))
                con.execute("UPDATE signals SET pinged = ? WHERE gid = ? AND pid = ? AND market = ? AND side = ?",
                            (1 if ok else 0, gid, pid, market, e["side"]))
                fired += 1
    if first_run:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('installed', ?)", (now,))
    con.commit()
    print(f"nba_role_open {now}: {len(keys)} props on the board, {fired} fired{' (install: marked open, no pings)' if first_run else ''}")
    return fired


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", action="store_true")
    a = ap.parse_args()
    if a.process:
        process()


if __name__ == "__main__":
    main()
