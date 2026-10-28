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
from collections import defaultdict
from pathlib import Path

import nba_boost as BOOST
import nba_early as EARLY
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
ABBR = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes": "3PM", "pra": "PRA", "pts_reb": "P+R", "pts_ast": "P+A",
        "reb_ast": "R+A"}
DDL = ["CREATE TABLE IF NOT EXISTS opened (gid TEXT, pid INTEGER, market TEXT, book TEXT, opened_at TEXT, "
       "PRIMARY KEY (gid, pid, market, book))",
       "CREATE TABLE IF NOT EXISTS signals (gid TEXT, pid INTEGER, market TEXT, side TEXT, book TEXT, line REAL, price REAL, "
       "ev REAL, p REAL, mu REAL, out_pids TEXT, date TEXT, team TEXT, player TEXT, logged_at TEXT, pinged INTEGER, "
       "PRIMARY KEY (gid, pid, market, side))",
       "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)",
       "CREATE TABLE IF NOT EXISTS ratio_signals (rule TEXT, gid TEXT, pid INTEGER, market TEXT, book TEXT, line REAL, "
       "price REAL, volume REAL, date TEXT, player TEXT, logged_at TEXT, pinged INTEGER, PRIMARY KEY (rule, gid, pid, market))"]
PINGED_RATIOS = ("RATIO_PA28",)                          # NBA_RATIO_PREREG.md amendment 3: the ratio rules that ping
DDL.append("CREATE TABLE IF NOT EXISTS idea_signals (rule TEXT, gid TEXT, pid INTEGER, market TEXT, line REAL, price REAL, "
           "note TEXT, date TEXT, player TEXT, logged_at TEXT, pinged INTEGER, PRIMARY KEY (rule, gid, pid, market))")
DDL.append("CREATE TABLE IF NOT EXISTS tip30_done (gid TEXT PRIMARY KEY, done_at TEXT)")
DDL.append("CREATE TABLE IF NOT EXISTS step_seen (date TEXT, pid INTEGER, seen_at TEXT, PRIMARY KEY (date, pid))")


def current_boards(q, markets=("points", "rebounds", "assists", "threes")):
    """{(gid, pid, market, book): (board, tip, player, collected_at)} from nba_lines' current board."""
    out = {}
    for book, at, gid, tip, pid, player, stat, line, side, odds in q.execute(
            "SELECT book, collected_at, gid, tip_utc, pid, player, stat, line, side, odds FROM board WHERE pid IS NOT NULL "
            f"AND book IN ('fd', 'dk') AND stat IN ({','.join('?' * len(markets))}) AND odds IS NOT NULL", markets):
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


def early_body(player, line, price, book, fga, last):
    from nba_ping import american
    return (f"🟡 EARLY {player} PTS o{line:g} {american(price)} {BOOK[book]} · {fga:.1f} FGA vs {last:.1f} last season "
            f"({fga / last:.2f}x) · shadow")


def ratio_body(rule, player, market, line, price, book, vol):
    from nba_ping import american
    return (f"🟣 PA28 {player} {ABBR[market]} o{line:g} {american(price)} {BOOK[book]} "
            f"· pot. ast {vol:.1f} ({vol / line:.1f}x) · shadow")


def boost_signal(con, sender, f, gid, pid, market, book, line, price, date, player, x_name, now):
    """Record a BOOST flag, one per (rule, game, player, market) across books; ping BOOST and BOOST_STEP (BOOST_NH and
    BOOST_PICKUP are silent). Returns pings."""
    rule = {"history": "BOOST", "step": "BOOST_STEP", "pickup": "BOOST_PICKUP", "no history": "BOOST_NH"}[BOOST.kind_of(f)]
    cur = con.execute("INSERT OR IGNORE INTO ratio_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                      (rule, gid, pid, market, book, line, price, round(f["hits"] / f["h"] if rule == "BOOST" else f["proj"], 3),
                       date, player, now, 0))
    dup = rule == "BOOST_STEP" and con.execute("SELECT 1 FROM ratio_signals WHERE rule = 'BOOST' AND gid = ? AND pid = ? "
                                               "AND market = ? AND pinged = 1", (gid, pid, market)).fetchone()
    if cur.rowcount and rule in ("BOOST", "BOOST_STEP") and not dup:   # amendments 1, 6: history and STEP ping, once a prop
        ok = sender(BOOST.body(player, market, line, price, BOOK[book], f, x_name))
        con.execute("UPDATE ratio_signals SET pinged = ? WHERE rule = ? AND gid = ? AND pid = ? AND market = ?",
                    (1 if ok else 0, rule, gid, pid, market))
        return 1
    return 0


def step_checks(con, keys, now, n, matchup_db, gamelogs_db, lineups_db, sender, bds, rds, stat_cache):
    """NBA_BOOST_PREREG.md amendments 4 and 6: at the first run after a player first appears as a new starter in
    NBA.com's lineup (or as that starter's bench pickup), his props that opened before that snapshot are judged for
    STEP (or PICKUP) at their current main line. Returns pings."""
    by = defaultdict(list)                               # (date, pid) -> [(gid, market, book, board, tip, player)]
    for (gid, pid, market, book), (board, tip, player, seen) in keys.items():
        if tip and seen <= now:
            by[(E._et_date(tip), pid)].append((gid, market, book, board, tip, player))
    late = (dt.datetime.fromisoformat(now) + dt.timedelta(minutes=TOO_LATE_MIN)).isoformat()
    fired = 0
    for date in sorted({d for d, _p in by}):
        at, fives = BOOST.posted_fives(lineups_db, date, now)
        if not fives:
            continue
        season = ROLE.season_of(date)
        bd = bds.get(season) or bds.setdefault(season, BOOST.live_data(matchup_db, gamelogs_db, season))
        rd = rds.get(season) or rds.setdefault(season, ROLE.RoleData(matchup_db, gamelogs_db, season))
        st = stat_cache.get(date) or stat_cache.setdefault(date, statuses(n, date, now))
        for team, five in sorted(fives.items()):
            if bd.usual_five(team, date) is None:
                continue
            out = {x for x, (tm, s_, _nm) in st.items() if tm == team and s_ in OUTS}
            tfive, pairs = bd.tonight(team, date, out, five)
            who = [(p, BOOST.step_eval) for p in sorted(pairs)]
            who += [(pk[0], BOOST.pickup_eval) for s_ in sorted(pairs) if (pk := bd.pickup(team, date, s_, tfive, out))]
            for p, judge in who:
                if not con.execute("INSERT OR IGNORE INTO step_seen VALUES (?, ?, ?)", (date, p, now)).rowcount:
                    continue                             # checked when he first appeared
                for gid, market, book, board, tip, player in by.get((date, p), ()):
                    op = con.execute("SELECT opened_at FROM opened WHERE gid = ? AND pid = ? AND market = ? AND book = ?",
                                     (gid, p, market, book)).fetchone()
                    m = R.main_of(board)
                    if not op or op[0][:19] >= at or not m or RP.iso(tip) <= late:
                        continue                         # judged at its opener with this lineup, or too late
                    f = judge(bd, rd, date, team, p, market, m[0], m[1], out, five)
                    if f:
                        fired += boost_signal(con, sender, f, gid, p, market, book, m[0], m[1], date, player,
                                              st[f["x"]][2] or str(f["x"]), now)
    return fired


def tip30(con, q, keys, now, n, matchup_db, gamelogs_db, lineups_db, index_json, sender):
    """NBA_IDEAS_PREREG.md amendment 1: at each game's first run at or after tip - 30 (before tip - 5), RETURN_UNDER and
    FOUL_BIG on FanDuel's current board, with the decisions the side-by-side replays. Returns pings sent."""
    import nba_ideas as IDEAS
    import nba_sxs_rules as SR
    from nba_ping import american
    games = defaultdict(dict)                            # gid -> {(pid, market): (main, player)}; gid -> tip (UTC, as posted)
    tips = {}
    for (gid, pid, market, book), (board, tip, player, _s) in keys.items():
        m = R.main_of(board)
        if book == "fd" and m:
            games[gid][(pid, market)] = (m, player)
            tips[gid] = tip
    fired = 0
    for gid, props in sorted(games.items()):
        tip = RP.iso(tips[gid])
        if not (RP.minus(tip, 30) <= now < RP.minus(tip, 5)) or con.execute("SELECT 1 FROM tip30_done WHERE gid = ?", (gid,)).fetchone():
            continue
        con.execute("INSERT INTO tip30_done VALUES (?, ?)", (gid, now))
        date = E._et_date(tips[gid])                     # the posted tip carries its offset; the naive one would read as local time
        season = ROLE.season_of(date)
        rd = ROLE.RoleData(matchup_db, gamelogs_db, season)
        vd = SR.VolumeData(lineups_db, matchup_db, index_json)
        fd = IDEAS.FoulData(matchup_db, season)
        dv = RATIO.DvpData(matchup_db, gamelogs_db, season)
        listed = {p: (tm, st_) for p, (tm, st_, _nm) in statuses(n, date, now).items()}
        team_of = {p: rd.team_of(p, date) for p, _mk in props}
        ha = q.execute("SELECT home, away FROM board WHERE gid = ? AND home IS NOT NULL LIMIT 1", (gid,)).fetchone()
        teams = sorted(ha) if ha else sorted({t for t in team_of.values() if t})
        bets = []
        for team in teams:
            boards = {p for p, t in team_of.items() if t == team}
            history = [{p: r["min"] for p, r in b.items() if r["min"]} for _d, _g, b in rd.season.before(team, date)]
            for b in IDEAS.return_bets(history, SR.cleared_returners(rd, vd, team, date, now, listed), boards):
                bets += [("RETURN_UNDER", b, mk, "teammate returns") for mk in ("points", "rebounds", "assists", "pra")]
        for p, team in team_of.items():
            opp = next((t for t in teams if t != team), None) if team else None
            if IDEAS.foul_bet(fd, dv.groups.get(p) or vd.group(p), p, opp, date):
                bets += [("FOUL_BIG", p, mk, f"{fd.pf36(p, date):.1f} PF/36 vs {opp}") for mk in ("points", "rebounds")]
        for rule, p, mk, note in bets:
            got = props.get((p, mk))
            if not got or not got[0][2]:
                continue
            (line, _o, under), player = got
            cur = con.execute("INSERT OR IGNORE INTO idea_signals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                              (rule, gid, p, mk, line, under, note, date, player, now, 0))
            if cur.rowcount:
                tag = {"RETURN_UNDER": "🔻 RETURN", "FOUL_BIG": "🟠 FOUL"}[rule]
                ok = sender(f"{tag} {player} {ABBR.get(mk, mk.upper())} u{line:g} {american(under)} FD · {note} · shadow")
                con.execute("UPDATE idea_signals SET pinged = ? WHERE rule = ? AND gid = ? AND pid = ? AND market = ?",
                            (1 if ok else 0, rule, gid, p, mk))
                fired += 1
    return fired


def process(now=None, lines_db=HERE / "nba_lines.sqlite", news_db=HERE / "nba_news.sqlite", matchup_db=HERE / "nba_matchup.sqlite",
            gamelogs_db=HERE / "nba_gamelogs.sqlite", tracking_db=HERE / "nba_tracking.sqlite", lineups_db=HERE / "nba_lineups.sqlite",
            index_json=HERE / "nba_player_index.json", db=DB, sender=None):
    import nba_ping as PING
    sender = sender or PING.send
    now = now or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    con = sqlite3.connect(db)
    for s_ in DDL:
        con.execute(s_)
    q, n = PD._ro(lines_db), PD._ro(news_db)
    first_run = con.execute("SELECT value FROM meta WHERE key = 'installed'").fetchone() is None
    keys = current_boards(q, markets=tuple(BOOST.PARTS))
    installed = set((con.execute("SELECT value FROM meta WHERE key = 'markets'").fetchone() or (",".join(ROLE.MARKET_STAT),))[0].split(","))
    done = {(g, p, m, b) for g, p, m, b in con.execute("SELECT gid, pid, market, book FROM opened")}
    rds, rts, eds, bds, stat_cache, fives_of, fired = {}, {}, {}, {}, {}, {}, 0
    for (gid, pid, market, book), (board, tip, player, seen) in sorted(keys.items()):
        if market not in BOOST.PARTS or (gid, pid, market, book) in done or seen > now:
            continue
        m = R.main_of(board)
        if not m:
            continue
        con.execute("INSERT OR IGNORE INTO opened VALUES (?, ?, ?, ?, ?)", (gid, pid, market, book, seen))
        if first_run or market not in installed or not tip or RP.iso(tip) <= (dt.datetime.fromisoformat(now) + dt.timedelta(minutes=TOO_LATE_MIN)).isoformat():
            continue                                     # install (or a market new here): mark what is open; never act near tip
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
        if market == "points":                           # NBA_EARLY_PREREG.md amendment 2: the early volume surge, pinged
            ed = eds.get(season) or eds.setdefault(season, EARLY.EarlyData(matchup_db, gamelogs_db, season))
            if EARLY.early_surge(ed, pid, date, m[0]):
                g_ = [(mn, f) for d_, mn, f in ed.games.get(pid, ()) if d_ < date]
                fga = sum(f for _m, f in g_) / len(g_)
                cur = con.execute("INSERT OR IGNORE INTO ratio_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                  ("EARLY_SURGE", gid, pid, market, book, m[0], m[1], round(fga, 2), date, player, now, 0))
                if cur.rowcount:
                    ok = sender(early_body(player, m[0], m[1], book, fga, ed.last[pid]))
                    con.execute("UPDATE ratio_signals SET pinged = ? WHERE rule = 'EARLY_SURGE' AND gid = ? AND pid = ? AND market = ?",
                                (1 if ok else 0, gid, pid, market))
                    fired += 1
        bd = bds.get(season) or bds.setdefault(season, BOOST.live_data(matchup_db, gamelogs_db, season))
        bteam = bd.team_now(pid, date)                   # NBA_BOOST_PREREG.md: a starter out, the teammate's over
        if bteam:
            st = stat_cache.get(date) or stat_cache.setdefault(date, statuses(n, date, now))
            out_b = {x for x, (tm, s_, _nm) in st.items() if tm == bteam and s_ in OUTS}
            fv = fives_of.get(date) or fives_of.setdefault(date, BOOST.posted_fives(lineups_db, date, now))
            if out_b:                                    # amendment 6: STEP and PICKUP beside BOOST / BOOST_NH
                rd = rds.get(season) or rds.setdefault(season, ROLE.RoleData(matchup_db, gamelogs_db, season))
                five = fv[1].get(bteam)
                for f in (BOOST.boost_eval(bd, date, bteam, pid, market, m[0], m[1], out_b),
                          BOOST.step_eval(bd, rd, date, bteam, pid, market, m[0], m[1], out_b, five),
                          BOOST.pickup_eval(bd, rd, date, bteam, pid, market, m[0], m[1], out_b, five)):
                    if f:
                        fired += boost_signal(con, sender, f, gid, pid, market, book, m[0], m[1], date, player,
                                              st[f["x"]][2] or str(f["x"]), now)
        if market not in ROLE.MARKET_STAT:
            continue
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
    if not first_run:
        fired += step_checks(con, keys, now, n, matchup_db, gamelogs_db, lineups_db, sender, bds, rds, stat_cache)
        fired += tip30(con, q, keys, now, n, matchup_db, gamelogs_db, lineups_db, index_json, sender)
    if first_run:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('installed', ?)", (now,))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('markets', ?)", (",".join(BOOST.PARTS),))
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
