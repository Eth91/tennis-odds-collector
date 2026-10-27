#!/usr/bin/env python3
"""ROLE_OPEN live (NBA_ROLE1_PREREG.md, NBA_SXS_PREREG.md amendment 2): every minute, find props a book has just
opened (first seen with a two-sided main rung), run the same decision the side-by-side replays
(nba_role.role_eval), log it to nba_role.sqlite and ping the phone, labeled shadow, when it fires.

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
import nba_role as ROLE

HERE = Path(__file__).resolve().parent
DB = HERE / "nba_role.sqlite"
LOOKBACK_MIN, TOO_LATE_MIN = 15, 5
OUTS = ("Out", "Doubtful")
BOOK = {"fd": "FD", "dk": "DK"}
ABBR = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes": "3PM"}
DDL = ["CREATE TABLE IF NOT EXISTS opened (gid TEXT, pid INTEGER, market TEXT, book TEXT, opened_at TEXT, "
       "PRIMARY KEY (gid, pid, market, book))",
       "CREATE TABLE IF NOT EXISTS signals (gid TEXT, pid INTEGER, market TEXT, side TEXT, book TEXT, line REAL, price REAL, "
       "ev REAL, p REAL, mu REAL, out_pids TEXT, date TEXT, team TEXT, player TEXT, logged_at TEXT, pinged INTEGER, "
       "PRIMARY KEY (gid, pid, market, side))",
       "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"]


def board_of(q, gid, pid, market, book, until):
    b = {}
    for line, side, odds in q.execute("SELECT line, side, odds FROM quotes WHERE gid = ? AND pid = ? AND stat = ? AND book = ? "
                                      "AND seen_at <= ? ORDER BY seen_at", (gid, pid, market, book, until)):
        k = (round(float(line), 1), side)
        if odds is None:
            b.pop(k, None)
        else:
            b[k] = odds
    return b


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


def process(now=None, lines_db=HERE / "nba_lines.sqlite", news_db=HERE / "nba_news.sqlite", matchup_db=HERE / "nba_matchup.sqlite",
            gamelogs_db=HERE / "nba_gamelogs.sqlite", db=DB, sender=None):
    import nba_ping as PING
    sender = sender or PING.send
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    con = sqlite3.connect(db)
    for s_ in DDL:
        con.execute(s_)
    q, n = PD._ro(lines_db), PD._ro(news_db)
    first_run = con.execute("SELECT value FROM meta WHERE key = 'installed'").fetchone() is None
    since = "0000" if first_run else (dt.datetime.fromisoformat(now) - dt.timedelta(minutes=LOOKBACK_MIN)).isoformat()
    keys = q.execute("SELECT gid, pid, stat, book, MAX(tip_utc), MAX(player) FROM quotes WHERE seen_at > ? AND seen_at <= ? "
                     "AND pid IS NOT NULL AND book IN ('fd', 'dk') AND stat IN ('points', 'rebounds', 'assists', 'threes') "
                     "GROUP BY gid, pid, stat, book", (since, now)).fetchall()
    done = {(g, p, m, b) for g, p, m, b in con.execute("SELECT gid, pid, market, book FROM opened")}
    rds, stat_cache, fired = {}, {}, 0
    for gid, pid, market, book, tip, player in keys:
        if (gid, pid, market, book) in done:
            continue
        m = R.main_of(board_of(q, gid, pid, market, book, now))
        if not m:
            continue
        con.execute("INSERT OR IGNORE INTO opened VALUES (?, ?, ?, ?, ?)", (gid, pid, market, book, now))
        if first_run or not tip or RP.iso(tip) <= (dt.datetime.fromisoformat(now) + dt.timedelta(minutes=TOO_LATE_MIN)).isoformat():
            continue                                     # install: mark what is already open; never act near or after tip
        date = E._et_date(tip)
        season = ROLE.season_of(date)
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
    print(f"nba_role_open {now}: {len(keys)} recent props, {fired} fired{' (install: marked open, no pings)' if first_run else ''}")
    return fired


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--process", action="store_true")
    a = ap.parse_args()
    if a.process:
        process()


if __name__ == "__main__":
    main()
