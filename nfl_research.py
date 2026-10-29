#!/usr/bin/env python3
"""NFL prop research for Pickz: the data behind the NFL side of docs/nba_props.html (nfl_props.json; the page is
nba_research_ui.py, the same page as the NBA's, switched by the league button).

The same shape as nba_research's payload, so the page reads both the same way: the week's games, every player prop
FanDuel and DraftKings post (nfl_lines.sqlite, alternate rungs included) with each book's line history, the fair price
and how far the best price beats it; each player's game logs this season and last (nfl_stats.sqlite: the box score,
snaps, target share, air yards, red-zone looks, longest plays); the injury report (nflverse's official report and
practice participation, ESPN's statuses and news notes); matchup context (defense vs position by market, the opponent's
points allowed and pace); ESPN's depth charts; live box scores for games under way. And what football adds: where a
back's carries go and what the defense allows there, a receiver's target tree, each team's share of its targets and
carries, and whose volume moved over the last three games. Everything is descriptive or a market estimate: nothing here
is a projection or a pick.

LIMITS
  books     FanDuel and DraftKings only (nfl_lines). DraftKings arrives as a snapshot (it blocks this box).
  logs      regular season and playoffs, this season and last (nflverse; a game lands the morning after it is played).
  injuries  the official report as nflverse stores it (Wednesday to Saturday), ESPN's list for the days between.

    python3 nfl_research.py --out /home/ubuntu/tennis-odds-collector/docs    # writes nfl_props.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import statistics as st
import urllib.request
from collections import defaultdict
from pathlib import Path

import nfl_common as C
import nba_research as NR

HERE = Path(__file__).resolve().parent
LINES = Path(os.environ.get("NFL_LINES_DB", HERE / "nfl_lines.sqlite"))
STATS = Path(os.environ.get("NFL_STATS_DB", HERE / "nfl_stats.sqlite"))
CLOSE_BOARDS = HERE / "nfl_close_boards.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
# market -> (label, log columns summed). The books' NFL player props (nfl_lines' stat keys)
MARKETS = {"pass_yds": ("PASS YDS", ("pass_yds",)), "pass_tds": ("PASS TD", ("pass_tds",)), "pass_att": ("ATT", ("pass_att",)),
           "pass_comp": ("COMP", ("pass_comp",)), "pass_int": ("INT", ("pass_int",)), "long_comp": ("LONG CMP", ("long_comp",)),
           "rush_yds": ("RUSH YDS", ("rush_yds",)), "rush_att": ("CARRIES", ("rush_att",)), "long_rush": ("LONG RUSH", ("long_rush",)),
           "rec": ("REC", ("rec",)), "rec_yds": ("REC YDS", ("rec_yds",)), "long_rec": ("LONG REC", ("long_rec",)),
           "rush_rec_yds": ("RUSH+REC", ("rush_yds", "rec_yds")), "pass_rush_yds": ("PASS+RUSH", ("pass_yds", "rush_yds")),
           "anytime_td": ("TD", ("td",)), "kick_pts": ("KICK PTS", ("kick_pts",)), "fg_made": ("FG", ("fg_made",)),
           "sacks": ("SACKS", ("sacks",))}
ONE_SIDED = ("anytime_td", "sacks")          # yes-only markets: the 0.5 rung is the line
LOG_COLS = None                              # nfl_stats.LOG_COLS, bound on import below
# defense vs position: the groups and the markets each is ranked in (what the defense allowed that group a game)
GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE", "K": "K"}
DVP_MARKETS = {"QB": ("pass_yds", "pass_tds", "pass_att", "pass_comp", "pass_int", "long_comp", "rush_yds", "rush_att",
                      "pass_rush_yds", "anytime_td"),
               "RB": ("rush_yds", "rush_att", "long_rush", "rec", "rec_yds", "long_rec", "rush_rec_yds", "anytime_td"),
               "WR": ("rec", "rec_yds", "long_rec", "rush_rec_yds", "anytime_td"),
               "TE": ("rec", "rec_yds", "long_rec", "rush_rec_yds", "anytime_td"),
               "K": ("kick_pts", "fg_made")}
MAX_OF = {"long_comp", "long_rush", "long_rec"}         # a group's longest play in a game is its best one, not a sum
RANK_MIN = 3                 # a team ranks once it has this many games this season (else last season's rank stands in)
FRESH_GAMES = 2              # an absence is news while he played in one of his team's last 2 games
ROT_SNAP = 30                # a listed player under 30% of the snaps gets no replacement read
MIN_WITHOUT = 2              # team games without him before a teammate's gain in them is read
MIN_GAIN = 1.5               # targets + carries a game a teammate must gain without him to be named
OUT_LIKE = {"Out", "Doubtful"}
LONG_OUT = ("Injured Reserve", "Physically Unable to Perform", "Suspension", "Non Football Injury", "Reserve")


def _stats_cols():
    import nfl_stats
    return nfl_stats.LOG_COLS


LOG_COLS = _stats_cols()
COL = {c: i for i, c in enumerate(LOG_COLS)}


def stat_value(log, market):
    """A market's value in one game log (dict keyed by LOG_COLS), or None when a part is missing."""
    vals = [log.get(p) for p in MARKETS[market][1]]
    return None if any(v is None for v in vals) else float(sum(vals))


def season_str(season):
    """2026 -> "2026-27" (the page's season format, shared with the NBA side)."""
    return f"{season}-{str(season + 1)[2:]}"


# ── ESPN (live state, box scores, injuries, depth charts), cached under nfl_cache ─────────────────────────────
def espn_json(path, max_age, get=None):
    """An ESPN site API document, cached for max_age seconds (a failure falls back to the cache, however old)."""
    C.CACHE.mkdir(parents=True, exist_ok=True)
    f = C.CACHE / ("espn__" + path.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-"))
    import time
    if f.exists() and (max_age is None or time.time() - f.stat().st_mtime < max_age):
        try:
            return json.loads(f.read_text())
        except ValueError:
            pass
    try:
        raw = (get or (lambda u: C.fetch(u, timeout=20)))(f"{ESPN}/{path}")
        j = json.loads(raw)
    except Exception:
        try:
            return json.loads(f.read_text())
        except (OSError, ValueError):
            return None
    tmp = f.with_name(f.name + ".part")
    tmp.write_text(json.dumps(j))
    os.replace(tmp, f)
    return j


def live_state(games, get=None):
    """{gid: {"state": pregame/live/final/postponed, "label", "score": [away, home], "updated", "frac" (share of the
    game played), "espn", "weather", "stats": {pid: {log col: value}}}} from ESPN's scoreboard and, for games under
    way or over, its box score."""
    out = {g["gid"]: {"state": "pregame"} for g in games}
    if not games:
        return out
    d0 = min(g["date"] for g in games).replace("-", "")
    d1 = max(g["date"] for g in games).replace("-", "")
    sb = espn_json(f"scoreboard?dates={d0}-{d1}&limit=40", 50, get) or {}
    by_teams = {(g["away"], g["home"]): g["gid"] for g in games}
    for e in sb.get("events", []):
        c = (e.get("competitions") or [{}])[0]
        side = {x.get("homeAway"): x for x in c.get("competitors", [])}
        a, h = (C.team(((side.get(k) or {}).get("team") or {}).get("abbreviation")) for k in ("away", "home"))
        gid = by_teams.get((a, h))
        if not gid:
            continue
        s = c.get("status") or {}
        ty = s.get("type") or {}
        state = {"pre": "pregame", "in": "live", "post": "final"}.get(ty.get("state"), "pregame")
        if ty.get("name") in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_SUSPENDED"):
            state = "postponed"
        per, clock = s.get("period") or 0, s.get("clock") or 0
        frac = 1.0 if state == "final" else min(1.0, max(0.0, ((per - 1) * 900 + (900 - clock)) / 3600)) if per else 0.0
        w = e.get("weather") or {}
        out[gid] = {"state": state, "label": ty.get("shortDetail") or "", "espn": e.get("id"),
                    "score": [int((side.get("away") or {}).get("score") or 0), int((side.get("home") or {}).get("score") or 0)]
                    if state != "pregame" else None,
                    "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "frac": round(frac, 3),
                    "weather": {"text": w.get("displayValue"), "temp": w.get("temperature")} if w else None,
                    "indoor": bool((c.get("venue") or {}).get("indoor"))}
    return out


BOX = {"passing": {"C/ATT": ("pass_comp", "pass_att"), "YDS": "pass_yds", "TD": "pass_tds", "INT": "pass_int"},
       "rushing": {"CAR": "rush_att", "YDS": "rush_yds", "TD": "rush_tds", "LONG": "long_rush"},
       "receiving": {"REC": "rec", "YDS": "rec_yds", "TD": "rec_tds", "LONG": "long_rec", "TGTS": "targets"},
       "kicking": {"FG": ("fg_made", "fg_att"), "XP": ("pat_made", None), "PTS": "kick_pts"},
       "defensive": {"TOT": "tackles", "SACKS": "sacks"},
       "kickReturns": {"TD": "ret_td"}, "puntReturns": {"TD": "ret_td"}}


def box_stats(summary, espn_pid):
    """{pid: {log col: value}} from an ESPN summary's box score (ESPN athlete ids mapped through the roster)."""
    out = defaultdict(dict)
    for tm in ((summary or {}).get("boxscore") or {}).get("players") or []:
        for cat in tm.get("statistics") or []:
            want = BOX.get(cat.get("name"))
            if not want:
                continue
            labels = cat.get("labels") or []
            for a in cat.get("athletes") or []:
                pid = espn_pid.get(str((a.get("athlete") or {}).get("id")))
                if pid is None:
                    continue
                for lab, val in zip(labels, a.get("stats") or []):
                    k = want.get(lab)
                    if not k:
                        continue
                    if isinstance(k, tuple):
                        parts = str(val).split("/")
                        for kk, v in zip(k, parts):
                            if kk:
                                out[pid][kk] = _num(v)
                    else:
                        v = _num(val)
                        out[pid][k] = (out[pid].get(k) or 0) + (v or 0) if k == "ret_td" else v
    for s in out.values():
        if "rush_tds" in s or "rec_tds" in s or "ret_td" in s:
            s["td"] = (s.get("rush_tds") or 0) + (s.get("rec_tds") or 0) + (s.get("ret_td") or 0)
        for k in ("rush_tds", "rec_tds"):
            s.setdefault(k, 0)
        s["td"] = s.get("td", 0)
        if "pass_yds" in s or "rush_yds" in s or "rec_yds" in s:
            for k in ("pass_yds", "rush_yds", "rec_yds", "rec", "rush_att"):
                s.setdefault(k, 0)
    return dict(out)


def _num(v):
    try:
        f = float(str(v).replace(",", ""))
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def live_boxes(live, espn_pid, get=None):
    """Box scores of the games under way (refetched each run) and over (cached for good)."""
    out = {}
    for gid, s in live.items():
        if s.get("state") not in ("live", "final") or not s.get("espn"):
            continue
        j = espn_json(f"summary?event={s['espn']}", None if s["state"] == "final" else 50, get)
        if j is not None:
            out[gid] = box_stats(j, espn_pid)
    return out


INJ_MAP = {"Out": "Out", "Doubtful": "Doubtful", "Questionable": "Questionable", "Probable": "Probable"}


def injuries(players, get=None, official=None):
    """{pid: {"status", "reason", "published", "news": [...], "practice", "long"}} — ESPN's injury list (statuses, the
    note under each), the official report (nflverse: game status and practice participation) over it where it has one.
    A player on injured reserve (or PUP, suspended) is Out, marked long."""
    espn_pid = {r["espn"]: pid for pid, r in players.items() if r.get("espn")}
    out = {}
    j = espn_json("injuries", 600, get) or {}
    for t in j.get("injuries", []):
        for i in t.get("injuries", []):
            pid = espn_pid.get(str((i.get("athlete") or {}).get("id") or ""))
            if pid is None:
                link = ((i.get("athlete") or {}).get("links") or [{}])[0].get("href", "")
                pid = espn_pid.get(link.split("/id/")[-1].split("/")[0]) if "/id/" in link else None
            if pid is None:
                continue
            raw = i.get("status") or ""
            longo = any(raw.startswith(x) for x in LONG_OUT)
            status = "Out" if longo else INJ_MAP.get(raw)
            det = i.get("details") or {}
            reason = " ".join(x for x in (det.get("side") if det.get("side") not in (None, "Not Specified") else "",
                                          det.get("type") or "") if x).strip()
            out[pid] = {"status": status, "raw": raw, "reason": reason or None, "published": i.get("date"),
                        "long": longo, "return": det.get("returnDate"),
                        "news": [{"source": "ESPN", "headline": i.get("shortComment") or "", "detected": i.get("date")}]
                        if i.get("shortComment") else []}
    for pid, o in (official or {}).items():
        e = out.setdefault(pid, {"status": None, "raw": None, "reason": None, "published": None, "long": False,
                                 "return": None, "news": []})
        if o.get("status"):
            e["status"] = o["status"]
            e["official"] = True
        if o.get("reason") and not e["reason"]:
            e["reason"] = o["reason"]
        e["practice"] = o.get("practice")
    return out


def official_report(season, week):
    """{pid: {"status", "reason", "practice"}} — the official report for the week (nflverse injuries)."""
    out = {}
    try:
        rows = C.rows(f"injuries/injuries_{season}.csv", 3600)
    except Exception:
        return out
    for r in rows:
        if str(r.get("week")) != str(week):
            continue
        pid = C.pid_of(r.get("gsis_id"))
        if pid is None:
            continue
        st_ = (r.get("report_status") or "").strip()
        out[pid] = {"status": st_ if st_ in INJ_MAP else None,
                    "reason": (r.get("report_primary_injury") or r.get("practice_primary_injury") or "").strip() or None,
                    "practice": (r.get("practice_status") or "").replace(" in Practice", "").replace(" Participation", "").strip() or None}
    return out


def depth_charts(teams, players, get=None):
    """{team: {"QB": [pid, ...], "RB": [...], "WR": [...], "TE": [...], "K": [...]}} from ESPN's depth charts (the
    offense formation's spots, WR1-3 merged in order), refreshed every 6 h."""
    espn_pid = {r["espn"]: pid for pid, r in players.items() if r.get("espn")}
    out = {}
    spots = {"qb": "QB", "rb": "RB", "wr1": "WR", "wr2": "WR", "wr3": "WR", "te": "TE", "pk": "K"}
    for t in teams:
        j = espn_json(f"teams/{C.TEAMS[t][3]}/depthcharts", 6 * 3600, get) or {}
        d = {"QB": [], "RB": [], "WR": [], "TE": [], "K": []}
        wr = []
        for f in j.get("depthchart") or []:
            for k, v in (f.get("positions") or {}).items():
                grp = spots.get(k)
                if not grp:
                    continue
                ids = [espn_pid.get(str(a.get("id"))) for a in v.get("athletes") or []]
                ids = [x for x in ids if x is not None]
                if grp == "WR":
                    wr.append((k, ids))
                elif not d[grp]:
                    d[grp] = ids
        for depth in range(3):                       # WR1 starter, WR2 starter, WR3 starter, then their backups
            for _, ids in sorted(wr):
                if depth < len(ids) and ids[depth] not in d["WR"]:
                    d["WR"].append(ids[depth])
        out[t] = d
    return out


# ── the store ────────────────────────────────────────────────────────────────────────────────────────────────
def load_logs(scon, seasons):
    """{pid: [row in LOG_COLS order, oldest first]}, {pid: position} over the seasons."""
    logs, pos = defaultdict(list), {}
    if scon is None:
        return logs, pos
    cols = ", ".join(LOG_COLS)
    for r in scon.execute(f"SELECT pid, pos, {cols} FROM logs WHERE season IN ({','.join('?' * len(seasons))}) "
                          f"ORDER BY date", list(seasons)):
        logs[r[0]].append([int(v) if isinstance(v, float) and v.is_integer() else v for v in r[2:]])   # 20, not 20.0
        pos[r[0]] = r[1]
    return logs, pos


def names_of(scon):
    if scon is None:
        return {}
    try:
        return {r[0]: r[1] for r in scon.execute("SELECT pid, name FROM names")}
    except sqlite3.OperationalError:
        return {}


def players_of(scon):
    if scon is None:
        return {}
    return {r[0]: {"name": r[1], "team": r[2], "pos": r[3], "headshot": r[4], "espn": r[5], "jersey": r[6],
                   "depth_pos": r[7], "status": r[8]}
            for r in scon.execute("SELECT pid, name, team, pos, headshot, espn, jersey, depth_pos, status FROM players")}


def team_games(scon, seasons):
    out = defaultdict(list)
    if scon is None:
        return out
    for r in scon.execute(f"SELECT season, gid, week, date, team, opp, home, plays, pass, rush, neutral_pass, sec_play, pts, "
                          f"opp_pts FROM team_games WHERE season IN ({','.join('?' * len(seasons))}) ORDER BY date",
                          list(seasons)):
        out[r[4]].append(dict(zip(("season", "gid", "week", "date", "team", "opp", "home", "plays", "pass", "rush",
                                   "neutral_pass", "sec_play", "pts", "opp_pts"), r)))
    return out


def _rank(vals, low_first=True):
    """{team: rank} — 1 = the lowest value (the toughest defense) when low_first; ties share the better rank."""
    order = sorted(vals.values(), reverse=not low_first)
    return {t: 1 + order.index(v) for t, v in vals.items()}


def dvp_tables(logs, pos, season, before=None):
    """Defense vs position for one season, games before `before` (a date) when given: ({"dvp": {grp: {market: {team:
    rank}}}, "val": {grp: {market: {team: a game}}}, "n": {team: games}, "lg": {grp: {market: league a game}}}).
    A defense's game total for a group is the sum over that group's players (the longest-play markets: the group's
    longest), averaged over its games; rank 1 allows the least."""
    per = defaultdict(lambda: defaultdict(float))          # (opp, gid, grp, market) -> total
    games = defaultdict(set)
    for pid, rows in logs.items():
        grp = GROUP.get(pos.get(pid))
        if not grp:
            continue
        for r in rows:
            if NR.season_of(r[COL["date"]]) != season_str(season) or (before and r[COL["date"]] >= before):
                continue
            opp, gid = r[COL["opp"]], r[COL["gid"]]
            games[opp].add(gid)
            lg = dict(zip(LOG_COLS, r))
            for m in DVP_MARKETS[grp]:
                v = stat_value(lg, m)
                if v is None:
                    continue
                k = (opp, gid, grp, m)
                per[k] = max(per.get(k, 0.0), v) if m in MAX_OF else per.get(k, 0.0) + v
    tot = defaultdict(lambda: defaultdict(float))
    for (opp, gid, grp, m), v in per.items():
        tot[(grp, m)][opp] += v
    val, dvp, lg = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for (grp, m), by in tot.items():
        avgs = {t: round(v / len(games[t]), 2) for t, v in by.items() if games[t]}
        for t in games:                                   # a defense that allowed that group nothing at all
            avgs.setdefault(t, 0.0)
        val[grp][m] = avgs
        dvp[grp][m] = _rank(avgs)
        lg[grp][m] = round(st.mean(avgs.values()), 2) if avgs else None
    return {"dvp": dict(dvp), "val": dict(val), "n": {t: len(g) for t, g in games.items()}, "lg": dict(lg)}


def def_tables(tg, season, before=None):
    """({team: rank by points allowed a game}, {team: rank by offensive plays a game (1 = the most)}, {team: points
    allowed}, {team: plays}, {team: games})."""
    pa, plays, n = {}, {}, {}
    for t, rows in tg.items():
        rs = [r for r in rows if r["season"] == season and (not before or r["date"] < before) and r["opp_pts"] is not None]
        if rs:
            pa[t] = round(sum(r["opp_pts"] for r in rs) / len(rs), 1)
            plays[t] = round(sum(r["plays"] for r in rs) / len(rs), 1)
            n[t] = len(rs)
    return _rank(pa), _rank(plays, low_first=False), pa, plays, n


def pos_ranks(logs, pos, season, min_games=3):
    """{grp: {market: [(a game, pid), ...] best first}} this season (players with min_games games)."""
    out = defaultdict(dict)
    for grp, mks in DVP_MARKETS.items():
        for m in mks:
            lst = []
            for pid, rows in logs.items():
                if GROUP.get(pos.get(pid)) != grp:
                    continue
                vals = [stat_value(dict(zip(LOG_COLS, r)), m) for r in rows if NR.season_of(r[COL["date"]]) == season_str(season)]
                vals = [v for v in vals if v is not None]
                if len(vals) >= min_games:
                    lst.append((round(st.mean(vals), 2), pid))
            out[grp][m] = sorted(lst, reverse=True)
    return out


def correlations(props, logs):
    """For each prop: the other props posted for the same game, ranked by |Pearson r| of the two stats over the games
    both players played for the same team (nba_research.correlations, on football's markets)."""
    series = {p["id"]: {r[COL["gid"]]: (r[COL["team"]], stat_value(dict(zip(LOG_COLS, r)), p["market"]))
                        for r in logs.get(p["pid"], [])} for p in props}
    by_game = defaultdict(list)
    for p in props:
        by_game[p["gid"]].append(p)
    out, pair = {}, {}
    for p in props:
        mine, res = series[p["id"]], []
        for o in by_game[p["gid"]]:
            if o["id"] == p["id"] or (o["pid"] == p["pid"] and o["market"] == p["market"]):
                continue
            if o["pid"] != p["pid"] and o["team"] != p["team"]:
                continue
            k = (p["id"], o["id"], p["team"]) if p["id"] < o["id"] else (o["id"], p["id"], p["team"])
            if k not in pair:
                theirs = series[o["id"]]
                shared = [g for g in mine.keys() & theirs.keys() if mine[g][0] == theirs[g][0] == p["team"]]
                pair[k] = (len(shared), NR.pearson([mine[g][1] for g in shared], [theirs[g][1] for g in shared])
                           if len(shared) >= CORR_MIN_N else None)
            n, r = pair[k]
            if r is not None:
                res.append({"id": o["id"], "r": round(r, 2), "n": n})
        out[p["id"]] = sorted(res, key=lambda x: (-abs(x["r"]), x["id"]))[:NR.CORR_TOP]
    return out


CORR_MIN_N = 8               # a football season is 17 games: 8 shared games, not basketball's 15


def touches(r):
    return (r[COL["targets"]] or 0) + (r[COL["rush_att"]] or 0)


def team_usage(logs, pos, team, season, roster_team):
    """The team's share of its targets, carries, receiving and rushing yards, red-zone looks by player this season:
    [{pid, name, pos, g, tgt, car, rec_yds, rush_yds, rz, share: {...}}], the biggest share of touches first."""
    by, tot = defaultdict(lambda: defaultdict(float)), defaultdict(float)
    gp = defaultdict(set)
    for pid, rows in logs.items():
        if GROUP.get(pos.get(pid)) not in ("QB", "RB", "WR", "TE"):
            continue
        for r in rows:
            if r[COL["team"]] != team or NR.season_of(r[COL["date"]]) != season_str(season):
                continue
            gp[pid].add(r[COL["gid"]])
            for k, c in (("tgt", "targets"), ("car", "rush_att"), ("rec_yds", "rec_yds"), ("rush_yds", "rush_yds"),
                         ("rz", "rz_tgt"), ("rz", "rz_rush"), ("air", "air_yds"), ("td", "td")):
                v = r[COL[c]] or 0
                by[pid][k] += v
                tot[k] += v
    out = []
    for pid, v in by.items():
        if not (v["tgt"] or v["car"]):
            continue
        out.append({"pid": pid, "pos": pos.get(pid), "g": len(gp[pid]), "now": roster_team.get(pid) == team,
                    **{k: round(v[k]) for k in ("tgt", "car", "rec_yds", "rush_yds", "rz", "air", "td")},
                    "share": {k: round(100 * v[k] / tot[k]) if tot[k] else 0 for k in ("tgt", "car", "rec_yds", "rush_yds", "rz", "air")}})
    return sorted(out, key=lambda e: -(e["tgt"] + e["car"]))


ROLE_KEYS = (("snap_pct", 12), ("targets", 2.5), ("rush_att", 4), ("tgt_share", 7), ("rz", 1.5))


def roles(logs, pos, players, teams, season, absent_names):
    """The slate's players whose volume moved over their last 3 games (this season, 5+ games), against the rest of
    their season: snaps %, targets, carries, target share, red-zone looks — {"rows": [...], "thresholds", "mode"}."""
    rows_out = []
    for pid, rows in logs.items():
        if GROUP.get(pos.get(pid)) not in ("QB", "RB", "WR", "TE"):
            continue
        pl = players.get(pid) or {}
        if pl.get("team") not in teams:
            continue
        cur = [r for r in rows if NR.season_of(r[COL["date"]]) == season_str(season) and r[COL["team"]] == pl["team"]]
        if len(cur) < 5:
            continue
        now, before = cur[-3:], cur[:-3]
        def avg(rs, k):
            vals = [(r[COL["rz_tgt"]] or 0) + (r[COL["rz_rush"]] or 0) if k == "rz" else r[COL[k]] for r in rs]
            vals = [v for v in vals if v is not None]
            return (round(sum(vals) / len(vals)) if k in ("snap_pct", "tgt_share") else round(sum(vals) / len(vals), 1)) if vals else None
        stt = {k: [avg(now, k), avg(before, k)] for k, _ in ROLE_KEYS}
        if not any(a is not None and b is not None and abs(a - b) >= th for (k, th) in ROLE_KEYS for a, b in [stt[k]]):
            continue
        rows_out.append({"pid": pid, "name": pl.get("name"), "team": pl["team"], "pos": pos.get(pid), "st": stt,
                         "min": stt["snap_pct"], "usg": [None, None], "out": absent_names.get(pl["team"], [])[:3],
                         "starts": [0, 0, 0, 3], "was_team": None})
    return {"rows": rows_out, "thresholds": dict(ROLE_KEYS), "mode": "recent"}


# ── the payload ────────────────────────────────────────────────────────────────────────────────────────────────
def build(now=None, sched=None, lines=None, stats=None, get=None, official=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    sched = sched if sched is not None else C.schedule(None)
    season, week = C.current_week(sched, now)
    games = sorted([g for g in sched if g["season"] == season and g["week"] == week], key=lambda g: g["utc"])
    gids = [g["gid"] for g in games]
    dates = sorted({g["date"] for g in games})
    q, scon = NR._ro(lines or LINES), NR._ro(stats or STATS)
    players = players_of(scon)
    all_names = names_of(scon)
    espn_pid = {r["espn"]: pid for pid, r in players.items() if r.get("espn")}
    live = live_state(games, get)
    boxes = live_boxes(live, espn_pid, get)
    quotes, names, newest = NR.book_quotes(q, gids, MARKETS)
    nowu = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
    started = [g["gid"] for g in games if dt.datetime.fromisoformat(g["utc"]) <= nowu]
    cb, cnames = NR.closing_boards(q, started, cache=CLOSE_BOARDS if lines is None else Path(lines).with_name("nfl_close.json"),
                                   markets=MARKETS) if q is not None else ({}, {})
    closed = set()
    for k, books in cb.items():
        if k not in quotes:
            quotes[k] = books
            closed.add(k)
    for k, n in cnames.items():
        names.setdefault(k, n)
    hist = NR.line_history(q, gids, MARKETS)
    t0 = min((pts[0][0] for h in hist.values() for pts in h.values() if pts), default=None)
    t0 = dt.datetime.fromisoformat(t0).replace(second=0, microsecond=0) if t0 else None
    _hmin = lambda s_: int((dt.datetime.fromisoformat(s_) - t0).total_seconds() // 60)
    gmap = {g["gid"]: g for g in games}
    seasons = (season - 1, season)
    logs, lpos = load_logs(scon, seasons)
    pos = {pid: (players.get(pid) or {}).get("pos") or lpos.get(pid) for pid in set(players) | set(lpos)}
    props = []
    for (gid, pid, market), books in sorted(quotes.items()):
        g = gmap[gid]
        team = (players.get(pid) or {}).get("team")
        if team not in (g["home"], g["away"]) and logs.get(pid):
            team = logs[pid][-1][COL["team"]]
        if team not in (g["home"], g["away"]):
            team = None
        main = (books.get("fd") or {}).get("main")
        if main is None:
            main = (books.get("dk") or {}).get("main")
        if main is None and market in ONE_SIDED and any(NR.rung(b, 0.5) for b in books.values()):
            main = 0.5
        props.append({"id": f"{gid}|{pid}|{market}", "gid": gid, "pid": pid, "market": market,
                      "player": names.get((gid, pid)) or (players.get(pid) or {}).get("name") or "", "team": team,
                      "opp": (g["away"] if team == g["home"] else g["home"]) if team else None,
                      "home": team == g["home"] if team else None, "books": books, "main": main,
                      **({"closed": True} if (gid, pid, market) in closed else {})})
    # matchup context: this season's defense vs position before the week (last season's where a defense has too few games)
    first = dates[0] if dates else None
    cur_t = dvp_tables(logs, pos, season, before=first)
    prev_t = dvp_tables(logs, pos, season - 1)
    tg = team_games(scon, seasons)
    d_rank, p_rank, d_pa, d_plays, d_n = def_tables(tg, season, before=first)
    pd_rank, pp_rank, *_ = def_tables(tg, season - 1)
    teams_n = len(C.TEAMS)
    use = lambda t: (cur_t["n"].get(t) or 0) >= RANK_MIN
    rk_cur = {"teams": teams_n, "dvp": {}, "val": {}, "lg": cur_t["lg"], "def": {}, "pace": {}, "n": cur_t["n"],
              "pa": d_pa, "plays": d_plays}
    for grp, mk in cur_t["dvp"].items():
        rk_cur["dvp"][grp] = {}
        rk_cur["val"][grp] = {}
        for m, tbl in mk.items():
            # a defense with too few games this season keeps last season's rank (marked by n < RANK_MIN)
            rk_cur["dvp"][grp][m] = {t: (tbl.get(t) if use(t) else (prev_t["dvp"].get(grp, {}).get(m, {}).get(t) or tbl.get(t)))
                                     for t in C.TEAMS if tbl.get(t) or prev_t["dvp"].get(grp, {}).get(m, {}).get(t)}
            rk_cur["val"][grp][m] = cur_t["val"][grp][m]
    rk_cur["def"] = {t: d_rank.get(t) if (d_n.get(t) or 0) >= RANK_MIN else pd_rank.get(t) for t in C.TEAMS if d_rank.get(t) or pd_rank.get(t)}
    rk_cur["pace"] = {t: p_rank.get(t) for t in C.TEAMS if p_rank.get(t)}
    ranks = {d: rk_cur for d in dates}
    ranks[season_str(season - 1)] = {"teams": teams_n, "dvp": prev_t["dvp"], "val": prev_t["val"], "lg": prev_t["lg"],
                                     "def": pd_rank, "pace": pp_rank, "n": prev_t["n"]}
    pr = pos_ranks(logs, pos, season)
    pr_prev = pos_ranks(logs, pos, season - 1)
    for p in props:
        g = gmap[p["gid"]]
        grp = GROUP.get(pos.get(p["pid"])) or ("D" if p["market"] in ("sacks",) else None)
        ctx = {"group": grp if grp in DVP_MARKETS and p["market"] in DVP_MARKETS[grp] else None, "pace": None, "def": None,
               "opp_games": (cur_t["n"].get(p["opp"]) or 0) if p["opp"] else 0, "pace_rank": None, "dvp_rank": None,
               "def_rank": None, "teams": teams_n, "pos": pos.get(p["pid"]) or "", "pos_rank": None, "pos_n": 0,
               "pos_season": None, "rank_n": (cur_t["n"].get(p["opp"]) or 0) if p["opp"] else 0}
        if p["opp"]:
            ctx["def_rank"] = rk_cur["def"].get(p["opp"])
            ctx["pace_rank"] = rk_cur["pace"].get(p["opp"])
            if ctx["group"]:
                ctx["dvp_rank"] = rk_cur["dvp"].get(grp, {}).get(p["market"], {}).get(p["opp"])
                v, lgv = cur_t["val"].get(grp, {}).get(p["market"], {}).get(p["opp"]), cur_t["lg"].get(grp, {}).get(p["market"])
                if v is not None and lgv:
                    ctx["def"] = round(v / lgv, 3)
                    ctx["allow"] = v
                    ctx["lg"] = lgv
        for label, table in ((season, pr), (season - 1, pr_prev)):
            lst = (table.get(grp) or {}).get(p["market"]) or []
            at = next((i for i, (_, pid_) in enumerate(lst) if pid_ == p["pid"]), None)
            if at is not None:
                ctx.update(pos_rank=at + 1, pos_n=len(lst), pos_season=season_str(label))
                break
        p["ctx"] = ctx
        p["flag"] = None
        lv = live.get(p["gid"], {})
        bx = (boxes.get(p["gid"]) or {}).get(p["pid"])
        if lv.get("state") in ("live", "final"):
            v = stat_value(bx, p["market"]) if bx else None
            if v is None and lv.get("state") in ("live", "final") and p["market"] in ("anytime_td", "sacks"):
                v = 0.0 if bx is not None or lv["state"] == "live" else None
            if v is None and bx is None and lv.get("state") == "live":
                v = 0.0                                        # not in the box score yet: nothing so far
            if v is not None:
                p["live"] = {"value": v, "frac": lv.get("frac", 0), "min": None}
        main = p["main"]
        mylogs = [dict(zip(LOG_COLS, r)) for r in logs.get(p["pid"], [])]
        vals = [stat_value(r, p["market"]) for r in mylogs]
        cur = [stat_value(r, p["market"]) for r in mylogs if NR.season_of(r["date"]) == season_str(season)]
        p["summary"] = None if main is None else {
            "l5": NR.hit_summary(vals[-5:], main), "l10": NR.hit_summary(vals[-10:], main),
            "l20": NR.hit_summary(vals[-20:], main), "season": NR.hit_summary(cur, main)}
        h = hist.get((p["gid"], p["pid"], p["market"]), {})
        p["hist"] = {b: [[_hmin(x[0]), x[1], NR._r3(x[2]), NR._r3(x[3])] for x in pts] for b, pts in h.items()}
        fd0 = (h.get("fd") or [None])[0]
        p["open"] = [fd0[1], fd0[2], fd0[0]] if fd0 else None
    pids = {p["pid"] for p in props}
    slate_teams = sorted({t for g in games for t in (g["home"], g["away"])})
    roster_team = {pid: r["team"] for pid, r in players.items()}
    # injuries: ESPN's list under the official report; each slate team's listed players, the most snaps first
    off = official if official is not None else official_report(season, week)
    inj = injuries(players, get, off)
    depth = depth_charts(slate_teams, players, get)
    by_team = defaultdict(list)
    for pid, rows in logs.items():
        for r in rows:
            by_team[(r[COL["team"]])].append((r[COL["date"]], r[COL["gid"]], pid, r))
    team_gids = {t: sorted({(d, gid) for d, gid, _, _ in by_team[t]}) for t in slate_teams}
    published = max((e.get("published") or "" for e in inj.values()), default="") or None
    report_meta = {d: {"published": published} for d in dates} if inj else {}
    injuries_out, absences, inj_report = {}, {}, {}
    absent_names = defaultdict(list)
    cur_s = season_str(season)
    for g in games:
        for t in (g["home"], g["away"]):
            gl = team_gids.get(t, [])
            last2 = {gid for _, gid in [x for x in gl if x[0] < g["date"]][-FRESH_GAMES:]}
            listed, ab = [], []
            for pid, e in inj.items():
                if roster_team.get(pid) != t or not e.get("status"):
                    continue
                mine = [r for r in logs.get(pid, []) if r[COL["team"]] == t]
                cur_r = [r for r in mine if NR.season_of(r[COL["date"]]) == cur_s]
                use_r = cur_r or mine
                snap = [r[COL["snap_pct"]] for r in use_r if r[COL["snap_pct"]] is not None]
                spct = round(sum(snap) / len(snap), 1) if snap else None
                played = [r[COL["gid"]] for r in mine]
                fresh = bool(last2 & set(played))
                missed = sum(1 for d, gid in gl if NR.season_of(d) == cur_s and gid not in set(played) and d < g["date"]
                             and (not cur_r or d >= cur_r[0][COL["date"]]))
                if e["status"] in ("Out", "Doubtful", "Questionable") and played:
                    ent = {"pid": pid, "name": (players.get(pid) or {}).get("name"), "pos": pos.get(pid) or "",
                           "status": e["status"], "reason": ("IR · " if e.get("long") and e.get("raw", "").startswith("Injured") else "") + (e.get("reason") or ""),
                           "mpg": spct, "gp": len(use_r), "season": NR.season_of(use_r[-1][COL["date"]]) if use_r else None,
                           "starter": bool(spct and spct >= 60), "missed": missed, "starts": None, "minutes": [],
                           "fresh": fresh, "practice": e.get("practice"), "long": e.get("long", False)}
                    grp = GROUP.get(pos.get(pid))
                    if spct and spct >= ROT_SNAP and grp in ("QB", "RB", "WR", "TE"):
                        ent["minutes"] = [dict(x, name=(players.get(x["pid"]) or {}).get("name") or str(x["pid"]))
                                          for x in gains(logs, pos, t, set(played), gl, pid)]
                        dc = (depth.get(t) or {}).get(grp) or []
                        if ent["starter"] and pid in dc[:3 if grp == "WR" else 1]:
                            nxt = next((x for x in dc if x != pid and (inj.get(x) or {}).get("status") not in OUT_LIKE
                                        and x not in dc[:3 if grp == "WR" else 1]), None) if grp == "WR" else \
                                next((x for x in dc if x != pid and (inj.get(x) or {}).get("status") not in OUT_LIKE), None)
                            if nxt is not None:
                                ent["starts"] = {"pid": nxt, "name": (players.get(nxt) or {}).get("name"), "k": None,
                                                 "n": None, "how": "depth"}
                    listed.append(ent)
                if e["status"] in OUT_LIKE and played and GROUP.get(pos.get(pid)) in ("QB", "RB", "WR", "TE"):
                    since = mine[0][COL["date"]] if mine else None
                    ab.append({"pid": pid, "played": played, "since": since, "status": e["status"], "fresh": fresh,
                               "name": (players.get(pid) or {}).get("name")})
                    if fresh:
                        absent_names[t].append((players.get(pid) or {}).get("name") or "")
            order = ("Out", "Doubtful", "Questionable")
            listed.sort(key=lambda x: (order.index(x["status"]), -(x["mpg"] or 0)))
            inj_report[f"{g['date']}|{t}"] = {"listed": True, "published": published, "players": listed}
            absences[f"{g['date']}|{t}"] = ab
    for p in props:
        d = gmap[p["gid"]]["date"]
        e = inj.get(p["pid"])
        injuries_out[f"{d}|{p['pid']}"] = {
            "official": {"status": e["status"], "reason": e.get("reason"), "published": e.get("published"),
                         "practice": e.get("practice"), "long": e.get("long")} if e and e.get("status") else None,
            "listed_team": bool(inj), "news": (e or {}).get("news", [])}
    # with / without: every current teammate who has played for the team (two seasons), the most snaps first
    mates = {}
    for t in slate_teams:
        gl = [gid for _, gid in team_gids.get(t, [])]
        if not gl:
            continue
        idx = {gid: i for i, gid in enumerate(gl)}
        ms = []
        for pid, rows in logs.items():
            if roster_team.get(pid) != t or GROUP.get(pos.get(pid)) not in ("QB", "RB", "WR", "TE"):
                continue
            mine = [r for r in rows if r[COL["team"]] == t]
            if not mine:
                continue
            on = ["0"] * len(gl)
            for r in mine:
                on[idx[r[COL["gid"]]]] = "1"
            sn = [r[COL["snap_pct"]] for r in mine if r[COL["snap_pct"]] is not None]
            ms.append({"pid": pid, "name": (players.get(pid) or {}).get("name"), "since": mine[0][COL["date"]],
                       "on": "".join(on), "mpg": round(sum(sn) / len(sn), 1) if sn else 0, "gp": len(mine)})
        mates[t] = {"gids": gl, "mates": sorted(ms, key=lambda m: -m["mpg"])[:40]}
    corr = correlations(props, logs)
    # the slate's other players with no prop up who matter to one (absent teammates): their logs too, for the filters
    extra = {a["pid"] for v in absences.values() for a in v}
    out_players = {}
    for pid in pids | extra:
        pl = players.get(pid) or {}
        out_players[str(pid)] = {"name": pl.get("name") or next((p["player"] for p in props if p["pid"] == pid), ""),
                                 "pos": pos.get(pid) or "", "logs": logs.get(pid, []), "headshot": pl.get("headshot"),
                                 "jersey": pl.get("jersey"), "espn": pl.get("espn")}
    # rushing direction and target trees for the players with props; each slate defense's direction allowed
    rush = {"p": {}, "d": {}, "lg": {}}
    tree = {}
    if scon is not None:
        for kind, key, cells in scon.execute("SELECT kind, key, cells FROM rush_dir WHERE season=?", (season,)):
            c = json.loads(cells)
            if kind == "p" and int(key) in pids:
                rush["p"][key] = c
            elif kind == "d":
                if key in slate_teams:
                    rush["d"][key] = c
                for dk, v in c.items():
                    a = rush["lg"].setdefault(dk, [0, 0, 0, 0])
                    a[0] += v[0]; a[1] += v[1]; a[2] += v[2]; a[3] += 1
        for pid, cells in scon.execute("SELECT pid, cells FROM tgt_tree WHERE season=?", (season,)):
            if pid in pids:
                tree[str(pid)] = json.loads(cells)
    rush["lg"] = {k: [round(v[0] / v[3], 1), round(v[1] / v[3], 1), round(v[2] / v[3], 2)] for k, v in rush["lg"].items() if v[3]}
    tgames = defaultdict(set)
    for t in slate_teams:
        tgames[t] = {gid for d, gid in team_gids.get(t, []) if NR.season_of(d) == cur_s}
    usage = {t: team_usage(logs, pos, t, season, roster_team) for t in slate_teams}
    for t, lst in usage.items():
        for e in lst:
            e["name"] = (players.get(e["pid"]) or {}).get("name") or str(e["pid"])
    teams_info = {t: {"games": len(tgames[t]), "plays": d_plays.get(t), "pa": d_pa.get(t),
                      "neutral_pass": _avg([r["neutral_pass"] for r in tg.get(t, []) if r["season"] == season]),
                      "sec_play": _avg([r["sec_play"] for r in tg.get(t, []) if r["season"] == season]),
                      "pts": _avg([r["pts"] for r in tg.get(t, []) if r["season"] == season and r["pts"] is not None])}
                  for t in slate_teams}
    glines = NR.game_lines(q, gids)
    for g in games:                                    # nflverse's line where FanDuel has none (yet)
        if g["gid"] not in glines and g.get("spread") is not None:
            glines[g["gid"]] = {"spread_home": -g["spread"], "spread_away": g["spread"], "total": g.get("total"),
                                "updated": None, "src": "nflverse"}
    spots = {g["gid"]: {g["home"]: _spot(g["home_rest"]), g["away"]: _spot(g["away_rest"])} for g in games}
    fresh = {}
    for b, at in newest.items():
        age = (nowu - NR._naive_utc(at)).total_seconds() / 60
        fresh[b] = {"updated": at, "age_min": round(age, 1), "stale": age > NR.BOOK_STALE_MIN}
    meta = {}
    if scon is not None:
        try:
            meta = json.loads(scon.execute("SELECT v FROM meta WHERE k='meta'").fetchone()[0])
        except (TypeError, sqlite3.OperationalError, ValueError):
            meta = {}
    stamp = now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()
    out = {
        "sport": "nfl", "generated_at": stamp, "season": cur_s, "week": week, "dates": dates, "log_cols": list(LOG_COLS),
        "hist_t0": t0.isoformat() if t0 else None,
        "markets": {k: v[0] for k, v in MARKETS.items()},
        "sources": {"books": fresh, "report": report_meta,
                    "logs": {"through": max((r[0] for v in logs.values() for r in v), default=None),
                             "seasons": [season_str(season - 1), cur_s], "built_at": meta.get("built_at")},
                    "matchup": {"available": bool(cur_t["n"])}, "game_lines": {"games": len(glines)}},
        "games": [{"gid": g["gid"], "date": g["date"], "tip": g["utc"], "away": g["away"], "home": g["home"],
                   "week": g["week"], "lines": glines.get(g["gid"]), "spots": spots.get(g["gid"]),
                   "roof": g.get("roof"), "surface": g.get("surface"), "stadium": g.get("stadium"), "div": g.get("div"),
                   **{k: v for k, v in live.get(g["gid"], {}).items()}} for g in games],
        "props": props, "players": out_players, "injuries": injuries_out, "flags": [],
        "absences": absences, "related": corr, "inj_report": inj_report, "mates": mates, "lineups": {},
        "depth": {t: {k: [[pid, (players.get(pid) or {}).get("name") or ""] for pid in v[:6]] for k, v in d.items()}
                  for t, d in depth.items()},
        "ranks": ranks, "proj_players": {}, "proj_meta": {"none": True},
        "rush_dir": rush, "tgt_tree": tree, "usage": usage, "teams": teams_info,
        "roles": roles(logs, pos, players, set(slate_teams), season, absent_names),
        "vs": vs_rows(logs, pos, slate_teams, all_names),
        "heads": {},
    }
    # every player the page may show a face for (injury lists, depth charts, usage, the vs table): his ESPN id
    shown = {e["pid"] for v in inj_report.values() for e in v["players"]} | {x["pid"] for v in inj_report.values() for e in v["players"] for x in e["minutes"]}
    shown |= {pid for d in depth.values() for v in d.values() for pid in v[:6]} | {e["pid"] for v in usage.values() for e in v}
    shown |= {r["pid"] for r in out["roles"]["rows"]} | {r[3] for v in out["vs"].values() for r in v} | {m["pid"] for v in mates.values() for m in v["mates"]}
    out["heads"] = {str(pid): (players.get(pid) or {}).get("espn") for pid in shown if (players.get(pid) or {}).get("espn")}
    out["_boxes"] = box_files(logs, pos, all_names, sched, seasons)
    for c in (q, scon):
        if c is not None:
            c.close()
    return out


VS_GAMES = 8                 # the opponent's last 8 games in the Matchup page's table


def vs_rows(logs, pos, teams, names):
    """{defense: [[date, gid, offense, pid, name, group, {market: value}], ...]} — each slate defense's last VS_GAMES
    games, the players of each group it faced (who touched the ball), newest first."""
    out = defaultdict(list)
    want = set(teams)
    for pid, rows in logs.items():
        grp = GROUP.get(pos.get(pid))
        if grp not in ("QB", "RB", "WR", "TE"):
            continue
        for r in rows:
            if r[COL["opp"]] not in want or not (r[COL["pass_att"]] if grp == "QB" else touches(r)):
                continue                        # a quarterback who threw, a back or receiver who touched it
            lg = dict(zip(LOG_COLS, r))
            out[r[COL["opp"]]].append([r[COL["date"]], r[COL["gid"]], r[COL["team"]], pid, names.get(pid) or str(pid), grp,
                                       {m: stat_value(lg, m) for m in DVP_MARKETS[grp]}])
    res = {}
    for t, rs in out.items():
        gids = sorted({(r[0], r[1]) for r in rs}, reverse=True)[:VS_GAMES]
        keep = {g for _, g in gids}
        res[t] = sorted([r for r in rs if r[1] in keep], key=lambda r: (r[0], -(r[6].get("rec_yds") or r[6].get("rush_yds") or r[6].get("pass_yds") or 0)), reverse=True)
    return res


BOX_COLS = ("snap_pct", "pass_comp", "pass_att", "pass_yds", "pass_tds", "pass_int", "rush_att", "rush_yds", "rush_tds",
            "long_rush", "targets", "rec", "rec_yds", "rec_tds", "long_rec", "fg_made", "fg_att", "pat_made", "sacks", "tackles")


def box_files(logs, pos, names, sched, seasons):
    """{gid: box} for every game in the logs: each team's players with a stat line (BOX_COLS), the score."""
    games = {g["gid"]: g for g in sched if g["season"] in seasons}
    by = defaultdict(lambda: defaultdict(list))
    for pid, rows in logs.items():
        for r in rows:
            by[r[COL["gid"]]][r[COL["team"]]].append([pid, names.get(pid) or str(pid), pos.get(pid) or ""] + [r[COL[c]] for c in BOX_COLS])
    out = {}
    for gid, teams in by.items():
        g = games.get(gid)
        if not g:
            continue
        order = {"QB": 0, "RB": 1, "FB": 1, "WR": 2, "TE": 3, "K": 4}
        out[gid] = {"date": g["date"], "status": "Final", "cols": list(BOX_COLS),
                    "teams": [{"tri": t, "pts": g["away_score"] if t == g["away"] else g["home_score"],
                               "players": sorted(teams.get(t, []), key=lambda x: (order.get(x[2], 5), -(x[3] or 0)))}
                              for t in (g["away"], g["home"])]}
    return out


def gains(logs, pos, team, played, gl, pid):
    """The teammates who got 1.5+ more targets + carries a game in the team's games without him (2+ of them, this
    season and last, games before the first he played for the team left out): [{pid, name, gain, mpg, n}]."""
    first = min((d for d, gid in gl if gid in played), default=None)
    if first is None:
        return []
    with_g = {gid for d, gid in gl if gid in played}
    wo_g = {gid for d, gid in gl if gid not in played and d >= first}
    if len(wo_g) < MIN_WITHOUT or len(with_g) < MIN_WITHOUT:
        return []
    out = []
    for y, rows in logs.items():
        if y == pid or GROUP.get(pos.get(y)) not in ("QB", "RB", "WR", "TE"):
            continue
        mine = {r[COL["gid"]]: touches(r) for r in rows if r[COL["team"]] == team}
        nw = [mine[g] for g in with_g if g in mine]
        no = [mine[g] for g in wo_g if g in mine]
        if len(nw) < MIN_WITHOUT or len(no) < MIN_WITHOUT:
            continue
        gain = sum(no) / len(no) - sum(nw) / len(nw)
        if gain >= MIN_GAIN:
            out.append({"pid": y, "gain": round(gain, 1), "mpg": round(sum(no) / len(no), 1), "n": len(no)})
    out.sort(key=lambda e: -e["gain"])
    return out[:3]


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if xs else None


def _spot(rest):
    """A team's schedule spot from its days of rest: short week (4 or fewer), off a bye (10+)."""
    if rest is None:
        return {"rest": None, "short": False, "bye": False, "b2b": False, "trip": None}
    r = int(rest)
    return {"rest": r, "short": r <= 4, "bye": r >= 10, "b2b": False, "trip": None}


BOX_FRESH_DAYS = 4           # a box score file is rewritten while its game is this recent (nflverse corrects stats)


def write(out_dir, payload, today=None):
    """Atomic writes of nfl_props.json and the box scores (docs/nflbox/{gid}.json: new games, and the last few days'
    again). The page itself is written by nba_research."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    boxes = payload.pop("_boxes", {}) or {}
    bd = out_dir / "nflbox"
    bd.mkdir(exist_ok=True)
    today = today or dt.date.today()
    for gid, b in boxes.items():
        f = bd / f"{gid}.json"
        if f.exists() and (today - dt.date.fromisoformat(b["date"])).days > BOX_FRESH_DAYS:
            continue
        tmp = bd / f".{gid}.json.tmp"
        tmp.write_text(json.dumps(b, separators=(",", ":")))
        os.replace(tmp, f)
    tmp = out_dir / ".nfl_props.json.tmp"
    tmp.write_text(json.dumps(payload, separators=(",", ":"), default=str))
    os.replace(tmp, out_dir / "nfl_props.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("NBA_RESEARCH_OUT", str(HERE / "docs")))
    a = ap.parse_args()
    pl = build()
    write(a.out, pl)
    print(f"nfl_research: week {pl['week']} · {len(pl['props'])} props · {len(pl['games'])} games · "
          f"{len(pl['players'])} players -> {a.out}")
