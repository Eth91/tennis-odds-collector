#!/usr/bin/env python3
"""NBA prop research for Pickz: the data behind docs/nba_props.html (the page itself is nba_research_ui.py).

From the slate to one prop: every player prop FanDuel and DraftKings post (nba_lines.board, with alternate rungs),
the player's game logs (this season and last, nba_matchup.sqlite box scores), the official injury report and the
news items the engine stores (kept apart, each with its time), matchup context (nba_matchup's point-in-time pace
and defense-vs-position factors; FanDuel's spread and total), historical association with the other props posted
for the same game, each book's line history (rebuilt from the quotes change log), the fair price (the books' no-vig
consensus) and how far the best price beats it, the engine's own shadow flags, and live box scores for games in
progress. Everything is descriptive or a market estimate. Nothing here is a projection or a bet. Which of it has
predicted anything is graded nightly by nba_research_score.py.

Read-only over the engine's stores; the output is one JSON file the page fetches.

LIMITS (shown on the page where they apply):
  books     FanDuel and DraftKings only (nba_lines). Markets: points, rebounds, assists, threes, PRA, P+R, P+A, R+A —
            what those feeds carry. No steals / blocks / turnovers props are collected, so none are listed.
  freshness each book's board refreshes about every 10 min (every 2 near tip); older than BOOK_STALE_MIN = "stale".
            The page is rebuilt every 2 min on the VM (cron); live box scores are fetched at each rebuild.
  logs      regular-season box scores, this season and last (nba_matchup.sqlite). No playoff games.
  matchup   ranks blend this season with last (rank_tables_blend, BLEND_K games); pace is this season only; no
            defense-vs-position factor for threes.
  injuries  the official report as stored by nba_injury_report; news items are third-party, labeled as such.
  related   Pearson r over shared games: a description of the past, not a correlation model or a prediction.

    python3 nba_research.py --out /home/ubuntu/tennis-odds-collector/docs    # writes nba_props.json + .html
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import re
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LINES, NEWS, SHADOW = HERE / "nba_lines.sqlite", HERE / "nba_news.sqlite", HERE / "nba_shadow.sqlite"
INDEX = HERE / "nba_player_index.json"
TRACKING = HERE / "nba_tracking.sqlite"
PROJ_LOG = HERE / "nba_proj_log.sqlite"          # the projection engine's prospective record (prereg test C)
ROLE = HERE / "nba_role.sqlite"                  # the engine's rules' log (nba_role_open.py, the VM cron); read-only
LINEUPS = HERE / "nba_lineups.sqlite"            # NBA.com's daily lineups as seen (nba_lineups_poll.py, the VM cron)
CLOSE_BOARDS = HERE / "nba_close_boards.json"    # each started game's last board before tip (closing_boards), cached
SLATE_ROLL_H = 6     # the slate moves on to the next day at 6 AM ET (4 AM MT), not midnight: late games stay on it
USUAL_GAMES = 10                                 # a team's usual starters: its most frequent five over its last 10 games
USUAL_MIN = 3                                    # ...this season, once it has 3 (before that, no starter is marked new)
ET, MT = ZoneInfo("America/New_York"), ZoneInfo("America/Denver")
# market -> (label, box-score parts). Only the markets the books' feeds carry (nba_lines.STAT_MAP).
MARKETS = {"points": ("PTS", ("pts",)), "rebounds": ("REB", ("reb",)), "assists": ("AST", ("ast",)),
           "threes": ("3PM", ("fg3m",)), "pra": ("PRA", ("pts", "reb", "ast")), "pts_reb": ("P+R", ("pts", "reb")),
           "pts_ast": ("P+A", ("pts", "ast")), "reb_ast": ("R+A", ("reb", "ast"))}
MATCHUP_KEY = {"points": "pts", "rebounds": "reb", "assists": "ast", "pra": "pra", "pts_reb": "pts_reb",
               "pts_ast": "pts_ast", "reb_ast": "reb_ast"}           # threes: no matchup factor is computed
LOG_COLS = ("date", "gid", "team", "opp", "home", "starter", "min", "pts", "reb", "ast", "fg3m", "fga", "fg3a", "fta",
            "margin", "rest", "usg", "pot_ast", "reb_ch")   # margin = his team's final margin; rest = days off before the game (0 = back-to-back);
                                       # usg = usage % (the share of his team's possessions he used while on the floor)
                                       # pot_ast / reb_ch = potential assists / rebound chances (nba_tracking.sqlite;
                                       # None where tracking has no row for that game)


def usage(mn, fga, fta, tov, t_fga, t_fta, t_tov, t_min):
    """Usage % (Basketball-Reference): 100 * (FGA + .44 FTA + TOV) * (team minutes / 5) / (MP * (team FGA + .44 FTA + TOV)).
    None under a minute or without the team's totals."""
    if None in (fga, fta, tov, t_fga, t_fta, t_tov, t_min) or not mn or mn < 1:
        return None
    den = mn * (t_fga + .44 * t_fta + t_tov)
    return round(100 * (fga + .44 * fta + tov) * (t_min / 5) / den, 1) if den else None
BOOK_STALE_MIN = 20          # a book's board older than this is shown as stale (it refreshes every ~10 min)
CORR_MIN_N, CORR_TOP = 15, 4
EVEN = 1.9091


def _naive_utc(t):
    t = dt.datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    return (t.astimezone(dt.timezone.utc) if t.tzinfo else t).replace(tzinfo=None, microsecond=0)


def season_of(date):
    y = int(date[:4]) if int(date[5:7]) >= 8 else int(date[:4]) - 1
    return f"{y}-{str(y + 1)[2:]}"


def prev_season(season):
    return f"{int(season[:4]) - 1}-{season[2:4]}"


# ── derived statistics (the page's JS mirrors these; test_nba_research checks both agree) ──────────────────
def stat_value(log, market):
    """A market's value in one game log (dict keyed by LOG_COLS), or None when a part is missing."""
    parts = MARKETS[market][1]
    vals = [log.get(p) for p in parts]
    return None if any(v is None for v in vals) else float(sum(vals))


def hit_summary(values, line):
    """Over / under / push counts at `line` over the games with a value; avg and median of those values."""
    vals = [v for v in values if v is not None]
    if not vals:
        return {"n": 0, "over": 0, "under": 0, "push": 0, "avg": None, "med": None}
    over = sum(1 for v in vals if v > line)
    under = sum(1 for v in vals if v < line)
    return {"n": len(vals), "over": over, "under": under, "push": len(vals) - over - under,
            "avg": round(st.mean(vals), 2), "med": float(st.median(vals))}


def pearson(xs, ys):
    """Pearson r over aligned pairs (both present), or None with < 3 pairs or no variance."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None
    sx = sy = 0                                       # two passes, not five: the page build runs it ~15k times
    for x, y in pairs:
        sx += x
        sy += y
    mx, my = sx / n, sy / n
    sxy = sxx = syy = 0
    for x, y in pairs:
        dx, dy = x - mx, y - my
        sxy += dx * dy
        sxx += dx * dx
        syy += dy * dy
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


# ── prices ──────────────────────────────────────────────────────────────────────────────────────────────
def no_vig(o, u):
    """The over's no-vig probability from decimal over / under prices, or None."""
    if not o or not u or o <= 1 or u <= 1:
        return None
    a, b = 1 / o, 1 / u
    return a / (a + b)


def rung(bookq, line):
    return next((r for r in bookq["rungs"] if r[0] == line), None) if bookq else None


def fair_at(books, line):
    """(the over's fair probability at `line`, books used): the mean no-vig of every book pricing both sides of
    that rung. (None, 0) when no book does. A market estimate, not a projection."""
    ps = [p for p in (no_vig(*(rung(books.get(b), line) or (None, None, None))[1:]) for b in ("fd", "dk")) if p is not None]
    return (sum(ps) / len(ps), len(ps)) if ps else (None, 0)


def value_at(books, line, side):
    """The best price on `side` at `line` against the fair probability: {"ev" (per $1), "book", "price", "fair"},
    or None. EV is positive only when one book's price beats the books' consensus."""
    fair, _ = fair_at(books, line)
    if fair is None:
        return None
    k, pr = (1, fair) if side == "over" else (2, 1 - fair)
    best = None
    for b in ("fd", "dk"):
        r = rung(books.get(b), line)
        if r and r[k] and (best is None or r[k] > best[1]):
            best = (b, r[k])
    return None if best is None else {"ev": best[1] * pr - 1, "book": best[0], "price": best[1], "fair": pr}


def zscore(hits, n, p):
    """How unusual `hits` in `n` games are if each game hits with probability `p` (the price's): (hits - np) /
    sqrt(np(1-p)). None without games or a price. |z| >= 1 is what the page colors."""
    if not n or p is None or not 0 < p < 1:
        return None
    return (hits - n * p) / math.sqrt(n * p * (1 - p))


# ── the price change log ─────────────────────────────────────────────────────────────────────────────────
def replay(rows):
    """rows = (seen_at, book, gid, pid, stat, line, side, odds) from nba_lines.quotes in time order. quotes is a
    CHANGE log: a cycle writes only the rungs whose price changed, and a rung taken down as odds NULL. So each
    book's board is carried forward. Yields (seen_at, {(gid, pid, stat, book): {(line, side): odds}}) with the
    full current state of every key that changed at that time."""
    state = defaultdict(dict)
    t0, dirty = None, set()
    for t, book, gid, pid, stat, line, side, odds in rows:
        if t != t0 and dirty:
            yield t0, {k: state[k] for k in dirty}
            dirty = set()
        t0 = t
        k = (gid, pid, stat, book)
        if odds is None:
            state[k].pop((round(float(line), 1), side), None)
        else:
            state[k][(round(float(line), 1), side)] = odds
        dirty.add(k)
    if dirty:
        yield t0, {k: state[k] for k in dirty}


def rungs_of(state):
    lines = sorted({ln for ln, _ in state})
    return [[ln, state.get((ln, "over")), state.get((ln, "under"))] for ln in lines]


def main_of(state):
    """(line, over, under) of the main rung of a board state, or None."""
    rr = rungs_of(state)
    ml = main_line(rr)
    return None if ml is None else tuple(next(r for r in rr if r[0] == ml))


HIST_MAX = 40


_r3 = lambda x: None if x is None else round(x, 3)


def line_history(q, gids, markets=None):
    """{(gid, pid, stat): {book: [[seen_at, line, over, under], ...]}} — each book's main rung every time it changed
    (the first entry = the open), from the change log. Long histories keep the first, the last and an even sample."""
    out = defaultdict(dict)
    if q is None or not gids:
        return out
    rows = q.execute(f"SELECT seen_at, book, gid, pid, stat, line, side, odds FROM quotes WHERE gid IN "
                     f"({','.join('?' * len(gids))}) AND pid IS NOT NULL ORDER BY seen_at", list(gids))
    tl = defaultdict(list)
    markets = MARKETS if markets is None else markets
    for t, changed in replay(r for r in rows if r[4] in markets):
        for k, st_ in changed.items():
            m = main_of(st_)
            if m is None:
                continue
            m = [t, m[0], round(m[1], 4) if m[1] else None, round(m[2], 4) if m[2] else None]
            if not tl[k] or tl[k][-1][1:] != m[1:]:
                tl[k].append(m)
    for (gid, pid, stat, book), pts in tl.items():
        if len(pts) > HIST_MAX:
            step = (len(pts) - 1) / (HIST_MAX - 1)
            pts = [pts[round(i * step)] for i in range(HIST_MAX)]
        out[(gid, pid, stat)][book] = pts
    return out


def main_line(rungs):
    """The book's main rung: two-sided, over price nearest even money (the engine's rule). rungs: [[line, o, u]]."""
    two = [r for r in rungs if r[1] and r[2]]
    return min(two, key=lambda r: abs(r[1] - EVEN))[0] if two else None


# ── sources ──────────────────────────────────────────────────────────────────────────────────────────────
def _ro(path):
    path = Path(path)
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if path.exists() else None


def book_quotes(q, gids, markets=None):
    """{(gid, pid, market): {book: {"updated", "rungs": [[line, over, under]], "main"}}}, {(gid, pid): name},
    {book: newest collected_at}. nba_lines.board holds each book's latest board."""
    out = defaultdict(dict)
    names, newest = {}, {}
    if q is None or not gids:
        return out, names, newest
    marks = ",".join("?" * len(gids))
    raw = defaultdict(lambda: defaultdict(lambda: [None, None]))
    upd = {}
    for book, at, gid, pid, player, stat, line, side, odds in q.execute(
            f"SELECT book, collected_at, gid, pid, player, stat, line, side, odds FROM board WHERE gid IN ({marks}) "
            f"AND pid IS NOT NULL", list(gids)):
        if stat not in (MARKETS if markets is None else markets) or odds is None:
            continue
        k = (gid, int(pid), stat, book)
        raw[k][round(float(line), 1)][0 if side == "over" else 1] = round(float(odds), 4)
        upd[k] = max(upd.get(k, ""), at or "")
        names[(gid, int(pid))] = player
        newest[book] = max(newest.get(book, ""), at or "")
    for (gid, pid, stat, book), rungs in raw.items():
        rr = sorted([[ln, o, u] for ln, (o, u) in rungs.items()], key=lambda r: r[0])
        out[(gid, pid, stat)][book] = {"updated": upd[(gid, pid, stat, book)], "rungs": rr, "main": main_line(rr)}
    return out, names, newest


REST = LOG_COLS.index("rest")


# a tracking value no real game reaches, per minute played: nba_tracking.sqlite has a few dates stored as multi-game totals
# (2026-04-01: up to 517 potential assists). Every single game in the store sits at or under 0.99 potential assists and
# 1.39 rebound chances a minute (10+ minutes, 23,100 player-games); past these the value is dropped, not used
TRK_MAX_PER_MIN = (1.0, 1.4)


def tracking(trk, pids):
    """{(date, pid): (potential assists, rebound chances)} from nba_tracking.sqlite. The Rebounding feed omits
    players with no rebound chances, so a tracked game without a rebounding value is 0 chances."""
    out = {}
    if trk is None or not pids:
        return out
    pids = list(pids)
    for i in range(0, len(pids), 400):
        chunk = pids[i:i + 400]
        for d, pid, pa, rc in trk.execute(f"SELECT date, player_id, potential_ast, reb_chances FROM tracking "
                                          f"WHERE player_id IN ({','.join('?' * len(chunk))})", chunk):
            out[(d, pid)] = (pa, rc if rc is not None else (0 if pa is not None else None))
    return out


def game_logs(mcon, pids, seasons, trk=None):
    """{pid: [log rows in LOG_COLS order]} from the cached box scores, oldest first; trk = nba_tracking.sqlite."""
    out = defaultdict(list)
    if mcon is None or not pids:
        return out
    pids = list(pids)
    tr = tracking(trk, pids)
    for i in range(0, len(pids), 400):
        chunk = pids[i:i + 400]
        q = ("SELECT p.pid, g.date, p.gid, p.team, CASE WHEN p.team = g.home THEN g.away ELSE g.home END, "
             "CASE WHEN p.team = g.home THEN 1 ELSE 0 END, p.starter, p.min, p.pts, p.reb, p.ast, p.fg3m, p.fga, p.fg3a, "
             "p.fta, CASE WHEN p.team = g.home THEN g.home_pts - g.away_pts ELSE g.away_pts - g.home_pts END, "
             "p.tov, t.fga, t.fta, t.tov, (SELECT SUM(x.min) FROM player_games x WHERE x.gid = p.gid AND x.team = p.team) "
             "FROM player_games p JOIN games g ON g.gid = p.gid LEFT JOIN team_games t ON t.gid = p.gid AND t.team = p.team "
             f"WHERE p.pid IN ({','.join('?' * len(chunk))}) "
             f"AND g.season IN ({','.join('?' * len(seasons))}) ORDER BY g.date, p.gid")
        for r in mcon.execute(q, chunk + list(seasons)):
            t = list(tr.get((r[1], r[0]), (None, None)))
            for k in (0, 1):                                    # an impossible tracking value: dropped
                if t[k] is not None and (r[7] or 0) >= 5 and t[k] / r[7] > TRK_MAX_PER_MIN[k]:
                    t[k] = None
            row = list(r[1:16]) + [None, usage(r[7], r[12], r[14], *r[16:])] + t
            row[6] = round(row[6] or 0, 1)
            out[r[0]].append(row)
    for rows in out.values():                       # rest: days off since his previous game; none across the summer
        for prev, row in zip([None] + rows[:-1], rows):
            if prev is not None:
                gap = (dt.date.fromisoformat(row[0]) - dt.date.fromisoformat(prev[0])).days - 1
                row[REST] = gap if gap <= 30 else None
    return out


def official_status(ncon, game_dates):
    """The latest official report listing each game date: ({(date, pid): {...}}, {(date, team): True},
    {date: {"mark", "published"}}). A team on the report without the player = not on the report."""
    status, teams, meta = {}, {}, {}
    if ncon is None:
        return status, teams, meta
    for d in game_dates:
        row = ncon.execute("SELECT mark, published_at FROM snapshots WHERE game_date=? ORDER BY published_at DESC "
                           "LIMIT 1", (d,)).fetchone()
        if not row:
            continue
        mark, pub = row
        meta[d] = {"mark": mark, "published": pub}
        for team, pid, player, st_, reason in ncon.execute(
                "SELECT team, pid, player, status, reason FROM snapshots WHERE game_date=? AND mark=?", (d, mark)):
            teams[(d, team)] = True
            if pid is not None:
                reason = re.sub(r"\s*\d{1,2}:\d{2}\s*\(ET\)\s*$", "", reason or "")   # the parser's game-time column
                status[(d, int(pid))] = {"status": st_, "reason": reason[:80], "published": pub, "team": team,
                                         "player": player}
    return status, teams, meta


def news_items(ncon, game_dates):
    """{(date, pid): [{source, status, detected, headline}]} — third-party items the engine stored, newest first."""
    out = defaultdict(list)
    if ncon is None:
        return out
    marks = ",".join("?" * len(game_dates))
    for src, det, pid, d, status, head, prov in ncon.execute(
            f"SELECT source, detected_at, pid, game_date, status, headline, provenance FROM news_items "
            f"WHERE game_date IN ({marks}) AND pid IS NOT NULL AND COALESCE(seeded, 0) = 0 ORDER BY detected_at DESC",
            list(game_dates)):
        k = (d, int(pid))
        if len(out[k]) < 3:
            author = (prov or "").split(":")[-1] if src == "x" else ""
            out[k].append({"source": src + (f" @{author}" if author and author != "x" else ""), "status": status,
                           "detected": det, "headline": (head or "")[:140]})
    return out


def game_lines(q, gids):
    """{gid: {"spread_home", "spread_away", "total", "updated"}} — FanDuel's latest game lines."""
    out = {}
    if q is None:
        return out
    for gid in gids:
        g = {}
        try:
            for market, side, key in (("spread", "home", "spread_home"), ("spread", "away", "spread_away"),
                                      ("total", "over", "total")):
                r = q.execute("SELECT line, seen_at FROM game_lines WHERE gid=? AND market=? AND side=? "
                              "ORDER BY seen_at DESC LIMIT 1", (gid, market, side)).fetchone()
                if r:
                    g[key] = r[0]
                    g["updated"] = max(g.get("updated", ""), r[1])
        except sqlite3.OperationalError:
            return out
        if g:
            out[gid] = g
    return out


def engine_flags(sh, game_dates):
    """{(gid, pid, market): {tier, card, why, line}} — the engine's SHADOW flags (never bets), one per play."""
    out = {}
    if sh is None:
        return out
    stat_of = {"pts": "points", "reb": "rebounds", "ast": "assists"}
    marks = ",".join("?" * len(game_dates))
    for gid, pid, stat, tier, card, why, line in sh.execute(
            f"SELECT gid, pid, stat, tier, card, card_why, line FROM flags WHERE game_date IN ({marks}) AND "
            f"void_reason IS NULL AND pid IS NOT NULL ORDER BY logged_at", list(game_dates)):
        k = (gid, int(pid), stat_of.get(stat, stat))
        cur = out.get(k)
        if cur is None or (card == 1 and cur["card"] != 1):
            out[k] = {"tier": tier, "card": card, "why": why, "line": line}
    return out


UNDER_PRICE = 1 / 0.6                                    # −150 or better, decimal
UNDER_BAND = (0.50, 0.70)                                # our projection over the line: 30–50% below it


def under_play(market, price, line, proj):
    """A play that pings the phone (nba_under.pings on the VM): an under at −150 or better, not threes, with our
    projection 30–50% below the line."""
    return (market != "threes" and price is not None and price >= UNDER_PRICE and bool(line) and proj is not None
            and UNDER_BAND[0] <= proj / line < UNDER_BAND[1])


def under_flags(rc, game_dates):
    """The board's flags: the under plays in nba_role.sqlite's idea_signals (rule UNDER20, read-only) that meet the
    ping criteria, whether or not the phone send went through, as logged: [{date, gid, pid, market, side, line, price
    (decimal), proj, mins, at (UTC), player}]. SHADOW plays: none is a bet. The engine's other rules are tracked
    silently and are not flags."""
    if rc is None or not game_dates:
        return []
    try:
        rows = rc.execute("SELECT date, gid, pid, market, line, price, note, player, logged_at FROM idea_signals WHERE "
                          f"rule = 'UNDER20' AND date IN ({','.join('?' * len(game_dates))}) ORDER BY logged_at",
                          list(game_dates)).fetchall()
    except sqlite3.OperationalError:                         # not made yet, or busy: no flags this build
        return []
    out = []
    for d, gid, pid, mk, line, price, note, player, at in rows:
        w = (note or "").split()                             # "proj 7.3 min 20.1"
        kv = dict(zip(w[::2], w[1::2]))
        try:
            proj, mins = float(kv["proj"]), float(kv["min"]) if "min" in kv else None
        except (KeyError, ValueError):
            continue
        if under_play(mk, price, line, proj):
            out.append({"date": d, "gid": gid, "pid": pid, "market": mk, "side": "under", "line": line, "price": price,
                        "proj": proj, "mins": mins, "at": at, "player": player})
    return out


def live_state(sched_games, get=None, now=None):
    """{gid: {"state", "label", "score", "stats": {pid: {...}}, "updated"}} for the slate. Box scores are fetched
    only for games in progress or finished today; a fetch failure leaves the state from the schedule."""
    if get is None:
        import nba_rosters as R
        get = lambda g: R._get(R.BOX.format(g))["game"]
    now = now or dt.datetime.now(dt.timezone.utc)
    out = {}
    for g in sched_games:
        ppd = "ppd" in (g.get("status_text") or "").lower() or "postpon" in (g.get("status_text") or "").lower()
        state = "postponed" if ppd else {1: "pregame", 2: "live", 3: "final"}.get(g.get("status"), "unknown")
        rec = {"state": state, "label": g.get("status_text") or "", "score": None, "stats": {}, "updated": None}
        if state in ("live", "final"):
            try:
                b = get(g["gid"])
                rec["label"] = b.get("gameStatusText") or rec["label"]
                rec["score"] = [b["awayTeam"].get("score"), b["homeTeam"].get("score")]
                rec["updated"] = now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
                if b.get("gameStatus") == 3:
                    rec["state"] = "final"
                for side in ("homeTeam", "awayTeam"):
                    for p in side_players(b[side]):
                        rec["stats"][p[0]] = p[1]
            except Exception as e:                                           # noqa: BLE001
                rec["error"] = f"live box unavailable ({type(e).__name__})"
        out[g["gid"]] = rec
    return out


def side_players(team):
    import nba_matchup as MU
    for p in team.get("players", []):
        s = p.get("statistics") or {}
        if str(p.get("played")) != "1":
            continue
        yield int(p["personId"]), {"min": round(MU._minutes(s.get("minutes")), 1), "pts": s.get("points", 0),
                                   "reb": s.get("reboundsTotal", 0), "ast": s.get("assists", 0),
                                   "fg3m": s.get("threePointersMade", 0)}


FRESH_GAMES = 2      # an absence is news while the player was in one of the team's last 2 games


def absences(official, logs_by_team, game_dates, team_last=None):
    """{(date, team): [{pid, name, status, played: [gids], since, mpg, fresh}]} — tonight's Out/Doubtful players with
    >= 10 games and >= 20 minutes a game for the team in the cached logs (the 'without' split). fresh = he played in
    one of the team's last FRESH_GAMES games (team_last: {team: [gids]}): news the recent logs don't reflect yet."""
    out = defaultdict(list)
    for (d, pid), s in official.items():
        if s["status"] not in ("Out", "Doubtful"):
            continue
        for team, rows in logs_by_team.get(pid, {}).items():
            if team != s.get("team"):
                continue                                   # the team the report lists him on, not a former one
            if len(rows) >= 10 and sum(r[6] for r in rows) / len(rows) >= 20:
                played = [r[1] for r in rows]
                out[(d, team)].append({"pid": pid, "status": s["status"], "played": played,
                                       "since": rows[0][0], "mpg": round(sum(r[6] for r in rows) / len(rows), 1),
                                       "fresh": any(g in played for g in (team_last or {}).get(team, []))})
    for v in out.values():
        v.sort(key=lambda a: -a["mpg"])                    # the biggest minutes first: the one the list names
    return out


INJ_ORDER = ("Out", "Doubtful", "Questionable", "Probable")
ROTATION_MPG = 10.0  # a listed player under 10 minutes a game gets no replacement read (two-ways, the end of the bench)
MIN_WITHOUT = 2      # games a teammate played beside his absence before his minutes / starts in them are read
MIN_GAIN = 2.0       # minutes a game a teammate must gain without him to be named


def team_boxes(mcon, teams, seasons):
    """{team: [(gid, date, season, {pid: (starter, min)})]} oldest first, from the cached box scores (players who
    played; a player missing from a game's box did not play)."""
    out = defaultdict(list)
    if mcon is None or not teams:
        return out
    seen = {}
    for gid, d, s, team, pid, st, mn in mcon.execute(
            f"SELECT g.gid, g.date, g.season, p.team, p.pid, p.starter, p.min FROM player_games p JOIN games g "
            f"ON g.gid = p.gid WHERE p.team IN ({','.join('?' * len(teams))}) "
            f"AND g.season IN ({','.join('?' * len(seasons))}) ORDER BY g.date, g.gid", list(teams) + list(seasons)):
        if (team, gid) not in seen:
            seen[(team, gid)] = (gid, d, s, {})
            out[team].append(seen[(team, gid)])
        seen[(team, gid)][3][pid] = (st or 0, mn or 0.0)
    return out


def appearances(mcon, pids, seasons):
    """{pid: [(date, season, team, starter, min)]} every game each player played, any team, oldest first."""
    out = defaultdict(list)
    if mcon is None or not pids:
        return out
    pids = list(pids)
    for i in range(0, len(pids), 400):
        chunk = pids[i:i + 400]
        for pid, d, s, team, st, mn in mcon.execute(
                f"SELECT p.pid, g.date, g.season, p.team, p.starter, p.min FROM player_games p JOIN games g ON g.gid = p.gid "
                f"WHERE p.pid IN ({','.join('?' * len(chunk))}) AND g.season IN ({','.join('?' * len(seasons))}) "
                f"ORDER BY g.date", chunk + list(seasons)):
            out[pid].append((d, s, team, st or 0, mn or 0.0))
    return out


def depth_read(boxes, x, mates, stays):
    """How the team played the games player x missed. boxes: the team's team_boxes rows; mates: the teammates to read;
    stays: {season: True} when x was still on the team after his last game that season (sitting, not traded), so
    the team's later games that season count as missed. Each teammate is read over his own first-to-last game for
    the team (a game inside that span he sat counts as 0 minutes).
    -> (games x played, games x missed, {pid: [n_with, n_without, min_with, min_without, starts_with, starts_without]})"""
    by_season = defaultdict(list)
    for b in boxes:
        by_season[b[2]].append(b)
    out, played, missed = defaultdict(lambda: [0, 0, 0.0, 0.0, 0, 0]), 0, 0
    for s, gs in by_season.items():
        at = [i for i, b in enumerate(gs) if x in b[3]]
        if at:
            lo, hi = at[0], len(gs) - 1 if stays.get(s) else at[-1]
        elif stays.get(s):
            lo, hi = 0, len(gs) - 1                      # on the team all season without a game
        else:
            continue
        played += sum(1 for b in gs[lo:hi + 1] if x in b[3])
        missed += sum(1 for b in gs[lo:hi + 1] if x not in b[3])
        for y in mates:
            ay = [i for i, b in enumerate(gs) if y in b[3]]
            if not ay:
                continue
            for b in gs[max(lo, ay[0]):min(hi, ay[-1]) + 1]:
                st, mn = b[3].get(y, (0, 0.0))
                k = 0 if x in b[3] else 1
                r = out[y]
                r[k] += 1
                r[2 + k] += mn
                r[4 + k] += st
    return played, missed, out


def schedule_spots(sched, gids):
    """Each team's schedule spot in the games `gids`, from the season's schedule (postponed games left out) ->
    {gid: {TRI: {rest, b2b, g3in4, g4in6, trip}}}: days off before the game (None for a team's first), a back-to-back,
    a 3rd game in 4 nights, a 4th in 6, and on the road, which game of the trip it is: [k, n] (None at home)."""
    want, by = set(gids), defaultdict(list)
    for g in sched:
        if "PPD" in (g.get("status_text") or "").upper():
            continue
        by[g["home"]].append((g["date_et"], g["gid"], True))
        by[g["away"]].append((g["date_et"], g["gid"], False))
    out = {}
    for team, gl in by.items():
        gl.sort()
        days = [dt.date.fromisoformat(d) for d, _, _ in gl]
        for i, (_, gid, home) in enumerate(gl):
            if gid not in want:
                continue
            day = days[i]
            rest = (day - days[i - 1]).days - 1 if i else None
            within = lambda n: sum(1 for x in days[max(0, i - n):i + 1] if (day - x).days < n + 1)
            trip = None
            if not home:
                a = b = i
                while a > 0 and not gl[a - 1][2]:
                    a -= 1
                while b + 1 < len(gl) and not gl[b + 1][2]:
                    b += 1
                trip = [i - a + 1, b - a + 1]
            out.setdefault(gid, {})[team] = {"rest": rest, "b2b": rest == 0, "g3in4": within(3) >= 3,
                                             "g4in6": within(5) >= 4, "trip": trip}
    return out


def closing_boards(q, gids, cache=CLOSE_BOARDS, markets=None):
    """The books pull a game's props at tip, so the board loses them; the Live tab still wants them. -> ({(gid, pid,
    stat): {book: {"updated", "rungs", "main"}}}, {(gid, pid): name}) from each prop's last board before tip
    (nba_research_score.boards_before_tip), for started games. Cached per game in `cache`: a past board never changes."""
    import nba_research_score as RSC
    out, names = defaultdict(dict), {}
    if q is None or not gids:
        return out, names
    try:
        cached = json.loads(Path(cache).read_text())
    except (OSError, ValueError):
        cached = {}
    todo = [g for g in gids if g not in cached]
    if todo:
        marks = ",".join("?" * len(todo))
        nm = {}
        for gid, pid, player in q.execute(f"SELECT gid, pid, MAX(player) FROM quotes WHERE gid IN ({marks}) AND pid IS NOT NULL "
                                          f"GROUP BY gid, pid", todo):
            nm.setdefault(gid, {})[str(int(pid))] = player
        for gid in todo:
            cached[gid] = {"names": nm.get(gid, {}), "boards": {}}
        for (gid, pid, stat, book), rec in RSC.boards_before_tip(q, todo, markets).items():
            rr = rungs_of(rec["close"] or {})
            if rr:
                cached[gid]["boards"][f"{pid}|{stat}|{book}"] = rr
        tmp = Path(cache).with_name("." + Path(cache).name + ".tmp")
        tmp.write_text(json.dumps(cached, separators=(",", ":")))
        os.replace(tmp, cache)
    for gid in gids:
        c = cached.get(gid) or {}
        for k, rr in c.get("boards", {}).items():
            pid, stat, book = k.split("|")
            out[(gid, int(pid), stat)][book] = {"updated": None, "rungs": rr, "main": main_line(rr)}
        for pid, name in c.get("names", {}).items():
            names[(gid, int(pid))] = name
    return out, names


def lineups(lcon, dates, boxes, official):
    """{"date|TEAM": {status, at, starters: [[pid, name, pos]], usual: [pid], missing: [[pid, name, status]],
    inactive: [[pid, name]]}} from the latest NBA.com lineups snapshot of each date (nba_lineups_poll.py). status:
    Confirmed once all five starters are, else Expected; at: the newest confirmation. usual: the five who started most
    of the team's last USUAL_GAMES games this season (team_boxes rows), empty until it has USUAL_MIN (last season's
    starters are not this team's after an offseason); missing: a usual starter on tonight's list not starting, with his
    status on the official report. A date with no snapshot (lineups are posted on game day) is left out."""
    import zlib
    out = {}
    if lcon is None:
        return out
    for d in dates:
        row = lcon.execute("SELECT body FROM snaps WHERE date_et=? ORDER BY fetched_at DESC LIMIT 1", (d,)).fetchone()
        if not row:
            continue
        try:
            j = json.loads(zlib.decompress(row[0]))
        except (zlib.error, ValueError):
            j = json.loads(row[0])
        for g in j.get("games", []):
            for side in ("homeTeam", "awayTeam"):
                t = g.get(side) or {}
                team, ps = t.get("teamAbbreviation"), t.get("players") or []
                if not team or not ps:
                    continue
                st = [p for p in ps if p.get("position")]
                recent = [b for b in boxes.get(team, []) if b[1] < d and b[2] == season_of(d)][-USUAL_GAMES:]
                starts = defaultdict(int)
                for b in recent:
                    for pid, (s_, _) in b[3].items():
                        starts[pid] += s_
                usual = [pid for pid, n in sorted(starts.items(), key=lambda kv: -kv[1])[:5] if n] if len(recent) >= USUAL_MIN else []
                on = {int(p["personId"]) for p in st}
                name = {int(p["personId"]): p.get("playerName") or "" for p in ps}
                out[f"{d}|{team}"] = {
                    "status": "Confirmed" if st and all(p.get("lineupStatus") == "Confirmed" for p in st) else "Expected",
                    "at": max((p.get("timestamp") or "" for p in st), default="") or None,
                    "starters": [[int(p["personId"]), p.get("playerName") or "", p.get("position") or ""] for p in st],
                    "usual": usual,
                    "missing": [[pid, name[pid], (official.get((d, pid)) or {}).get("status")] for pid in usual
                                if pid not in on and pid in name],
                    "inactive": [[int(p["personId"]), p.get("playerName") or ""] for p in ps
                                 if p.get("rosterStatus") == "Inactive"]}
    return out


LINEUP_OUT = ("Out", "Doubtful")                 # a projected lineup leaves these out; Questionable / Probable are in


def projected_lineups(games, boxes, official, roster, posted):
    """{"date|TEAM": {status: "Projected", starters: [[pid, name, pos, report status]], subs: [[pid, for pid, for name]],
    usual: [pid], missing: [[pid, name, status]], inactive: []}} for each slate team with no posted lineup: its usual
    five (the most starts over its last USUAL_GAMES games this season, players on its roster now; USUAL_MIN games
    first) less anyone Out or Doubtful on the official report (Questionable and Probable players stay, their status
    shown). Each missing starter is replaced by whoever started most often in the team's games he did not start (this
    season and last, the seasons he was on the team), a player of his position first among equals, then the most starts
    and minutes lately; the surest replacement is placed first. Guards first, then forwards, then centers."""
    out = {}
    for g in games:
        d, season = g["date_et"], season_of(g["date_et"])
        for team in (g["away"], g["home"]):
            if f"{d}|{team}" in posted:
                continue
            seasonb = [b for b in boxes.get(team, []) if b[1] < d and b[2] == season]
            recent = seasonb[-USUAL_GAMES:]
            if len(recent) < USUAL_MIN:
                continue
            mine = {int(k) for k, v in roster.items() if v[0] == team}
            starts, mins = defaultdict(int), defaultdict(float)
            for b in recent:
                for pid, (st_, mn) in b[3].items():
                    if pid in mine:
                        starts[pid] += st_
                        mins[pid] += mn
            status = lambda pid: (official.get((d, pid)) or {}).get("status")
            ok = lambda pid: status(pid) not in LINEUP_OUT
            pos = lambda pid: (roster.get(str(pid)) or ["", "", ""])[2] or ""
            usual = [pid for pid, n in sorted(starts.items(), key=lambda kv: (-kv[1], -mins[kv[0]]))[:5] if n]
            five, subs, gone = [pid for pid in usual if ok(pid)], [], [u for u in usual if not ok(u)]
            when = {}                                        # for each missing starter: who started in the games he did not
            for u in gone:
                when[u] = defaultdict(int)
                his = {b[2] for b in boxes.get(team, []) if u in b[3]}           # the seasons he played for this team
                for b in boxes.get(team, []):
                    if b[1] < d and b[2] in his and not b[3].get(u, (0, 0))[0]:
                        for pid, (st_, _) in b[3].items():
                            when[u][pid] += st_
            grp = lambda pid: set(pos(pid).replace("-", "")) or {"F"}
            key = lambda u, pid: (when[u][pid], bool(grp(u) & grp(pid)), starts[pid], mins[pid])
            while gone:                                      # the surest replacement first, then the next
                cands = [pid for pid in mine if pid not in five and ok(pid)]
                if not cands:
                    break
                u, pick = max(((u, max(cands, key=lambda pid: key(u, pid))) for u in gone), key=lambda up: key(*up))
                gone.remove(u)
                five.append(pick)
                subs.append([pick, u, (roster.get(str(u)) or ["", ""])[1]])
            while len(five) < 5:                             # fewer than five usual starters yet: the most-used others
                cands = [pid for pid in mine if pid not in five and ok(pid)]
                if not cands:
                    break
                five.append(max(cands, key=lambda pid: (starts[pid], mins[pid])))
            five.sort(key=lambda pid: {"G": 0, "F": 1, "C": 2}.get(pos(pid)[:1], 1))
            out[f"{d}|{team}"] = {"status": "Projected", "at": None,
                                  "starters": [[pid, (roster.get(str(pid)) or ["", ""])[1], pos(pid), status(pid)] for pid in five],
                                  "subs": subs, "usual": usual,
                                  "missing": [[u, (roster.get(str(u)) or ["", ""])[1], status(u)] for u in usual if not ok(u)],
                                  "inactive": []}
    return out


def team_mates(boxes, roster):
    """{team: {"gids": [its games, oldest first], "mates": [{pid, name, since, on, mpg, gp}]}} — everyone on each
    team's roster now who has played for it in the cached seasons, the most minutes a game first. on: "1" / "0" per
    team game (he played / did not); since: his first game for the team. The prop page's With / Without filter."""
    out = {}
    for team, bs in boxes.items():
        mates = []
        for k, v in roster.items():
            pid = int(k)
            if v[0] != team:
                continue
            on = "".join("1" if pid in b[3] else "0" for b in bs)
            if "1" not in on:
                continue
            mins = [b[3][pid][1] for b in bs if pid in b[3]]
            mates.append({"pid": pid, "name": v[1], "since": bs[on.index("1")][1], "on": on,
                          "mpg": round(sum(mins) / len(mins), 1), "gp": len(mins)})
        out[team] = {"gids": [b[0] for b in bs], "mates": sorted(mates, key=lambda m: -m["mpg"])}
    return out


def _pos_set(pos):
    return set((pos or "").replace("-", ""))


def injury_report(mcon, official, teams_listed, report_meta, games, roster, seasons, boxes=None):
    """{"date|team": {"listed", "published", "players": [...]}} — every player on each slate team's latest official
    report (not Available), worst status then most minutes first: his minutes a game (this season, else last), whether
    he starts, fresh (he played in one of the team's last FRESH_GAMES games: news), and from the games he missed for the team (this season and last), the teammates who gained 2+ minutes a
    game and, for a starter, who started in his place. With no such games, the bench player at his position with the
    most minutes is named for the start (how = "position"). No read for a player without a game for the team (it has
    played without him all along) or a bench player who has missed more of its games than he played (the games he
    played are the odd ones). roster: {pid: [team, name, pos]} (the player index)."""
    season = seasons[-1]
    slate = sorted({(g["date_et"], t) for g in games for t in (g["home"], g["away"])})
    listed = defaultdict(list)
    for (d, pid), s in official.items():
        if s["status"] in INJ_ORDER and (d, s.get("team")) in teams_listed:
            listed[(d, s["team"])].append((pid, s))
    if boxes is None:
        boxes = team_boxes(mcon, sorted({t for _, t in slate}), seasons)
    apps = appearances(mcon, {pid for v in listed.values() for pid, _ in v}
                       | {int(k) for k, v in roster.items() if v[0] in {t for _, t in slate}}, seasons)
    name = lambda pid, s=None: (roster.get(str(pid)) or [None, None])[1] or (s or {}).get("player") or str(pid)

    def form(pid, team):                          # (mpg, games, season of them, starter) from his recent games
        rows = apps.get(pid, [])
        cur = [r for r in rows if r[1] == season]
        use = cur or [r for r in rows if r[1] != season]
        if not use:
            return None, 0, None, False
        recent = ([r for r in rows if r[2] == team] or rows)[-20:]
        return (round(sum(r[4] for r in use) / len(use), 1), len(use), use[-1][1],
                sum(r[3] for r in recent) >= len(recent) / 2)

    out = {}
    for d, team in slate:
        sick = {pid for pid, s in listed.get((d, team), []) if s["status"] in ("Out", "Doubtful")}
        mates = {int(k): v for k, v in roster.items() if v[0] == team and int(k) not in sick}
        last = [b for b in boxes.get(team, []) if b[1] < d][-FRESH_GAMES:]       # the team's last games before tonight
        players = []
        for pid, s in listed.get((d, team), []):
            mpg, gp, ssn, starter = form(pid, team)
            e = {"pid": pid, "name": name(pid, s), "pos": (roster.get(str(pid)) or ["", "", ""])[2] or "",
                 "status": s["status"], "reason": s.get("reason") or "", "mpg": mpg, "gp": gp, "season": ssn,
                 "starter": bool(starter), "missed": 0, "starts": None, "minutes": [],
                 "fresh": any(pid in b[3] for b in last)}
            if mpg is not None and mpg >= ROTATION_MPG:
                rows = apps.get(pid, [])
                stays = {}
                for sn in seasons:
                    in_s = [r for r in rows if r[1] == sn]
                    stays[sn] = (in_s[-1][2] == team) if in_s else (sn == season and bool(rows) and rows[-1][2] == team)
                played, missed, rd = depth_read(boxes.get(team, []), pid, [m for m in mates if m != pid], stays)
                e["missed"] = missed
                if not played:
                    rd = {}               # no game for this team yet: it has played without him all along
                elif not starter and played < missed:
                    rd = {}               # a bench player out more often than in: the games he played are the odd ones
                gains = []
                for y, (nw, no, mw, mo, sw, so) in rd.items():
                    if no >= MIN_WITHOUT and nw >= MIN_WITHOUT and mo / no - mw / nw >= MIN_GAIN:
                        gains.append({"pid": y, "name": name(y), "gain": round(mo / no - mw / nw, 1),
                                      "mpg": round(mo / no, 1), "n": no})
                e["minutes"] = sorted(gains, key=lambda g: -g["gain"])[:3]
                if starter and played:
                    best = max(((so / no - (sw / nw if nw else 0), y, so, no) for y, (nw, no, mw, mo, sw, so) in rd.items()
                                if no >= MIN_WITHOUT and nw >= MIN_WITHOUT and so / no >= .5 and sw / nw < .5), default=None)
                    if best:
                        e["starts"] = {"pid": best[1], "name": name(best[1]), "k": best[2], "n": best[3], "how": "games"}
                    else:
                        ps = _pos_set(e["pos"])
                        bench = [(form(y, team), y) for y, v in mates.items() if y != pid and _pos_set(v[2]) & ps]
                        bench = [(f[0], y) for f, y in bench if f[0] is not None and not f[3]]
                        if bench:
                            y = max(bench)[1]
                            e["starts"] = {"pid": y, "name": name(y), "k": None, "n": None, "how": "position"}
            players.append(e)
        players.sort(key=lambda e: (INJ_ORDER.index(e["status"]), -(e["mpg"] or 0)))
        out[f"{d}|{team}"] = {"listed": (d, team) in teams_listed, "published": (report_meta.get(d) or {}).get("published"),
                              "players": players}
    return out


def rank_tables(S, mcon, date):
    """Point-in-time ranks before `date` among the teams that have played: {"dvp": {group: {market: {team: rank}}},
    "def": {team: rank}, "teams": n}. rank 1 = the TOUGHEST defense (fewest allowed); the last = the softest. dvp = the
    stat allowed to a position group per possession (nba_matchup's factor); def = points allowed per possession."""
    teams = [t for t in S.by_team if S._team_before(t, date)[0]]
    out = {"dvp": {}, "def": {}, "teams": len(teams)}
    if not teams:
        return out
    lg = S._league_before(date)
    for g in ("G", "F", "C"):
        fac = {t: S.group_factors(t, date, g, lg) for t in teams}
        out["dvp"][g] = {m: _ranks({t: fac[t].get(k, 1.0) for t in teams}) for m, k in MATCHUP_KEY.items()}
    allowed, poss = defaultdict(float), defaultdict(float)
    for gid, d, home, away, hp, ap in mcon.execute("SELECT gid, date, home, away, home_pts, away_pts FROM games"):
        if d >= date or hp is None or gid not in S.games:
            continue
        for team, opp_pts in ((home, ap), (away, hp)):
            if (gid, team) in S.poss:
                allowed[team] += opp_pts
                poss[team] += S.poss[(gid, team)]
    out["def"] = _ranks({t: allowed[t] / poss[t] for t in teams if poss[t]})
    return out


BLEND_K = 15     # games: this season's defense counts as much as last season's after BLEND_K games


def rank_tables_blend(S, S_prev, mcon, date, k=BLEND_K):
    """rank_tables, with each team's this-season rate pulled toward ITS OWN last-season factor (not the league's)
    by k games: (n * rate + k * last-season factor * league rate) / (n + k). Early in a season the ranks are last
    season's; they turn into this season's as games are played. The audit (2026-10-26) found this season's ranks
    on 1-2 games carried no signal and last season's did. {"dvp", "def", "teams", "n": {team: games}}."""
    out = {"dvp": {}, "def": {}, "teams": 0, "n": {}}
    if S is None or S_prev is None:
        return out
    teams = sorted(set(S.by_team) | set(S_prev.by_team))
    out["teams"] = len(teams)
    lg, lg_p = S._league_before(date), S_prev._league_before("9999-12-31")
    n_of = {t: (S._team_before(t, date)[0] if t in S.by_team else 0) for t in teams}
    out["n"] = n_of
    for g in ("G", "F", "C"):
        prev = {t: S_prev.group_factors(t, "9999-12-31", g, lg_p) for t in teams}
        cur = {}
        for t in teams:
            n, poss, tot = S._team_before(t, date) if t in S.by_team else (0, 0, {})
            f = {}
            for st_, parts in MU_STATS().items():
                lg_r = sum((lg[2] if lg else {}).get((g, p_), 0.0) for p_ in parts) if lg else 0.0
                pf = prev[t].get(st_, 1.0)
                if n and poss and lg_r > 0:
                    r = sum(tot.get((g, p_), 0.0) for p_ in parts) / poss
                    f[st_] = (n * r + k * pf * lg_r) / (n + k) / lg_r
                else:
                    f[st_] = pf
            cur[t] = f
        out["dvp"][g] = {m: _ranks({t: cur[t].get(key, 1.0) for t in teams}) for m, key in MATCHUP_KEY.items()}
    scores = {gid: (hp, ap) for gid, hp, ap in mcon.execute("SELECT gid, home_pts, away_pts FROM games")}

    def ppp(Sx, d):                                    # points allowed per possession / the league's, before d
        a, p_ = defaultdict(float), defaultdict(float)
        for gid, (gd, home, away) in Sx.games.items():
            hp, ap = scores.get(gid, (None, None))
            if gd >= d or hp is None:
                continue
            for team, opp_pts in ((home, ap), (away, hp)):
                if (gid, team) in Sx.poss:
                    a[team] += opp_pts
                    p_[team] += Sx.poss[(gid, team)]
        lgv = sum(a.values()) / sum(p_.values()) if sum(p_.values()) else None
        return {t: a[t] / p_[t] / lgv for t in a if p_[t] and lgv}, a, p_
    cur_r, prev_r = ppp(S, date)[0], ppp(S_prev, "9999-12-31")[0]
    out["def"] = _ranks({t: (n_of[t] * cur_r.get(t, 1.0) + k * prev_r.get(t, 1.0)) / (n_of[t] + k) for t in teams})
    return out


def MU_STATS():
    import nba_matchup as MU
    return MU.STATS


def _ranks(vals):
    """{team: value} -> {team: rank}, 1 = the smallest value (fewest allowed)."""
    order = sorted(vals, key=lambda t: (vals[t], t))
    return {t: i + 1 for i, t in enumerate(order)}


def positions(mcon, pids, seasons, idx_pos):
    """{pid: position code} — his most frequent starting position (box scores), else the index's ("F", "G-F")."""
    out = {}
    if mcon is not None and pids:
        marks = ",".join("?" * len(pids))
        for pid, pos, n in mcon.execute(
                f"SELECT p.pid, p.pos, COUNT(*) FROM player_games p JOIN games g ON g.gid = p.gid WHERE p.starter = 1 "
                f"AND p.pos != '' AND p.pid IN ({marks}) AND g.season IN ({','.join('?' * len(seasons))}) "
                f"GROUP BY p.pid, p.pos ORDER BY 3 DESC", list(pids) + list(seasons)):
            out.setdefault(pid, pos)
    for pid in pids:
        out.setdefault(pid, idx_pos.get(pid) or "")
    return out


def pos_ranks(mcon, season, idx_pos, min_games=3):
    """{group: {market: [(per-game avg, pid)] best first}} for one season: every player with >= min_games, grouped
    by his most frequent starting position (else the index's). The page ranks a player within his group."""
    import nba_matchup as MU
    tot, n, starts = defaultdict(lambda: defaultdict(float)), defaultdict(int), defaultdict(lambda: defaultdict(int))
    for pid, pos, st_, pts, reb, ast, fg3m in mcon.execute(
            "SELECT p.pid, p.pos, p.starter, p.pts, p.reb, p.ast, p.fg3m FROM player_games p JOIN games g ON g.gid = p.gid "
            "WHERE g.season = ?", (season,)):
        n[pid] += 1
        for k, v in (("pts", pts), ("reb", reb), ("ast", ast), ("fg3m", fg3m)):
            tot[pid][k] += v or 0
        if st_ and MU.GROUP.get(pos):
            starts[pid][MU.GROUP[pos]] += 1
    out = defaultdict(lambda: defaultdict(list))
    for pid, games in n.items():
        if games < min_games:
            continue
        grp = max(starts[pid], key=starts[pid].get) if starts[pid] else MU.GROUP.get((idx_pos.get(pid) or "")[:1])
        if not grp:
            continue
        for m, (_, parts) in MARKETS.items():
            out[grp][m].append((round(sum(tot[pid][k] for k in parts) / games, 2), pid))
    for g in out.values():
        for m in g:
            g[m].sort(key=lambda x: (-x[0], x[1]))
    return out


def correlations(props, logs):
    """For each prop: the other props posted for the same game, ranked by |Pearson r| of the two stats over the
    games both players played for the same team (same player: every game). Historical association only."""
    series = {}                                       # prop id -> {gid: (team, value)}, computed once per prop
    for p in props:
        series[p["id"]] = {r[1]: (r[2], stat_value(dict(zip(LOG_COLS, r)), p["market"])) for r in logs.get(p["pid"], [])}
    by_game = defaultdict(list)
    for p in props:
        by_game[p["gid"]].append(p)
    out, pair = {}, {}                                # pair: (n, r) of each pair once (r is symmetric); the team too,
                                                      # as the shared games are the ones played for it
    for p in props:
        mine = series[p["id"]]
        res = []
        for o in by_game[p["gid"]]:
            if o["id"] == p["id"] or (o["pid"] == p["pid"] and o["market"] == p["market"]):
                continue
            if o["pid"] != p["pid"] and o["team"] != p["team"]:
                continue                                   # same team only: shared games mean the same games
            k = (p["id"], o["id"], p["team"]) if p["id"] < o["id"] else (o["id"], p["id"], p["team"])
            if k not in pair:
                theirs = series[o["id"]]
                shared = [g for g in mine.keys() & theirs.keys() if mine[g][0] == theirs[g][0] == p["team"]]
                pair[k] = (len(shared), pearson([mine[g][1] for g in shared], [theirs[g][1] for g in shared])
                           if len(shared) >= CORR_MIN_N else None)
            n, r = pair[k]
            if r is not None:
                res.append({"id": o["id"], "r": round(r, 2), "n": n})
        out[p["id"]] = sorted(res, key=lambda x: (-abs(x["r"]), x["id"]))[:CORR_TOP]
    return out


# ── the payload ──────────────────────────────────────────────────────────────────────────────────────────
def build(now=None, sched=None, lines=None, news=None, shadow=None, matchup=None, index=None, box_get=None, tracking=None,
          lineups_db=None, role_db=None):
    import nba_matchup as MU
    now = now or dt.datetime.now(dt.timezone.utc)
    if sched is None:
        import nba_rosters as R
        sched = R.schedule()
    base = (now.astimezone(ET) - dt.timedelta(hours=SLATE_ROLL_H)).date()
    day = lambda k: (base + dt.timedelta(days=k)).isoformat()
    cand = [g for g in sched if g["date_et"] in (day(0), day(1), day(2))]
    live = live_state(cand, get=box_get, now=now)
    # a slate leaves the moment its last game is final (or postponed): the SLATE_ROLL_H hold only keeps a late game on
    # while it is being played, and the next slate (and the one after) takes its place
    first = [g for g in cand if g["date_et"] == day(0)]
    k0 = 1 if first and all(live[g["gid"]]["state"] in ("final", "postponed") for g in first) else 0
    dates = [day(k0), day(k0 + 1)]
    games = [g for g in cand if g["date_et"] in dates]
    gids = [g["gid"] for g in games]
    q, ncon, sh = _ro(lines or LINES), _ro(news or NEWS), _ro(shadow or SHADOW)
    mpath = Path(matchup or MU.DB)
    mcon = MU.connect(mpath) if mpath.exists() else None
    try:
        idx = json.loads(Path(index or INDEX).read_text()).get("players", {})
    except (OSError, ValueError):
        idx = {}
    pos = {int(k): v[2] for k, v in idx.items()}
    team_of = {int(k): v[0] for k, v in idx.items()}

    quotes, names, newest = book_quotes(q, gids)
    spots = schedule_spots(sched, gids)
    # games under way: their props come off the board at tip; their closing boards fill in, marked closed (Live tab only)
    started = [g["gid"] for g in games if g.get("utc") and _naive_utc(g["utc"]) <= now.astimezone(dt.timezone.utc).replace(tzinfo=None)]
    cb, cnames = closing_boards(q, started, cache=CLOSE_BOARDS if lines is None else Path(lines).with_name("close_boards.json"))
    closed = set()
    for k, books in cb.items():
        if k not in quotes:
            quotes[k] = books
            closed.add(k)
    for k, n in cnames.items():
        names.setdefault(k, n)
    hist = line_history(q, gids)
    # the line history goes out compact: minutes since the slate's first quote (hist_t0) and prices to 3 places; as
    # ISO strings it was two thirds of every prop (45,000 points a slate)
    t0 = min((pts[0][0] for h in hist.values() for pts in h.values() if pts), default=None)
    t0 = dt.datetime.fromisoformat(t0).replace(second=0, microsecond=0) if t0 else None
    _hmin = lambda s_: int((dt.datetime.fromisoformat(s_) - t0).total_seconds() // 60)
    gmap = {g["gid"]: g for g in games}
    props = []
    for (gid, pid, market), books in sorted(quotes.items()):
        g = gmap[gid]
        team = team_of.get(pid)
        if team not in (g["home"], g["away"]):
            team = None
        props.append({"id": f"{gid}|{pid}|{market}", "gid": gid, "pid": pid, "market": market,
                      "player": names.get((gid, pid), ""), "team": team,
                      "opp": (g["away"] if team == g["home"] else g["home"]) if team else None,
                      "home": team == g["home"] if team else None, "books": books,
                      "main": (books.get("fd") or {}).get("main") or (books.get("dk") or {}).get("main"),
                      **({"closed": True} if (gid, pid, market) in closed else {})})
    season = season_of(dates[0])
    pids = {p["pid"] for p in props}
    trk = _ro(tracking or TRACKING)
    lcon = _ro(lineups_db or LINEUPS)
    logs = game_logs(mcon, pids, (prev_season(season), season), trk)
    for p in props:                                     # a player with no index entry: his latest box team
        if p["team"] is None and logs.get(p["pid"]):
            t = logs[p["pid"]][-1][2]
            g = gmap[p["gid"]]
            if t in (g["home"], g["away"]):
                p.update(team=t, opp=g["away"] if t == g["home"] else g["home"], home=t == g["home"])
    official, teams_listed, report_meta = official_status(ncon, dates)
    news_by = news_items(ncon, dates)
    flags = engine_flags(sh, dates)
    rflags = under_flags(_ro(role_db or ROLE), dates)
    for f in rflags:
        f["team"] = team_of.get(f["pid"])
    glines = game_lines(q, gids)
    # matchup context: point-in-time factors for this season (nba_matchup), per prop
    S = MU.Season(mcon, season, index_pos=pos) if mcon is not None else None
    S_prev = MU.Season(mcon, prev_season(season), index_pos=pos) if mcon is not None else None
    # rank tables: this season as of each slate date, blended with last season (rank_tables_blend); last season as
    # it finished (for filtering last season's games by the tier their opponent was in)
    ranks = {}
    if S is not None:
        for d in dates:
            ranks[d] = rank_tables_blend(S, S_prev, mcon, d)
        ranks[prev_season(season)] = rank_tables(S_prev, mcon, "9999-12-31")
    pcodes = positions(mcon, list(pids), (prev_season(season), season), pos)
    pr_cur = pos_ranks(mcon, season, pos) if mcon is not None else {}
    pr_prev = pos_ranks(mcon, prev_season(season), pos) if mcon is not None else {}
    paces = {}                                           # date -> {team: pace factor}; pace does not depend on B
    for p in props:
        g = gmap[p["gid"]]
        ctx = {"group": None, "pace": None, "def": None, "opp_games": 0, "pace_rank": None, "dvp_rank": None,
               "def_rank": None, "teams": 0, "pos": pcodes.get(p["pid"], ""), "pos_rank": None, "pos_n": 0,
               "pos_season": None}
        if S is not None and p["opp"]:
            pace, mf = S.factors(p["opp"], g["date_et"], p["pid"])
            n_opp = S._team_before(p["opp"], g["date_et"])[0] if p["opp"] in S.by_team else 0
            grp = S.group(p["pid"], g["date_et"])
            ctx.update(group=grp, pace=round(pace, 3), opp_games=n_opp,
                       **({"def": round(mf.get(MATCHUP_KEY[p["market"]], 1.0), 3)} if p["market"] in MATCHUP_KEY else {}))
            rt = ranks.get(g["date_et"]) or {}
            if rt.get("teams"):
                ctx["teams"] = rt["teams"]
                ctx["rank_n"] = (rt.get("n") or {}).get(p["opp"], n_opp)          # this season's games in the blend
                if g["date_et"] not in paces:                  # this season only (pace has no blend yet)
                    paces[g["date_et"]] = {t: S.factors(t, g["date_et"], p["pid"])[0] for t in rt["def"] if t in S.by_team}
                ctx["pace_rank"] = 1 + sum(1 for t, v in paces[g["date_et"]].items() if v > pace) if n_opp else None
                ctx["def_rank"] = rt["def"].get(p["opp"])                                 # 1 = the toughest
                if grp and p["market"] in MATCHUP_KEY:
                    ctx["dvp_rank"] = rt["dvp"][grp][p["market"]].get(p["opp"])
        grp_b = MU.GROUP.get(ctx["pos"]) or MU.GROUP.get((ctx["pos"] or "")[:1])
        for label, table in ((season, pr_cur), (prev_season(season), pr_prev)):        # his rank among his position
            lst = (table.get(grp_b) or {}).get(p["market"]) or []
            at = next((i for i, (_, pid_) in enumerate(lst) if pid_ == p["pid"]), None)
            if at is not None:
                ctx.update(pos_rank=at + 1, pos_n=len(lst), pos_season=label)
                break
        p["ctx"] = ctx
        p["flag"] = flags.get((p["gid"], p["pid"], p["market"]))
        lv = live.get(p["gid"], {})
        if lv.get("state") in ("live", "final") and p["pid"] in lv.get("stats", {}):
            s_ = lv["stats"][p["pid"]]
            p["live"] = {"value": stat_value(s_, p["market"]), "min": s_["min"]}
        main = p["main"]
        mylogs = [dict(zip(LOG_COLS, r)) for r in logs.get(p["pid"], [])]   # every game, any team (as the page)
        vals = [stat_value(r, p["market"]) for r in mylogs]
        cur = [stat_value(r, p["market"]) for r in mylogs if season_of(r["date"]) == season]
        p["summary"] = None if main is None else {
            "l5": hit_summary(vals[-5:], main), "l10": hit_summary(vals[-10:], main),
            "l20": hit_summary(vals[-20:], main), "season": hit_summary(cur, main)}
        h = hist.get((p["gid"], p["pid"], p["market"]), {})
        p["hist"] = {b: [[_hmin(x[0]), x[1], _r3(x[2]), _r3(x[3])] for x in pts] for b, pts in h.items()}
        fd0 = (h.get("fd") or [None])[0]
        p["open"] = [fd0[1], fd0[2], fd0[0]] if fd0 else None
    # 'without' splits: every team's absences for its game date
    by_team = defaultdict(lambda: defaultdict(list))
    absent_pids = {pid for (d, pid), s in official.items() if s["status"] in ("Out", "Doubtful")}
    for pid, rows in game_logs(mcon, absent_pids, (prev_season(season), season)).items():
        for r in rows:
            by_team[pid][r[2]].append(r)
    team_last = defaultdict(list)                       # each team's last FRESH_GAMES finals before the slate
    if mcon is not None:
        for gid, d, h, a in mcon.execute("SELECT gid, date, home, away FROM games WHERE home_pts IS NOT NULL AND date < ? "
                                         "ORDER BY date", (dates[0],)):
            for t in (h, a):
                team_last[t] = (team_last[t] + [gid])[-FRESH_GAMES:]
    absent = absences(official, by_team, dates, team_last)
    both = (prev_season(season), season)
    boxes = team_boxes(mcon, sorted({t for g in games for t in (g["home"], g["away"])}), both)
    inj_report = injury_report(mcon, official, teams_listed, report_meta, games, idx, both, boxes=boxes)
    corr = correlations(props, logs)
    players = {}
    for pid in pids:
        players[pid] = {"name": next((p["player"] for p in props if p["pid"] == pid), ""), "pos": pos.get(pid) or "",
                        "logs": logs.get(pid, [])}
    injuries = {}
    for p in props:
        d = gmap[p["gid"]]["date_et"]
        o = official.get((d, p["pid"]))
        injuries[f"{d}|{p['pid']}"] = {
            "official": o, "listed_team": bool(teams_listed.get((d, p["team"]))) if p["team"] else False,
            "news": news_by.get((d, p["pid"]), [])}
    # the projection engine (nba_project, NBA_PROJECTION_PREREG.md): model estimates beside the book prices,
    # never a pick; on any failure the props carry no projection and proj_meta says why
    try:
        import nba_project as NPJ
        proj, proj_players, proj_meta = NPJ.for_payload(props, games, now,
                                                         log_db=PROJ_LOG if q is not None and lines is None else None)
    except Exception as e:                                                   # noqa: BLE001
        proj, proj_players, proj_meta = {}, {}, {"error": f"projection unavailable ({type(e).__name__})"}
    for p in props:
        p["proj"] = proj.get(p["id"])
    stamp = now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    fresh = {}
    for b, at in newest.items():
        age = (now.astimezone(dt.timezone.utc).replace(tzinfo=None) - _naive_utc(at)).total_seconds() / 60
        fresh[b] = {"updated": at, "age_min": round(age, 1), "stale": age > BOOK_STALE_MIN}
    # NBA.com's posted lineups, and a projected five for every slate team still without one
    lu = lineups(lcon, dates, boxes, official)
    lu.update(projected_lineups(games, boxes, official, idx, lu))
    out = {
        "generated_at": stamp, "season": season, "dates": dates, "log_cols": list(LOG_COLS),
        "hist_t0": t0.isoformat() if t0 else None,
        "markets": {k: v[0] for k, v in MARKETS.items()},
        "sources": {"books": fresh, "report": report_meta,
                    "logs": {"through": max((r[0] for v in logs.values() for r in v), default=None),
                             "seasons": [prev_season(season), season]},
                    "matchup": {"available": S is not None},
                    "game_lines": {"games": len(glines)}},
        "games": [{"gid": g["gid"], "date": g["date_et"], "tip": g["utc"], "away": g["away"], "home": g["home"],
                   "lines": glines.get(g["gid"]), "spots": spots.get(g["gid"]),
                   **{k: v for k, v in live.get(g["gid"], {}).items() if k != "stats"}}
                  for g in sorted(games, key=lambda g: g["utc"])],
        "props": props, "players": {str(k): v for k, v in players.items()}, "injuries": injuries,
        "flags": rflags,
        "absences": {f"{d}|{t}": [dict(a, name=next((n for (gg, pp), n in names.items() if pp == a["pid"]), None)
                                       or (idx.get(str(a["pid"])) or [None, None])[1]) for a in v]
                     for (d, t), v in absent.items()},
        "related": corr,
        "inj_report": inj_report,
        "mates": team_mates(boxes, idx),
        "lineups": lu,
        # past games are filtered by the tier their opponent sits in (DvP / Def Rank chips): this season's ranks
        # as of the slate date, last season's as it finished
        "ranks": {k: v for k, v in ranks.items()},
        "proj_players": proj_players, "proj_meta": proj_meta,
    }
    for c in (q, ncon, sh, mcon, trk, lcon):
        if c is not None:
            c.close()
    return out


def write(out_dir, payload):
    """Atomic writes of nba_props.json and nba_props.html (the board server serves docs/ as is)."""
    import nba_research_ui as UI
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (("nba_props.json", json.dumps(payload, separators=(",", ":"), default=str)),
                       ("nba_props.html", UI.page())):
        tmp = out_dir / f".{name}.tmp"
        tmp.write_text(body)
        os.replace(tmp, out_dir / name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("NBA_RESEARCH_OUT", str(HERE / "docs")))
    a = ap.parse_args()
    pl = build()
    write(a.out, pl)
    print(f"nba_research: {len(pl['props'])} props · {len(pl['games'])} games · {len(pl['players'])} players -> {a.out}")
