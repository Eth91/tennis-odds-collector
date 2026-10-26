#!/usr/bin/env python3
"""NBA prop research for Pickz: the data behind docs/nba_props.html (the page itself is nba_research_ui.py).

From the slate to one prop: every player prop FanDuel and DraftKings post (nba_lines.board, with alternate rungs),
the player's game logs (this season and last, nba_matchup.sqlite box scores), the official injury report and the
news items the engine stores (kept apart, each with its time), matchup context (nba_matchup's point-in-time pace
and defense-vs-position factors; FanDuel's spread and total), historical association with the other props posted
for the same game, the line's movement since FanDuel opened it, the engine's own shadow flags, and live box
scores for games in progress. Everything is descriptive. Nothing here is a projection or a bet.

Read-only over the engine's stores; the output is one JSON file the page fetches.

LIMITS (shown on the page where they apply):
  books     FanDuel and DraftKings only (nba_lines). Markets: points, rebounds, assists, threes, PRA, P+R, P+A, R+A —
            what those feeds carry. No steals / blocks / turnovers props are collected, so none are listed.
  freshness each book's board refreshes about every 10 min (every 2 near tip); older than BOOK_STALE_MIN = "stale".
            The page is rebuilt every 2 min on the VM (cron); live box scores are fetched at each rebuild.
  logs      regular-season box scores, this season and last (nba_matchup.sqlite). No playoff games.
  matchup   season-to-date only (none until the opponent has played); no factor for threes.
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
import sqlite3
import statistics as st
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
LINES, NEWS, SHADOW = HERE / "nba_lines.sqlite", HERE / "nba_news.sqlite", HERE / "nba_shadow.sqlite"
INDEX = HERE / "nba_player_index.json"
ET, MT = ZoneInfo("America/New_York"), ZoneInfo("America/Denver")
# market -> (label, box-score parts). Only the markets the books' feeds carry (nba_lines.STAT_MAP).
MARKETS = {"points": ("PTS", ("pts",)), "rebounds": ("REB", ("reb",)), "assists": ("AST", ("ast",)),
           "threes": ("3PM", ("fg3m",)), "pra": ("PRA", ("pts", "reb", "ast")), "pts_reb": ("P+R", ("pts", "reb")),
           "pts_ast": ("P+A", ("pts", "ast")), "reb_ast": ("R+A", ("reb", "ast"))}
MATCHUP_KEY = {"points": "pts", "rebounds": "reb", "assists": "ast", "pra": "pra", "pts_reb": "pts_reb",
               "pts_ast": "pts_ast", "reb_ast": "reb_ast"}           # threes: no matchup factor is computed
LOG_COLS = ("date", "gid", "team", "opp", "home", "starter", "min", "pts", "reb", "ast", "fg3m")
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
    if len(pairs) < 3:
        return None
    mx = sum(x for x, _ in pairs) / len(pairs)
    my = sum(y for _, y in pairs) / len(pairs)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def main_line(rungs):
    """The book's main rung: two-sided, over price nearest even money (the engine's rule). rungs: [[line, o, u]]."""
    two = [r for r in rungs if r[1] and r[2]]
    return min(two, key=lambda r: abs(r[1] - EVEN))[0] if two else None


# ── sources ──────────────────────────────────────────────────────────────────────────────────────────────
def _ro(path):
    path = Path(path)
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True) if path.exists() else None


def book_quotes(q, gids):
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
        if stat not in MARKETS or odds is None:
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


def opening(q, gid, pid, market):
    """FanDuel's first main rung for this prop in the change log: (line, over, seen_at) or None."""
    import nba_reaction as RX
    rows = q.execute("SELECT seen_at, line, side, odds FROM quotes WHERE book='fd' AND gid=? AND pid=? AND stat=?",
                     (gid, pid, market)).fetchall()
    for t, m in RX.timeline(rows):
        if m:
            return [m[0], round(m[1], 4), t]
    return None


def game_logs(mcon, pids, seasons):
    """{pid: [log rows in LOG_COLS order]} from the cached box scores, oldest first."""
    out = defaultdict(list)
    if mcon is None or not pids:
        return out
    pids = list(pids)
    for i in range(0, len(pids), 400):
        chunk = pids[i:i + 400]
        q = ("SELECT p.pid, g.date, p.gid, p.team, CASE WHEN p.team = g.home THEN g.away ELSE g.home END, "
             "CASE WHEN p.team = g.home THEN 1 ELSE 0 END, p.starter, p.min, p.pts, p.reb, p.ast, p.fg3m "
             f"FROM player_games p JOIN games g ON g.gid = p.gid WHERE p.pid IN ({','.join('?' * len(chunk))}) "
             f"AND g.season IN ({','.join('?' * len(seasons))}) ORDER BY g.date, p.gid")
        for r in mcon.execute(q, chunk + list(seasons)):
            row = list(r[1:])
            row[6] = round(row[6] or 0, 1)
            out[r[0]].append(row)
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
                status[(d, int(pid))] = {"status": st_, "reason": (reason or "")[:80], "published": pub, "team": team}
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


def absences(official, logs_by_team, game_dates):
    """{(date, team): [{pid, name, status, played: [gids], since}]} — tonight's Out/Doubtful players with >= 10
    games and >= 20 minutes a game for the team in the cached logs (the 'without' split)."""
    out = defaultdict(list)
    for (d, pid), s in official.items():
        if s["status"] not in ("Out", "Doubtful"):
            continue
        for team, rows in logs_by_team.get(pid, {}).items():
            if team != s.get("team"):
                continue                                   # the team the report lists him on, not a former one
            if len(rows) >= 10 and sum(r[6] for r in rows) / len(rows) >= 20:
                out[(d, team)].append({"pid": pid, "status": s["status"], "played": [r[1] for r in rows],
                                       "since": rows[0][0]})
    return out


def correlations(props, logs):
    """For each prop: the other props posted for the same game, ranked by |Pearson r| of the two stats over the
    games both players played for the same team (same player: every game). Historical association only."""
    idx = {}
    for p in props:
        lg = {r[1]: dict(zip(LOG_COLS, r)) for r in logs.get(p["pid"], [])}
        idx[p["id"]] = lg
    by_game = defaultdict(list)
    for p in props:
        by_game[p["gid"]].append(p)
    out = {}
    for p in props:
        mine = idx[p["id"]]
        res = []
        for o in by_game[p["gid"]]:
            if o["id"] == p["id"] or (o["pid"] == p["pid"] and o["market"] == p["market"]):
                continue
            if o["pid"] != p["pid"] and o["team"] != p["team"]:
                continue                                   # same team only: shared games mean the same games
            theirs = idx[o["id"]]
            shared = [g for g in mine if g in theirs and mine[g]["team"] == theirs[g]["team"] == p["team"]]
            if len(shared) < CORR_MIN_N:
                continue
            r = pearson([stat_value(mine[g], p["market"]) for g in shared],
                        [stat_value(theirs[g], o["market"]) for g in shared])
            if r is not None:
                res.append({"id": o["id"], "r": round(r, 2), "n": len(shared)})
        out[p["id"]] = sorted(res, key=lambda x: -abs(x["r"]))[:CORR_TOP]
    return out


# ── the payload ──────────────────────────────────────────────────────────────────────────────────────────
def build(now=None, sched=None, lines=None, news=None, shadow=None, matchup=None, index=None, box_get=None):
    import nba_matchup as MU
    now = now or dt.datetime.now(dt.timezone.utc)
    if sched is None:
        import nba_rosters as R
        sched = R.schedule()
    today = now.astimezone(ET).date()
    dates = [(today + dt.timedelta(days=k)).isoformat() for k in (0, 1)]
    games = [g for g in sched if g["date_et"] in dates]
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
                      "main": (books.get("fd") or {}).get("main") or (books.get("dk") or {}).get("main")})
    season = season_of(dates[0])
    pids = {p["pid"] for p in props}
    logs = game_logs(mcon, pids, (prev_season(season), season))
    for p in props:                                     # a player with no index entry: his latest box team
        if p["team"] is None and logs.get(p["pid"]):
            t = logs[p["pid"]][-1][2]
            g = gmap[p["gid"]]
            if t in (g["home"], g["away"]):
                p.update(team=t, opp=g["away"] if t == g["home"] else g["home"], home=t == g["home"])
    official, teams_listed, report_meta = official_status(ncon, dates)
    news_by = news_items(ncon, dates)
    flags = engine_flags(sh, dates)
    glines = game_lines(q, gids)
    live = live_state(games, get=box_get, now=now)
    # matchup context: point-in-time factors for this season (nba_matchup), per prop
    S = MU.Season(mcon, season, index_pos=pos) if mcon is not None else None
    for p in props:
        g = gmap[p["gid"]]
        ctx = {"group": None, "pace": None, "def": None, "opp_games": 0}
        if S is not None and p["opp"]:
            pace, mf = S.factors(p["opp"], g["date_et"], p["pid"])
            n_opp = S._team_before(p["opp"], g["date_et"])[0] if p["opp"] in S.by_team else 0
            ctx.update(group=S.group(p["pid"], g["date_et"]), pace=round(pace, 3), opp_games=n_opp,
                       **({"def": round(mf.get(MATCHUP_KEY[p["market"]], 1.0), 3)} if p["market"] in MATCHUP_KEY else {}))
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
        if q is not None:
            p["open"] = opening(q, p["gid"], p["pid"], p["market"])
    # 'without' splits: every team's absences for its game date
    by_team = defaultdict(lambda: defaultdict(list))
    absent_pids = {pid for (d, pid), s in official.items() if s["status"] in ("Out", "Doubtful")}
    for pid, rows in game_logs(mcon, absent_pids, (prev_season(season), season)).items():
        for r in rows:
            by_team[pid][r[2]].append(r)
    absent = absences(official, by_team, dates)
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
    stamp = now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    fresh = {}
    for b, at in newest.items():
        age = (now.astimezone(dt.timezone.utc).replace(tzinfo=None) - _naive_utc(at)).total_seconds() / 60
        fresh[b] = {"updated": at, "age_min": round(age, 1), "stale": age > BOOK_STALE_MIN}
    out = {
        "generated_at": stamp, "season": season, "dates": dates, "log_cols": list(LOG_COLS),
        "markets": {k: v[0] for k, v in MARKETS.items()},
        "sources": {"books": fresh, "report": report_meta,
                    "logs": {"through": max((r[0] for v in logs.values() for r in v), default=None),
                             "seasons": [prev_season(season), season]},
                    "matchup": {"available": S is not None},
                    "game_lines": {"games": len(glines)}},
        "games": [{"gid": g["gid"], "date": g["date_et"], "tip": g["utc"], "away": g["away"], "home": g["home"],
                   "lines": glines.get(g["gid"]), **{k: v for k, v in live.get(g["gid"], {}).items() if k != "stats"}}
                  for g in sorted(games, key=lambda g: g["utc"])],
        "props": props, "players": {str(k): v for k, v in players.items()}, "injuries": injuries,
        "absences": {f"{d}|{t}": [dict(a, name=next((n for (gg, pp), n in names.items() if pp == a["pid"]), None)
                                       or (idx.get(str(a["pid"])) or [None, None])[1]) for a in v]
                     for (d, t), v in absent.items()},
        "related": corr,
    }
    for c in (q, ncon, sh, mcon):
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
