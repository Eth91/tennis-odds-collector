#!/usr/bin/env python3
"""NHL prop research for Pickz: the data behind the NHL side of docs/nba_props.html (nhl_props.json; the page is
nba_research_ui.py, the same page as the NBA's and the NFL's, switched by the league button).

The same shape as nba_research's and nfl_research's payloads, so the page reads all three the same way: today's and
tomorrow's games, every player prop FanDuel and DraftKings post (nhl_lines.sqlite, alternate rungs included) with each
book's line history, the fair price and how far the best price beats it; each player's game logs this season and last
(nhl_stats.sqlite: goals, assists, shots, blocks, saves, power-play points, time on ice at even strength, on the power
play and short-handed, shifts, shot attempts, his share of his team's shots and power-play time); the injury list
(ESPN's statuses and notes); the expected starting goalies (ESPN); matchup context (defense vs position by market,
goals and shots allowed, pace); the lines (nhl_onoff: forward lines, defense pairs and power-play units from the last
game's shifts); live box scores for games under way. Everything is descriptive or a market estimate: nothing here is a
projection or a pick.

LIMITS
  books     FanDuel and DraftKings only (nhl_lines). DraftKings arrives as a snapshot (it blocks this box).
  logs      regular season and playoffs, this season and last (the NHL's reports; a game lands within the hour).
  injuries  ESPN's list (the NHL has no official injury report); day-to-day is the only "maybe".

    python3 nhl_research.py --out /home/ubuntu/tennis-odds-collector/docs    # writes nhl_props.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import statistics as st
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import nba_research as NR
import nhl_common as C
import nhl_stats as S

HERE = Path(__file__).resolve().parent
LINES = Path(os.environ.get("NHL_LINES_DB", HERE / "nhl_lines.sqlite"))
STATS = Path(os.environ.get("NHL_STATS_DB", HERE / "nhl_stats.sqlite"))
ONOFF = Path(os.environ.get("NHL_ONOFF_DB", HERE / "nhl_onoff.sqlite"))
CLOSE_BOARDS = HERE / "nhl_close_boards.json"
LINED = HERE / "nhl_lined.json"
ESPN = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
# market -> (label, log columns summed). The books' NHL player props (nhl_lines' stat keys)
MARKETS = {"points": ("PTS", ("points",)), "shots": ("SOG", ("shots",)), "goals": ("G", ("goals",)),
           "assists": ("A", ("assists",)), "saves": ("SV", ("saves",)), "blocks": ("BLK", ("blocks",)),
           "ppp": ("PPP", ("ppp",))}
LOG_COLS = S.LOG_COLS
COL = {c: i for i, c in enumerate(LOG_COLS)}
GROUP = {"C": "C", "L": "W", "R": "W", "D": "D", "G": "G"}
SKATER_M = ("goals", "assists", "points", "shots", "blocks", "ppp")
DVP_MARKETS = {"C": SKATER_M, "W": SKATER_M, "D": SKATER_M, "G": ("saves",)}
RANK_MIN = 5                 # a team ranks once it has this many games this season (else last season's rank stands in)
SLATE_ROLL_H = NR.SLATE_ROLL_H
FRESH_GAMES = 3              # an absence is news while he played in one of his team's last 3 games
ROT_MIN = 10                 # a listed player under 10 minutes a game gets no replacement read
MIN_WITHOUT = 2              # team games without him before a teammate's gain in them is read
MIN_GAIN = 1.5               # minutes of ice time a game a teammate must gain without him to be named
OUT_LIKE = {"Out"}
LONG_OUT = ("Injured Reserve", "Long Term Injured Reserve", "Suspension", "Suspended")
INJ_MAP = {"Out": "Out", "Day-To-Day": "Day-To-Day"}
CORR_MIN_N = 15              # games the two players shared before a correlation is shown (the NBA's)
VS_GAMES = 10                # the opponent's last 10 games in the Matchup page's table
BOX_FRESH_DAYS = 3           # a box score file is rewritten while its game is this recent (the NHL corrects stats)
REG_MIN = {"C": 14, "W": 14, "D": 18}                     # a regular: this many minutes a game this season


def stat_value(log, market):
    """A market's value in one game log (dict keyed by LOG_COLS), or None when a part is missing."""
    vals = [log.get(p) for p in MARKETS[market][1]]
    return None if any(v is None for v in vals) else float(sum(vals))


season_str = lambda season: f"{season}-{str(season + 1)[2:]}"          # 2026 -> "2026-27", the page's season


# ── ESPN (injuries, starting goalies), cached under nhl_cache ─────────────────────────────────────────────────
def espn_json(path, max_age, get=None):
    """An ESPN site API document, cached for max_age seconds (a failure falls back to the cache, however old)."""
    name = "espn__" + path.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "-")
    try:
        return C.cached(name, f"{ESPN}/{path}", max_age, get=get)
    except Exception:                                                        # noqa: BLE001
        return None


def injuries(players, get=None):
    """{pid: {"status" (Out / Day-To-Day), "raw", "reason", "published", "news": [...], "long"}} — ESPN's injury list,
    matched by name within the team ESPN files him under. On injured reserve (long-term too) or suspended is Out, long."""
    res = C.Resolver({pid: r for pid, r in players.items() if r.get("team")}, search=False)
    out = {}
    j = espn_json("injuries", 600, get) or {}
    for t in j.get("injuries", []):
        team = C.team_of_name(t.get("displayName") or "")
        for i in t.get("injuries", []):
            a = i.get("athlete") or {}
            pid = res.resolve(a.get("displayName") or "", (team,)) if team else None
            if pid is None:
                continue
            raw = i.get("status") or ""
            longo = any(raw.startswith(x) for x in LONG_OUT)
            status = "Out" if longo else INJ_MAP.get(raw)
            det = i.get("details") or {}
            reason = " ".join(x for x in (det.get("side") if det.get("side") not in (None, "Not Specified") else "",
                                          det.get("type") or "") if x).strip()
            out[pid] = {"status": status, "raw": raw, "reason": reason or None, "published": i.get("date"), "long": longo,
                        "return": det.get("returnDate"),
                        "news": [{"source": "ESPN", "headline": i.get("shortComment") or "", "detected": i.get("date")}]
                        if i.get("shortComment") else []}
    return out


def goalies(games, players, get=None):
    """{gid: {team: {"pid", "name", "status" ("Expected" / "Confirmed" ...)}}} — ESPN's probable starting goalies."""
    res = C.Resolver({pid: r for pid, r in players.items() if r.get("team")}, get=get)
    by_teams = {(g["away"], g["home"]): g["gid"] for g in games}
    out = {}
    for day in sorted({g["date"] for g in games}):
        sb = espn_json(f"scoreboard?dates={day.replace('-', '')}", 300, get) or {}
        for e in sb.get("events", []):
            c = (e.get("competitions") or [{}])[0]
            side = {x.get("homeAway"): x for x in c.get("competitors", [])}
            a, h = (C.team(((side.get(k) or {}).get("team") or {}).get("abbreviation")) for k in ("away", "home"))
            gid = by_teams.get((a, h))
            if not gid:
                continue
            for k, t in (("away", a), ("home", h)):
                for p in (side.get(k) or {}).get("probables") or []:
                    if p.get("name") != "probableStartingGoalie":
                        continue
                    nm = (p.get("athlete") or {}).get("displayName") or ""
                    pid = res.resolve(nm, (t,))
                    out.setdefault(gid, {})[t] = {"pid": pid, "name": nm,
                                                  "status": ((p.get("status") or {}).get("name")) or "Expected"}
    return out


# ── the NHL's live scores and box scores ──────────────────────────────────────────────────────────────────────
def _period_label(per, desc, clock):
    kind = (desc or {}).get("periodType") or "REG"
    name = "OT" if kind == "OT" else "SO" if kind == "SO" else {1: "1st", 2: "2nd", 3: "3rd"}.get(per, f"P{per}")
    if (clock or {}).get("inIntermission"):
        return f"End {name}"
    return f"{name} {(clock or {}).get('timeRemaining') or ''}".strip()


def live_state(games, get=None):
    """{gid: {"state": pregame/live/final/postponed, "label", "score": [away, home], "updated", "frac" (share of
    regulation played), "ppp": {pid: power-play points so far}}} from the NHL's scores (a minute's cache). A game the
    feed leaves out is final once the schedule has its score."""
    out = {g["gid"]: {"state": "pregame"} for g in games}
    seen = set()
    for day in sorted({g["date"] for g in games}):
        try:
            sb = C.cached(f"score_{day}.json", f"{C.WEB}/score/{day}", 50, get=get)
        except Exception:                                                    # noqa: BLE001
            print(f"nhl_research: no NHL scores for {day}", file=sys.stderr)
            continue
        for e in sb.get("games", []):
            gid = str(e.get("id"))
            if gid not in out:
                continue
            seen.add(gid)
            state = C.game_state(e.get("gameState"))
            if (e.get("gameScheduleState") or "OK") not in ("OK",):
                state = "postponed"
            per, clock, desc = e.get("period") or 0, e.get("clock") or {}, e.get("periodDescriptor") or {}
            left = clock.get("secondsRemaining") or 0
            frac = 1.0 if state == "final" else min(1.0, ((min(per, 3) - 1) * 1200 + (1200 - left if per <= 3 else 1200)) / 3600) if per else 0.0
            ot = (e.get("gameOutcome") or {}).get("lastPeriodType")
            label = ("Final" + (f"/{ot}" if ot in ("OT", "SO") else "")) if state == "final" else \
                _period_label(per, desc, clock) if state == "live" else ""
            ppp = Counter()
            for gl in e.get("goals") or []:
                if (gl.get("strength") or "").lower() == "pp":
                    for x in [gl.get("playerId")] + [a.get("playerId") for a in gl.get("assists") or []]:
                        if x:
                            ppp[int(x)] += 1
            out[gid] = {"state": state, "label": label,
                        "score": [int((e.get("awayTeam") or {}).get("score") or 0), int((e.get("homeTeam") or {}).get("score") or 0)]
                        if state in ("live", "final") else None,
                        "sog": [(e.get("awayTeam") or {}).get("sog"), (e.get("homeTeam") or {}).get("sog")] if state in ("live", "final") else None,
                        "updated": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), "frac": round(frac, 3),
                        "ppp": {str(k): v for k, v in ppp.items()}}
    for g in games:
        if g["gid"] not in seen and g.get("home_score") is not None:
            out[g["gid"]] = {"state": "final", "label": "Final", "frac": 1.0, "ppp": {},
                             "score": [int(g["away_score"]), int(g["home_score"])]}
    return out


def _toi(s):
    try:
        m, sec = str(s or "0:0").split(":")
        return round(int(m) + int(sec) / 60, 2)
    except ValueError:
        return None


def live_boxes(live, get=None):
    """{gid: {pid: {log col: value}}} for games under way or over: the NHL's box score (half a minute's cache), with
    power-play points from the scoring summary (the box score has power-play goals only)."""
    out = {}
    for gid, lv in live.items():
        if lv.get("state") not in ("live", "final"):
            continue
        try:
            j = C.cached(f"box_{gid}.json", f"{C.WEB}/gamecenter/{gid}/boxscore", 30 if lv["state"] == "live" else 3600, get=get)
        except Exception:                                                    # noqa: BLE001
            continue
        stats = {}
        for side in ("awayTeam", "homeTeam"):
            blk = (j.get("playerByGameStats") or {}).get(side) or {}
            who = lambda p: {"_team": C.team((j.get(side) or {}).get("abbrev")), "_pos": p.get("position"),
                             "_name": (p.get("name") or {}).get("default") or ""}
            for grp in ("forwards", "defense"):
                for p in blk.get(grp) or []:
                    stats[int(p["playerId"])] = {"goals": p.get("goals"), "assists": p.get("assists"), "points": p.get("points"),
                                                 "shots": p.get("sog"), "blocks": p.get("blockedShots"), "hits": p.get("hits"),
                                                 "pm": p.get("plusMinus"), "pim": p.get("pim"), "min": _toi(p.get("toi")),
                                                 "ppp": (lv.get("ppp") or {}).get(str(p["playerId"]), 0), **who(p)}
            for p in blk.get("goalies") or []:
                stats[int(p["playerId"])] = {"saves": p.get("saves"), "sa": p.get("shotsAgainst"), "min": _toi(p.get("toi")),
                                             "goals": p.get("goals") or 0, "assists": p.get("assists") or 0, "pim": p.get("pim"),
                                             "points": (p.get("goals") or 0) + (p.get("assists") or 0), **who(p)}
        out[gid] = stats
    return out


# ── the store ────────────────────────────────────────────────────────────────────────────────────────────────
def load_logs(scon, seasons):
    """{pid: [row in LOG_COLS order, oldest first]}, {pid: position} over the seasons."""
    logs, pos, seen = defaultdict(list), {}, {}
    if scon is None:
        return logs, pos
    one = lambda v: int(v) if isinstance(v, float) and v.is_integer() else seen.setdefault(v, v) if isinstance(v, str) else v
    for r in scon.execute(f"SELECT pid, pos, {', '.join(LOG_COLS)} FROM logs WHERE season IN "
                          f"({','.join('?' * len(seasons))}) ORDER BY date, gid", list(seasons)):
        logs[r[0]].append([one(v) for v in r[2:]])           # 3, not 3.0; one copy of each date, game id and team (the VM's RAM)
        pos[r[0]] = r[1]
    return logs, pos


def players_of(scon):
    if scon is None:
        return {}
    return {r[0]: {"name": r[1], "team": r[2], "pos": r[3], "headshot": r[4], "jersey": r[5]}
            for r in scon.execute("SELECT pid, name, team, pos, headshot, jersey FROM players")}


def names_of(scon):
    if scon is None:
        return {}
    return {r[0]: r[1] for r in scon.execute("SELECT pid, name FROM names")}


def team_games(scon, seasons):
    out = defaultdict(list)
    if scon is None:
        return out
    for r in scon.execute(f"SELECT {', '.join(S.TEAM_COLS)} FROM team_games WHERE season IN "
                          f"({','.join('?' * len(seasons))}) ORDER BY date", list(seasons)):
        out[r[3]].append(dict(zip(S.TEAM_COLS, r)))
    return out


def lines_of(ocon, teams):
    """{team: {"F": [[pid x3], ...], "D": [[pid x2], ...], "PP1": [...], "PP2": [...], "G": [pid], "gid", "date"}} — each
    team's last game's lines (nhl_onoff.lines); {} without the store."""
    out = {}
    if ocon is None:
        return out
    try:
        for t, js in ocon.execute(f"SELECT team, js FROM lines WHERE team IN ({','.join('?' * len(teams))})", list(teams)):
            out[t] = json.loads(js)
    except sqlite3.OperationalError:
        pass
    return out


# ── matchup context ──────────────────────────────────────────────────────────────────────────────────────────
_rank = lambda vals, low_first=True: {t: 1 + sorted(vals.values(), reverse=not low_first).index(v) for t, v in vals.items()}


def dvp_tables(logs, pos, season, before=None):
    """Defense vs position for one season, games before `before` (a date) when given: ({"dvp": {grp: {market: {team:
    rank}}}, "val": {grp: {market: {team: a game}}}, "n": {team: games}, "lg": {grp: {market: league a game}}}). A
    defense's game total for a group (centers, wingers, defensemen, goalies) is the sum over that group's players,
    averaged over its games; rank 1 allows the least. A goalie's saves "allowed" by a team are its shots on goal that
    were stopped: a team that shoots little ranks 1st."""
    per = defaultdict(float)
    games = defaultdict(set)
    cur = season_str(season)
    for pid, rows in logs.items():
        grp = GROUP.get(pos.get(pid))
        if not grp:
            continue
        for r in rows:
            if NR.season_of(r[COL["date"]]) != cur or (before and r[COL["date"]] >= before):
                continue
            opp, gid = r[COL["opp"]], r[COL["gid"]]
            games[opp].add(gid)
            for m in DVP_MARKETS[grp]:
                v = r[COL[MARKETS[m][1][0]]]
                if v is not None:
                    per[(opp, gid, grp, m)] += v
    tot = defaultdict(lambda: defaultdict(float))
    for (opp, gid, grp, m), v in per.items():
        tot[(grp, m)][opp] += v
    val, dvp, lg = defaultdict(dict), defaultdict(dict), defaultdict(dict)
    for (grp, m), by in tot.items():
        avgs = {t: round(v / len(games[t]), 2) for t, v in by.items() if games[t]}
        for t in games:
            avgs.setdefault(t, 0.0)
        val[grp][m] = avgs
        dvp[grp][m] = _rank(avgs)
        lg[grp][m] = round(st.mean(avgs.values()), 2) if avgs else None
    return {"dvp": dict(dvp), "val": dict(val), "n": {t: len(g) for t, g in games.items()}, "lg": dict(lg)}


def def_tables(tg, season, before=None):
    """({team: rank by goals allowed a game (1 = the fewest)}, {team: rank by shots in its games a game (pace, 1 = the
    most)}, {team: {"ga", "sa", "gf", "sf", "pace", "pp", "pk", "games"}})."""
    ga, pace, info = {}, {}, {}
    for t, rows in tg.items():
        rs = [r for r in rows if r["season"] == season and (not before or r["date"] < before) and r["ga"] is not None]
        if not rs:
            continue
        n = len(rs)
        f = lambda k: sum(r[k] or 0 for r in rs) / n
        ga[t], pace[t] = round(f("ga"), 2), round(f("sf") + f("sa"), 1)
        opp_pp = [(r2["pp_opp"] or 0, r2["ppg"] or 0) for r in rs for r2 in tg.get(r["opp"], []) if r2["gid"] == r["gid"]]
        ppo, ppg = sum(r["pp_opp"] or 0 for r in rs), sum(r["ppg"] or 0 for r in rs)
        k_o, k_g = sum(o for o, _ in opp_pp), sum(g for _, g in opp_pp)
        info[t] = {"ga": ga[t], "gf": round(f("gf"), 2), "sa": round(f("sa"), 1), "sf": round(f("sf"), 1), "pace": pace[t],
                   "pp": round(100 * ppg / ppo, 1) if ppo else None, "pk": round(100 * (1 - k_g / k_o), 1) if k_o else None,
                   "pp_opp": round(ppo / n, 2), "pim": round(f("pim"), 1), "hits": round(f("hits"), 1), "games": n}
    return _rank(ga), _rank(pace, low_first=False), info


def pos_ranks(logs, pos, season, min_games=5):
    """{grp: {market: [(a game, pid), ...] best first}} this season (players with min_games games)."""
    out = defaultdict(dict)
    by_grp = defaultdict(list)
    cur_s = season_str(season)
    for pid, rows in logs.items():
        grp = GROUP.get(pos.get(pid))
        if grp in DVP_MARKETS:
            cur = [r for r in rows if NR.season_of(r[COL["date"]]) == cur_s]
            if len(cur) >= min_games:
                by_grp[grp].append((pid, cur))
    for grp, mks in DVP_MARKETS.items():
        for m in mks:
            c = COL[MARKETS[m][1][0]]
            lst = [(round(st.mean(v), 2), pid) for pid, cur in by_grp[grp] for v in [[r[c] for r in cur if r[c] is not None]]
                   if len(v) >= min_games]
            out[grp][m] = sorted(lst, reverse=True)
    return out


def correlations(props, logs):
    """For each prop: the other props posted for the same game (his own other markets and his teammates'), ranked by
    |Pearson r| of the two stats over the games both played for the same team."""
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


def team_usage(logs, pos, team, season, roster_team):
    """The team's skaters this season: [{pid, pos, g, now, toi, ev, pp, sh, sog, att, share: {sog, pp}}] (a game each,
    his share of the team's shots and of its power-play time), the most ice time first."""
    cur_s = season_str(season)
    out = []
    for pid, rows in logs.items():
        if GROUP.get(pos.get(pid)) not in ("C", "W", "D"):
            continue
        rs = [r for r in rows if r[COL["team"]] == team and NR.season_of(r[COL["date"]]) == cur_s]
        if not rs:
            continue
        a = lambda k: round(sum(r[COL[k]] or 0 for r in rs) / len(rs), 2)
        sh = [r[COL["shot_share"]] for r in rs if r[COL["shot_share"]] is not None]
        pp = [r[COL["pp_share"]] for r in rs if r[COL["pp_share"]] is not None]
        out.append({"pid": pid, "pos": pos.get(pid), "g": len(rs), "now": roster_team.get(pid) == team, "toi": a("min"),
                    "ev": a("ev_min"), "pp": a("pp_min"), "sh": a("sh_min"), "sog": a("shots"), "att": a("attempts"),
                    "share": {"sog": round(st.mean(sh)) if sh else 0, "pp": round(st.mean(pp)) if pp else 0}})
    return sorted(out, key=lambda e: -e["toi"])


# ── roles: the page's Injuries › Roles, over a hockey season (82 games, as the NBA's): his last 3 games against his
# season average, a stat a game moving by at least ROLE_KEYS ──
ROLE_KEYS = (("min", 2.5), ("pp_min", 1.0), ("shots", 1.0), ("attempts", 1.5), ("pp_share", 20))
ROLE_RECENT = 3
ROLE_RECENT_FROM = 5         # until the median team has 5 games: his season so far against last season (20+ games there)
ROLE_LAST_MIN = 20
ROLE_SEASON_MIN = 5
lined_players = lambda q, season, cache=None, max_age=3600: _lined(q, season, cache, max_age)


def _lined(q, season, cache, max_age):
    """Players a book has posted a prop line for this season (Roles lists only these); cached an hour in `cache`."""
    if q is None:
        return None
    if cache is not None and cache.exists() and time.time() - cache.stat().st_mtime < max_age:
        try:
            return set(json.loads(cache.read_text()))
        except ValueError:
            pass
    out = {int(pid) for (pid,) in q.execute("SELECT DISTINCT pid FROM quotes WHERE seen_at >= ? AND pid IS NOT NULL",
                                            (f"{season}-08-01",))}
    if cache is not None:
        tmp = cache.with_name(cache.name + ".tmp")
        tmp.write_text(json.dumps(sorted(out)))
        os.replace(tmp, cache)
    return out


def roles_mode(team_gids):
    gp = sorted(len(v) for v in team_gids.values())
    return "recent" if gp and gp[len(gp) // 2] >= ROLE_RECENT_FROM else "season"


def roles(logs, pos, players, teams, season, lined=None):
    """The slate's skaters whose ice time, power-play time, shots, shot attempts or power-play share a game moved by at
    least ROLE_KEYS, in roles_mode's comparison: "season" (his games this season for his team against all of last
    season's, "was_team" set when he played most of them elsewhere) or "recent" (his last 3 games against his season
    average, the last 3 included); and the slate's goalies whose starts changed ([starts now, starts before, games
    before, games now]: "before" is the games ahead of his last 3). Each with the regular teammates who missed one of
    his team's last 3 games. lined: players a book has posted a prop for this season (None: everyone). {"rows": [...]
    the biggest ice-time move first, "thresholds", "mode"}."""
    cur_s, last_s = season_str(season), season_str(season - 1)
    played, gids = defaultdict(set), defaultdict(set)
    for pid, rows in logs.items():
        for r in rows:
            played[(r[COL["team"]], r[COL["gid"]])].add(pid)
            if NR.season_of(r[COL["date"]]) == cur_s:
                gids[r[COL["team"]]].add((r[COL["date"]], r[COL["gid"]]))
    team_gids = {t: [g for _, g in sorted(v)] for t, v in gids.items()}
    mode = roles_mode(team_gids)
    mean = lambda vals, k: round(sum(vals) / len(vals)) if k == "pp_share" else round(sum(vals) / len(vals), 1)
    rows_out = []
    for pid, rows in logs.items():
        pl = players.get(pid) or {}
        team, grp = pl.get("team"), GROUP.get(pos.get(pid))
        if not grp or team not in teams or (lined is not None and pid not in lined):
            continue
        cur = [r for r in rows if NR.season_of(r[COL["date"]]) == cur_s and r[COL["team"]] == team]
        tg = team_gids.get(team) or []
        if grp == "G":                                       # a goalie's role is his starts
            if len(cur) < 1 or len(tg) < ROLE_RECENT + 1:
                continue
            recent_g = set(tg[-ROLE_RECENT:])
            starts = lambda gs: sum(1 for r in cur if r[COL["gid"]] in gs and r[COL["starter"]])
            now, before = starts(recent_g), starts(set(tg[:-ROLE_RECENT]))
            n_before = len(tg) - ROLE_RECENT
            if (now >= 2 and before <= n_before / 3) or (now == 0 and before >= n_before * 2 / 3 and n_before >= 2):
                toi = {r[COL["gid"]]: r[COL["min"]] or 0 for r in cur}          # his ice time a team game, 0 when he sat
                per = lambda gs: round(sum(toi.get(g, 0) for g in gs) / len(gs), 1) if gs else None
                mins = [per(tg[-ROLE_RECENT:]), per(tg[:-ROLE_RECENT])]
                rows_out.append({"pid": pid, "name": pl.get("name"), "team": team, "pos": "G",
                                 "st": {k: (mins if k == "min" else None) for k, _ in ROLE_KEYS}, "min": mins, "usg": [None, None],
                                 "out": [], "starts": [now, before, n_before, ROLE_RECENT], "was_team": None})
            continue
        last3 = tg[-(ROLE_RECENT + 1):]
        if len(cur) < ROLE_RECENT or any(r[COL["gid"]] not in last3 for r in cur[-ROLE_RECENT:]):
            continue                                         # not playing lately: a return or an absence, not a role
        was_team = None
        if mode == "recent":
            if len(cur) < ROLE_SEASON_MIN:
                continue
            recent, base = cur[-ROLE_RECENT:], cur
        else:
            recent = cur
            base = [r for r in rows if NR.season_of(r[COL["date"]]) == last_s]
            if len(base) < ROLE_LAST_MIN:
                continue
            top = Counter(r[COL["team"]] for r in base).most_common(1)[0][0]
            was_team = top if top != team else None
        stt = {}
        for k, _ in ROLE_KEYS:
            now = [r[COL[k]] for r in recent if r[COL[k]] is not None]
            was = [r[COL[k]] for r in base if r[COL[k]] is not None]
            stt[k] = [mean(now, k), mean(was, k)] if len(now) >= min(ROLE_RECENT, len(recent)) and len(now) and len(was) >= 3 else None
        if not any(v and abs(v[0] - v[1]) >= th for (k, th) in ROLE_KEYS for v in [stt[k]]):
            continue
        recent_g = tg[-ROLE_RECENT:]
        regs = []
        for mate, mrows in logs.items():
            mg = GROUP.get(pos.get(mate))
            if mate == pid or mg not in REG_MIN or (players.get(mate) or {}).get("team") != team:
                continue
            mins = [r[COL["min"]] for r in mrows if NR.season_of(r[COL["date"]]) == cur_s and r[COL["team"]] == team
                    and r[COL["gid"]] not in recent_g and r[COL["min"]] is not None]
            if len(mins) >= 2 and sum(mins) / len(mins) >= REG_MIN[mg] and any(mate not in played.get((team, g), ()) for g in recent_g):
                regs.append((-sum(mins) / len(mins), (players.get(mate) or {}).get("name") or ""))
        rows_out.append({"pid": pid, "name": pl.get("name"), "team": team, "pos": pos.get(pid), "st": stt,
                         "min": stt["min"] or [None, None], "usg": [None, None], "out": [n for _, n in sorted(regs)],
                         "starts": [0, 0, 0, ROLE_RECENT], "was_team": was_team})
    rows_out.sort(key=lambda e: -abs(e["min"][0] - e["min"][1]) if e["min"][0] is not None else 0)
    return {"rows": rows_out, "thresholds": dict(ROLE_KEYS), "mode": mode}


def vs_rows(logs, pos, teams, names):
    """{defense: [[date, gid, offense, pid, name, group, {market: value}], ...]} — each slate team's last VS_GAMES games
    against, the skaters (and goalies) who played it, newest first."""
    out = defaultdict(list)
    want = set(teams)
    for pid, rows in logs.items():
        grp = GROUP.get(pos.get(pid))
        if not grp:
            continue
        cols = [(m, COL[MARKETS[m][1][0]]) for m in DVP_MARKETS[grp]]          # one log column a market (no dict a row)
        for r in rows:
            if r[COL["opp"]] not in want or not r[COL["min"]]:
                continue
            out[r[COL["opp"]]].append([r[COL["date"]], r[COL["gid"]], r[COL["team"]], pid, names.get(pid) or str(pid), grp,
                                       {**{m: r[c] for m, c in cols}, "min": r[COL["min"]]}])
    res = {}
    for t, rs in out.items():
        keep = {g for _, g in sorted({(r[0], r[1]) for r in rs}, reverse=True)[:VS_GAMES]}
        res[t] = sorted([r for r in rs if r[1] in keep], key=lambda r: (r[0], r[6].get("points") or 0, r[6].get("shots") or 0),
                        reverse=True)
    return res


BOX_COLS = ("min", "goals", "assists", "points", "shots", "hits", "blocks", "ppp", "pm", "pim", "pp_min", "saves", "sa")


def box_files(logs, pos, names, sched, want=None):
    """{gid: box} for every game in the logs (or only the gids in `want`): each team's players with a stat line
    (BOX_COLS): forwards, then defensemen, then goalies, the most ice time first; the score."""
    games = {g["gid"]: g for g in sched}
    by = defaultdict(lambda: defaultdict(list))
    for pid, rows in logs.items():
        for r in rows:
            if want is not None and r[COL["gid"]] not in want:
                continue
            by[r[COL["gid"]]][r[COL["team"]]].append([pid, names.get(pid) or str(pid), pos.get(pid) or ""] + [r[COL[c]] for c in BOX_COLS])
    out = {}
    order = {"C": 0, "L": 0, "R": 0, "D": 1, "G": 2}
    for gid, teams in by.items():
        g = games.get(gid)
        if not g:
            continue
        out[gid] = {"date": g["date"], "status": "Final", "cols": list(BOX_COLS),
                    "teams": [{"tri": t, "pts": g["away_score"] if t == g["away"] else g["home_score"],
                               "players": sorted(teams.get(t, []), key=lambda x: (order.get(x[2], 3), -(x[3] or 0)))}
                              for t in (g["away"], g["home"])]}
    return out


def live_box_files(boxes, live, games, players):
    """{gid: box} for the slate's games under way (or over, before the logs have them), in box_files' shape, from the
    NHL's live box score: the page's box score sheet while the game is on."""
    out = {}
    order = {"C": 0, "L": 0, "R": 0, "D": 1, "G": 2}
    for g in games:
        lv, bx = live.get(g["gid"]) or {}, boxes.get(g["gid"])
        if lv.get("state") not in ("live", "final") or not bx:
            continue
        by = defaultdict(list)
        for pid, v in bx.items():
            name = (players.get(pid) or {}).get("name") or v.get("_name") or str(pid)
            by[v.get("_team")].append([pid, name, v.get("_pos") or ""] + [v.get(c) for c in BOX_COLS])
        sc = lv.get("score") or [None, None]
        out[g["gid"]] = {"date": g["date"], "status": lv.get("label") or ("Final" if lv["state"] == "final" else "Live"),
                         "cols": list(BOX_COLS), "live": lv["state"] == "live",
                         "teams": [{"tri": t, "pts": sc[i], "players": sorted(by.get(t, []), key=lambda x: (order.get(x[2], 3), -(x[3] or 0)))}
                                   for i, t in enumerate((g["away"], g["home"]))]}
    return out


def gains(logs, pos, team, played, gl, pid):
    """The teammates who got MIN_GAIN+ more minutes a game in the team's games without him (2+ of them, this season and
    last, games before the first he played for the team left out): [{pid, gain, mpg, n, pp}] (pp: the power-play
    minutes they gained)."""
    first = min((d for d, gid in gl if gid in played), default=None)
    if first is None:
        return []
    with_g = {gid for d, gid in gl if gid in played}
    wo_g = {gid for d, gid in gl if gid not in played and d >= first}
    if len(wo_g) < MIN_WITHOUT or len(with_g) < MIN_WITHOUT:
        return []
    grp = GROUP.get(pos.get(pid))
    out = []
    for y, rows in logs.items():
        yg = GROUP.get(pos.get(y))
        if y == pid or yg not in ("C", "W", "D") or (grp in ("C", "W", "D") and (yg == "D") != (grp == "D")):
            continue                                         # forwards replace forwards, defensemen defensemen
        mine = {r[COL["gid"]]: (r[COL["min"]] or 0, r[COL["pp_min"]] or 0) for r in rows if r[COL["team"]] == team}
        nw = [mine[g] for g in with_g if g in mine]
        no = [mine[g] for g in wo_g if g in mine]
        if len(nw) < MIN_WITHOUT or len(no) < MIN_WITHOUT:
            continue
        gain = sum(x[0] for x in no) / len(no) - sum(x[0] for x in nw) / len(nw)
        if gain >= MIN_GAIN:
            out.append({"pid": y, "gain": round(gain, 1), "mpg": round(sum(x[0] for x in no) / len(no), 1), "n": len(no),
                        "pp": round(sum(x[1] for x in no) / len(no) - sum(x[1] for x in nw) / len(nw), 1)})
    out.sort(key=lambda e: -e["gain"])
    return out[:3]


def moneyline(q, gids):
    """{gid: {"home", "away"} no-vig win chances} from FanDuel's latest moneyline (nhl_lines.game_lines)."""
    out = {}
    if q is None:
        return out
    for gid in gids:
        try:
            r = {side: odds for side, odds in q.execute(
                "SELECT side, odds FROM game_lines WHERE gid=? AND market='moneyline' AND side IN ('home', 'away') "
                "ORDER BY seen_at", (gid,))}
        except sqlite3.OperationalError:
            return out
        if r.get("home") and r.get("away"):
            p = NR.no_vig(r["home"], r["away"])
            if p is not None:
                out[gid] = {"home": round(p, 3), "away": round(1 - p, 3), "home_odds": r["home"], "away_odds": r["away"]}
    return out


def slate(sched, now, live_of):
    """(dates, games) on the page: today and tomorrow (US Eastern, rolled at SLATE_ROLL_H), today dropped once all of its
    games are final or postponed (nba_research's rule)."""
    base = (now.astimezone(C.ET) - dt.timedelta(hours=SLATE_ROLL_H)).date()
    day = lambda k: (base + dt.timedelta(days=k)).isoformat()
    cand = [g for g in sched if g["date"] in (day(0), day(1), day(2))]
    live = live_of(cand)
    first = [g for g in cand if g["date"] == day(0)]
    k0 = 1 if first and all(live[g["gid"]]["state"] in ("final", "postponed") for g in first) else 0
    dates = [day(k0), day(k0 + 1)]
    return dates, [g for g in cand if g["date"] in dates], live


# ── the payload ────────────────────────────────────────────────────────────────────────────────────────────────
def build(now=None, sched=None, lines=None, stats=None, onoff=None, get=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    season = C.season_of(now.astimezone(C.ET).date())
    if sched is None:
        sched = C.schedule(season, max_age=600) + C.schedule(season - 1, max_age=86400)
    dates, games, live = slate(sched, now, lambda cand: live_state(cand, get))
    games.sort(key=lambda g: (g["utc"], g["gid"]))
    gids = [g["gid"] for g in games]
    q, scon, ocon = NR._ro(lines or LINES), NR._ro(stats or STATS), NR._ro(onoff or ONOFF)
    players = players_of(scon)
    all_names = names_of(scon)
    boxes = live_boxes(live, get)
    quotes, names, newest = NR.book_quotes(q, gids, MARKETS)
    nowu = now.astimezone(dt.timezone.utc).replace(tzinfo=None)
    started = [g["gid"] for g in games if dt.datetime.fromisoformat(g["utc"]) <= nowu]
    cb, cnames = NR.closing_boards(q, started, cache=CLOSE_BOARDS if lines is None else Path(lines).with_name("nhl_close.json"),
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
    props, found = [], C.searched()
    for (gid, pid, market), books in sorted(quotes.items()):
        g = gmap[gid]
        team = (players.get(pid) or {}).get("team")
        if team not in (g["home"], g["away"]) and logs.get(pid):
            team = logs[pid][-1][COL["team"]]
        if team not in (g["home"], g["away"]):
            team = found.get(pid)                            # a call-up no roster lists yet: the team the search found
        if team not in (g["home"], g["away"]):
            team = None
        if team and pid not in players:
            players[pid] = {"name": names.get((gid, pid)) or "", "team": team, "pos": lpos.get(pid), "jersey": None,
                            "headshot": C.headshot(season, team, pid)}
        elif team and players[pid].get("team") != team:      # traded or called up since: his face is filed under the new team
            players[pid] = {**players[pid], "team": team, "headshot": C.headshot(season, team, pid)}
        main = (books.get("fd") or {}).get("main")
        if main is None:
            main = (books.get("dk") or {}).get("main")
        if main is None:                                     # a ladder only (DraftKings' power-play points): its first rung
            rungs = sorted({r[0] for b in books.values() for r in b["rungs"]})
            main = 0.5 if 0.5 in rungs else (rungs[0] if rungs else None)
        props.append({"id": f"{gid}|{pid}|{market}", "gid": gid, "pid": pid, "market": market,
                      "player": names.get((gid, pid)) or (players.get(pid) or {}).get("name") or "", "team": team,
                      "opp": (g["away"] if team == g["home"] else g["home"]) if team else None,
                      "home": team == g["home"] if team else None, "books": books, "main": main,
                      **({"closed": True} if (gid, pid, market) in closed else {})})
    # matchup context: this season's defense vs position before the slate (last season's where a team has too few games)
    first = dates[0]
    cur_t = dvp_tables(logs, pos, season, before=first)
    prev_t = dvp_tables(logs, pos, season - 1)
    tg = team_games(scon, seasons)
    d_rank, p_rank, d_info = def_tables(tg, season, before=first)
    pd_rank, pp_rank, pd_info = def_tables(tg, season - 1)
    teams_n = len(C.TEAMS)
    use = lambda t: (cur_t["n"].get(t) or 0) >= RANK_MIN
    rk_cur = {"teams": teams_n, "dvp": {}, "val": {}, "lg": cur_t["lg"], "def": {}, "pace": {}, "n": cur_t["n"]}
    for grp, mk in cur_t["dvp"].items():
        rk_cur["dvp"][grp], rk_cur["val"][grp] = {}, {}
        for m, tbl in mk.items():
            rk_cur["dvp"][grp][m] = {t: (tbl.get(t) if use(t) else (prev_t["dvp"].get(grp, {}).get(m, {}).get(t) or tbl.get(t)))
                                     for t in C.TEAMS if tbl.get(t) or prev_t["dvp"].get(grp, {}).get(m, {}).get(t)}
            rk_cur["val"][grp][m] = cur_t["val"][grp][m]
    rk_cur["def"] = {t: d_rank.get(t) if use(t) else pd_rank.get(t) for t in C.TEAMS if d_rank.get(t) or pd_rank.get(t)}
    rk_cur["pace"] = {t: p_rank.get(t) if use(t) else pp_rank.get(t) for t in C.TEAMS if p_rank.get(t) or pp_rank.get(t)}
    ranks = {d: rk_cur for d in dates}
    ranks[season_str(season - 1)] = {"teams": teams_n, "dvp": prev_t["dvp"], "val": prev_t["val"], "lg": prev_t["lg"],
                                     "def": pd_rank, "pace": pp_rank, "n": prev_t["n"]}
    pr, pr_prev = pos_ranks(logs, pos, season), pos_ranks(logs, pos, season - 1)
    for p in props:
        grp = GROUP.get(pos.get(p["pid"]))
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
                    ctx.update(**{"def": round(v / lgv, 3), "allow": v, "lg": lgv})
        for label, table in ((season, pr), (season - 1, pr_prev)):
            lst = (table.get(grp) or {}).get(p["market"]) or []
            at = next((i for i, (_, pid_) in enumerate(lst) if pid_ == p["pid"]), None)
            if at is not None:
                ctx.update(pos_rank=at + 1, pos_n=len(lst), pos_season=season_str(label))
                break
        p["ctx"] = ctx
        p["flag"] = None
        lv = live.get(p["gid"], {})
        if lv.get("state") in ("live", "final"):
            bx = (boxes.get(p["gid"]) or {}).get(p["pid"])
            v = bx.get(MARKETS[p["market"]][1][0]) if bx else None
            if v is None and lv["state"] == "live":
                v = 0                                        # not in the box score yet: nothing so far
            if v is not None:
                p["live"] = {"value": v, "frac": lv.get("frac", 0), "min": (bx or {}).get("min")}
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
    lines_ = lines_of(ocon, slate_teams)
    inj = injuries(players, get)
    gl_ = goalies(games, players, get)
    by_team = defaultdict(list)
    for pid, rows in logs.items():
        for r in rows:
            by_team[r[COL["team"]]].append((r[COL["date"]], r[COL["gid"]]))
    team_gids = {t: sorted(set(by_team[t])) for t in slate_teams}
    published = max((e.get("published") or "" for e in inj.values()), default="") or None
    report_meta = {d: {"published": published} for d in dates} if inj else {}
    injuries_out, absences, inj_report = {}, {}, {}
    cur_s = season_str(season)
    for g in games:
        for t in (g["home"], g["away"]):
            gl = team_gids.get(t, [])
            lastn = {gid for _, gid in [x for x in gl if x[0] < g["date"]][-FRESH_GAMES:]}
            L = lines_.get(t) or {}
            top6 = {x for ln in (L.get("F") or [])[:2] for x in ln} | {x for ln in (L.get("D") or [])[:2] for x in ln}
            listed, ab = [], []
            for pid, e in inj.items():
                if roster_team.get(pid) != t or not e.get("status"):
                    continue
                mine = [r for r in logs.get(pid, []) if r[COL["team"]] == t]
                cur_r = [r for r in mine if NR.season_of(r[COL["date"]]) == cur_s]
                use_r = cur_r or mine
                mn = [r[COL["min"]] for r in use_r if r[COL["min"]] is not None]
                mpg = round(sum(mn) / len(mn), 1) if mn else None
                played = [r[COL["gid"]] for r in mine]
                fresh = bool(lastn & set(played))
                missed = sum(1 for d, gid in gl if NR.season_of(d) == cur_s and gid not in set(played) and d < g["date"]
                             and (not cur_r or d >= cur_r[0][COL["date"]]))
                grp = GROUP.get(pos.get(pid))
                reg = grp == "G" and sum(1 for r in cur_r if r[COL["starter"]]) * 2 >= max(1, len(cur_r)) or \
                    grp in REG_MIN and (mpg or 0) >= REG_MIN[grp]
                if played:
                    ent = {"pid": pid, "name": (players.get(pid) or {}).get("name"), "pos": pos.get(pid) or "",
                           "status": e["status"], "reason": ("IR · " if e.get("long") and (e.get("raw") or "").startswith(("Injured", "Long")) else "") + (e.get("reason") or ""),
                           "mpg": mpg, "gp": len(use_r), "season": NR.season_of(use_r[-1][COL["date"]]) if use_r else None,
                           "starter": bool(reg), "missed": missed, "starts": None, "minutes": [], "fresh": fresh,
                           "practice": None, "long": e.get("long", False)}
                    if grp in REG_MIN and (mpg or 0) >= ROT_MIN:
                        ent["minutes"] = [dict(x, name=(players.get(x["pid"]) or {}).get("name") or str(x["pid"]))
                                          for x in gains(logs, pos, t, set(played), gl, pid)]
                        if pid in top6:                      # a top-six forward or top-four defenseman: who moves up
                            nxt = next((x["pid"] for x in ent["minutes"] if x["pid"] not in top6), None)
                            if nxt is not None:
                                ent["starts"] = {"pid": nxt, "name": (players.get(nxt) or {}).get("name"), "k": None, "n": None,
                                                 "how": "depth"}
                    listed.append(ent)
                if e["status"] in OUT_LIKE and played:
                    ab.append({"pid": pid, "played": played, "since": mine[0][COL["date"]] if mine else None,
                               "status": e["status"], "fresh": fresh, "name": (players.get(pid) or {}).get("name")})
            order = ("Out", "Day-To-Day")
            listed.sort(key=lambda x: (order.index(x["status"]) if x["status"] in order else 2, -(x["mpg"] or 0)))
            inj_report[f"{g['date']}|{t}"] = {"listed": True, "published": published, "players": listed}
            absences[f"{g['date']}|{t}"] = ab
    for p in props:
        d = gmap[p["gid"]]["date"]
        e = inj.get(p["pid"])
        injuries_out[f"{d}|{p['pid']}"] = {
            "official": {"status": e["status"], "reason": e.get("reason"), "published": e.get("published"), "practice": None,
                         "long": e.get("long")} if e and e.get("status") else None,
            "listed_team": bool(inj), "news": (e or {}).get("news", [])}
    # with / without: every current teammate who has played for the team (two seasons): the skaters by ice time, then
    # the goalies (who play the whole game) by games
    mates = {}
    for t in slate_teams:
        gl = [gid for _, gid in team_gids.get(t, [])]
        if not gl:
            continue
        idx = {gid: i for i, gid in enumerate(gl)}
        ms = []
        for pid, rows in logs.items():
            if roster_team.get(pid) != t or not GROUP.get(pos.get(pid)):
                continue
            mine = [r for r in rows if r[COL["team"]] == t]
            if not mine:
                continue
            on = ["0"] * len(gl)
            for r in mine:
                on[idx[r[COL["gid"]]]] = "1"
            mn = [r[COL["min"]] for r in mine if r[COL["min"]] is not None]
            ms.append({"pid": pid, "name": (players.get(pid) or {}).get("name"), "since": mine[0][COL["date"]],
                       "on": "".join(on), "mpg": round(sum(mn) / len(mn), 1) if mn else 0, "gp": len(mine)})
        sk = sorted((m for m in ms if pos.get(m["pid"]) != "G"), key=lambda m: -m["mpg"])
        gk = sorted((m for m in ms if pos.get(m["pid"]) == "G"), key=lambda m: -m["gp"])
        mates[t] = {"gids": gl, "mates": sk[:27] + gk[:3]}
    corr = correlations(props, logs)
    extra = {a["pid"] for v in absences.values() for a in v}
    out_players = {}
    for pid in pids | extra:
        pl = players.get(pid) or {}
        out_players[str(pid)] = {"name": pl.get("name") or next((p["player"] for p in props if p["pid"] == pid), ""),
                                 "pos": pos.get(pid) or "", "logs": logs.get(pid, []), "headshot": pl.get("headshot"),
                                 "jersey": pl.get("jersey")}
    usage = {t: team_usage(logs, pos, t, season, roster_team) for t in slate_teams}
    for lst in usage.values():
        for e in lst:
            e["name"] = (players.get(e["pid"]) or {}).get("name") or str(e["pid"])
    teams_info = {t: dict(d_info.get(t) or pd_info.get(t) or {}, sa_rank=None) for t in slate_teams}
    sa_rank = _rank({t: v["sa"] for t, v in d_info.items()}) if d_info else {}
    for t in slate_teams:
        teams_info[t]["sa_rank"] = sa_rank.get(t)
        teams_info[t]["games"] = (d_info.get(t) or {}).get("games", 0)
    glines = NR.game_lines(q, gids)
    ml = moneyline(q, gids)
    spots = NR.schedule_spots([dict(g, date_et=g["date"], status_text="PPD" if g["state"] == "postponed" else "")
                               for g in sched if g["season"] == season], gids)
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
    depth = {}
    for t in slate_teams:
        L = lines_.get(t)
        if L:
            depth[t] = {k: [[[pid, (players.get(pid) or {}).get("name") or all_names.get(pid) or ""] for pid in unit] for unit in v]
                        if k in ("F", "D") else [[pid, (players.get(pid) or {}).get("name") or all_names.get(pid) or ""] for pid in v]
                        for k, v in L.items() if k in ("F", "D", "PP1", "PP2", "G")}
            depth[t]["date"] = L.get("date")
            depth[t]["toi"] = L.get("toi") or {}
    out = {
        "sport": "nhl", "generated_at": stamp, "season": cur_s, "dates": dates, "log_cols": list(LOG_COLS),
        "hist_t0": t0.isoformat() if t0 else None,
        "markets": {k: v[0] for k, v in MARKETS.items()},
        "sources": {"books": fresh, "report": report_meta,
                    "logs": {"through": max((r[0] for v in logs.values() for r in v), default=None),
                             "seasons": [season_str(season - 1), cur_s], "built_at": meta.get("built_at")},
                    "matchup": {"available": bool(cur_t["n"])}, "game_lines": {"games": len(glines)}},
        "games": [{"gid": g["gid"], "date": g["date"], "tip": g["utc"], "away": g["away"], "home": g["home"],
                   "lines": dict(glines.get(g["gid"]) or {}, **({"ml": ml[g["gid"]]} if g["gid"] in ml else {})) or None,
                   "spots": spots.get(g["gid"]), "goalies": gl_.get(g["gid"]),
                   **{k: v for k, v in live.get(g["gid"], {}).items() if k != "ppp"}} for g in games],
        "props": props, "players": out_players, "injuries": injuries_out, "flags": [],
        "absences": absences, "related": corr, "inj_report": inj_report, "mates": mates, "lineups": {}, "depth": depth,
        "ranks": ranks, "proj_players": {}, "proj_meta": {"none": True}, "usage": usage, "teams": teams_info,
        "roles": roles(logs, pos, players, set(slate_teams), season, lined_players(q, season, LINED if lines is None else None)),
        "vs": vs_rows(logs, pos, slate_teams, all_names), "heads": {},
    }
    # every player the page may show a face for (injury lists, lines, usage, roles, the vs table, mates): his headshot
    shown = {e["pid"] for v in inj_report.values() for e in v["players"]} | {x["pid"] for v in inj_report.values() for e in v["players"] for x in e["minutes"]}
    shown |= {pid for L in lines_.values() for k in ("F", "D") for u in L.get(k) or [] for pid in u}
    shown |= {pid for L in lines_.values() for k in ("PP1", "PP2", "G") for pid in L.get(k) or []}
    shown |= {e["pid"] for v in usage.values() for e in v} | {r["pid"] for r in out["roles"]["rows"]}
    shown |= {r[3] for v in out["vs"].values() for r in v} | {m["pid"] for v in mates.values() for m in v["mates"]}
    shown |= {x["pid"] for v in gl_.values() for x in v.values() if x.get("pid")}
    out["heads"] = {str(pid): (players.get(pid) or {}).get("headshot") for pid in shown - pids if (players.get(pid) or {}).get("headshot")}
    out["_boxes"] = lambda want: box_files(logs, pos, all_names, sched, want)
    out["_box_dates"] = {r[COL["gid"]]: r[COL["date"]] for v in logs.values() for r in v}
    out["_live_boxes"] = {gid: b for gid, b in live_box_files(boxes, live, games, players).items() if gid not in out["_box_dates"]}
    for c in (q, scon, ocon):
        if c is not None:
            c.close()
    return out


def write(out_dir, payload, today=None):
    """Atomic writes of nhl_props.json and the box scores (docs/nhlbox/{gid}.json: new games, the last few days' again,
    and the games under way from the live box score). The page itself is written by nba_research."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    make, dates = payload.pop("_boxes", None), payload.pop("_box_dates", {}) or {}
    lives = payload.pop("_live_boxes", {}) or {}
    bd = out_dir / "nhlbox"
    bd.mkdir(exist_ok=True)
    today = today or dt.date.today()
    want = {gid for gid, d in dates.items()
            if not (bd / f"{gid}.json").exists() or (today - dt.date.fromisoformat(d)).days <= BOX_FRESH_DAYS}
    for gid, b in list((make(want) if make and want else {}).items()) + list(lives.items()):
        tmp = bd / f".{gid}.json.tmp"
        tmp.write_text(json.dumps(b, separators=(",", ":")))
        os.replace(tmp, bd / f"{gid}.json")
    tmp = out_dir / ".nhl_props.json.tmp"
    tmp.write_text(json.dumps(payload, separators=(",", ":"), default=str))
    os.replace(tmp, out_dir / "nhl_props.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.environ.get("NBA_RESEARCH_OUT", str(HERE / "docs")))
    a = ap.parse_args()
    t_ = time.time()
    pl = build()
    write(a.out, pl)
    print(f"nhl_research: {', '.join(pl['dates'])} · {len(pl['props'])} props · {len(pl['games'])} games · "
          f"{len(pl['players'])} players · {time.time() - t_:.0f}s -> {a.out}")
    # skip the interpreter's teardown: on the swapping VM, freeing every object read its pages back in and held the
    # build's lock for minutes after the page was written (2026-11-02)
    sys.stdout.flush()
    os._exit(0)
