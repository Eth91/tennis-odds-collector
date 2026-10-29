#!/usr/bin/env python3
"""NFL game logs for Pickz: nflverse's weekly stats, snap counts and play by play -> nfl_stats.sqlite (read by nfl_research).

One row per player per game, this season and last, with everything a prop is graded on and the usage behind it:
    logs        the box score (passing, rushing, receiving, kicking, the defense's sacks and tackles), the snaps he played
                and his share of them, his targets' share and air yards, and from the play by play what the weekly file
                lacks: his longest completion / rush / reception, red-zone targets and carries, deep (20+ air yard) targets.
                Each row carries its game's context: home, his team's final margin, days of rest, his team's spread and
                the total (nflverse's closing lines).
    players     name, team, position, headshot, ESPN id (the live box scores and injuries key on it), depth chart spot
    team_games  per team per game: offensive plays, passes, runs, the neutral-script pass rate, seconds a play, points
    rush_dir    where his carries went (left end ... right end) and what each defense allowed there, by season
    tgt_tree    where his targets went (behind the line / short / intermediate / deep x left / middle / right), by season
    meta        when it was built and the last week of each file

Rebuilt whole on every run (two seasons is ~30k rows; a minute on the VM). Last season's files are cached for a week, this
season's for CUR_MAX_AGE (nflverse refreshes them through the week, the weekly stats the morning after a game).

    python3 nfl_stats.py              # this season and last
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import sqlite3
from collections import defaultdict
from pathlib import Path

import nfl_common as C

HERE = Path(__file__).resolve().parent
DB = Path(os.environ.get("NFL_STATS_DB", HERE / "nfl_stats.sqlite"))
CUR_MAX_AGE, OLD_MAX_AGE = 3600, 7 * 86400
LOG_COLS = ("date", "gid", "week", "team", "opp", "home", "margin", "rest", "spr", "tot", "snaps", "snap_pct",
            "pass_att", "pass_comp", "pass_yds", "pass_tds", "pass_int", "sacked", "long_comp",
            "rush_att", "rush_yds", "rush_tds", "long_rush", "rush_share",
            "targets", "rec", "rec_yds", "rec_tds", "long_rec", "air_yds", "yac", "tgt_share", "air_share",
            "rz_tgt", "rz_rush", "deep_tgt", "td", "fg_made", "fg_att", "pat_made", "kick_pts", "sacks", "tackles")
# rush direction (nflverse run_location x run_gap) and the target tree's cells
DIRS = ("le", "lt", "lg", "m", "rg", "rt", "re")
DEPTHS = ("bl", "sh", "in", "dp")              # behind the line (<0 air yards), 0-9, 10-19, 20+
LOCS = ("l", "m", "r")
OFF_POS = {"QB", "RB", "FB", "WR", "TE", "K"}
DEF_GROUPS = {"DL", "LB", "DB"}

DDL = f"""
DROP TABLE IF EXISTS logs; DROP TABLE IF EXISTS players; DROP TABLE IF EXISTS team_games;
DROP TABLE IF EXISTS rush_dir; DROP TABLE IF EXISTS tgt_tree; DROP TABLE IF EXISTS meta; DROP TABLE IF EXISTS names;
CREATE TABLE logs (season INTEGER, pid INTEGER, pos TEXT, {", ".join(c + (" TEXT" if c in ("date", "gid", "team", "opp") else " REAL") for c in LOG_COLS)},
                   PRIMARY KEY (pid, gid));
CREATE INDEX logs_season ON logs (season, team);
CREATE TABLE players (pid INTEGER PRIMARY KEY, name TEXT, team TEXT, pos TEXT, headshot TEXT, espn TEXT, jersey TEXT,
                      depth_pos TEXT, status TEXT);
CREATE TABLE team_games (season INTEGER, gid TEXT, week INTEGER, date TEXT, team TEXT, opp TEXT, home INTEGER, plays INTEGER,
                         pass INTEGER, rush INTEGER, neutral_pass REAL, sec_play REAL, pts REAL, opp_pts REAL,
                         PRIMARY KEY (team, gid));
CREATE TABLE rush_dir (season INTEGER, kind TEXT, key TEXT, cells TEXT, PRIMARY KEY (season, kind, key));
CREATE TABLE tgt_tree (season INTEGER, pid INTEGER, cells TEXT, PRIMARY KEY (season, pid));
CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE names (pid INTEGER PRIMARY KEY, name TEXT, pos TEXT);   -- everyone in the logs, gone or not
"""


def _n(x):
    if x is None or x == "" or x == "NA":
        return None
    try:
        v = float(x)
    except ValueError:
        return None
    return int(v) if v.is_integer() else v


def _z(x):
    v = _n(x)
    return 0 if v is None else v


def _age(season, cur):
    return CUR_MAX_AGE if season == cur else OLD_MAX_AGE


WEEKLY_KEEP = ("player_id", "player_display_name", "player_name", "position", "position_group", "season_type", "game_id",
               "team", "completions", "attempts", "passing_yards", "passing_tds", "passing_interceptions", "sacks_suffered",
               "carries", "rushing_yards", "rushing_tds", "receptions", "targets", "receiving_yards", "receiving_tds",
               "receiving_air_yards", "receiving_yards_after_catch", "target_share", "air_yards_share", "special_teams_tds",
               "fg_made", "fg_att", "pat_made", "def_sacks", "def_tackles_solo", "def_tackle_assists")


def weekly(season, cur):
    """nflverse weekly player stats, only the columns used (renamed stats_player in 2025; the old player_stats file
    serves earlier seasons)."""
    try:
        it = C.iter_rows(f"stats_player/stats_player_week_{season}.csv", _age(season, cur))
        first = next(it)
    except Exception:
        it = C.iter_rows(f"player_stats/player_stats_{season}.csv", _age(season, cur))
        first = next(it)
    keep = lambda r: {k: r.get(k) for k in WEEKLY_KEEP}
    return [keep(first)] + [keep(r) for r in it]


def pbp_rows(season, cur):
    """(header index, rows) of a season's play by play, streamed from the gzip with csv.reader (DictReader over 372
    columns is slow; the whole file decompressed in memory cost the VM 600 MB)."""
    f = C.cached(f"pbp/play_by_play_{season}.csv.gz", _age(season, cur))
    fh = gzip.open(f, "rt", encoding="utf-8-sig", newline="")
    rd = csv.reader(fh)
    hdr = next(rd)
    return {c: i for i, c in enumerate(hdr)}, rd


def from_pbp_cached(season, cur):
    """from_pbp, with a past season's results kept in the cache beside its file (a finished season's file changes
    rarely; its parse is most of a build's minute)."""
    if season == cur:
        return from_pbp(season, cur)
    src = C.cached(f"pbp/play_by_play_{season}.csv.gz", _age(season, cur))
    f = C.CACHE / f"derived_pbp_{season}.json"
    try:
        j = json.loads(f.read_text())
        if j.get("mtime") == src.stat().st_mtime:
            per = {(int(k.split("|")[0]), k.split("|")[1]): v for k, v in j["per"].items()}
            team = {(k.split("|")[0], k.split("|")[1]): v for k, v in j["team"].items()}
            rdir = {(k.split("|")[0], k.split("|")[1]): v for k, v in j["rdir"].items()}
            tree = {int(k): v for k, v in j["tree"].items()}
            return per, team, rdir, tree
    except (OSError, ValueError, KeyError):
        pass
    per, team, rdir, tree = from_pbp(season, cur)
    f.write_text(json.dumps({"mtime": src.stat().st_mtime, "per": {f"{a}|{b}": v for (a, b), v in per.items()},
                             "team": {f"{a}|{b}": v for (a, b), v in team.items()},
                             "rdir": {f"{a}|{b}": {d: c for d, c in v.items()} for (a, b), v in rdir.items()},
                             "tree": {str(k): dict(v) for k, v in tree.items()}}))
    return per, team, rdir, tree


def from_pbp(season, cur):
    """Per (pid, gid): longest completion / rush / reception, red-zone targets and carries, deep targets; per team-game:
    plays, passes, runs, the neutral pass rate (win probability 20-80%, quarters 1-3) and seconds a play; per season:
    each rusher's and each defense's carries by direction, each receiver's target tree."""
    ix, rd = pbp_rows(season, cur)
    g = lambda r, c: r[ix[c]]
    per = defaultdict(lambda: {"long_comp": None, "long_rush": None, "long_rec": None, "rz_tgt": 0, "rz_rush": 0, "deep_tgt": 0})
    team = defaultdict(lambda: {"plays": 0, "pass": 0, "rush": 0, "npass": 0, "nplays": 0, "secs": 0.0, "nsec": 0})
    rdir = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))       # (kind, key) -> dir -> [att, yds, td]
    tree = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))       # pid -> cell -> [tgt, rec, yds]
    last_t = {}
    for r in rd:
        if g(r, "season_type") != "REG" and g(r, "season_type") != "POST":
            continue
        pt = g(r, "play_type")
        if pt not in ("pass", "run") or g(r, "two_point_attempt") == "1" or g(r, "aborted_play") == "1":
            continue
        gid, pos_t, def_t = g(r, "game_id"), C.team(g(r, "posteam")), C.team(g(r, "defteam"))
        if not pos_t:
            continue
        yl, yds = _n(g(r, "yardline_100")), _z(g(r, "yards_gained"))
        is_pass = g(r, "pass_attempt") == "1" or g(r, "qb_dropback") == "1"
        t = team[(pos_t, gid)]
        t["plays"] += 1
        t["pass" if is_pass else "rush"] += 1
        wp, q = _n(g(r, "wp")), _n(g(r, "qtr"))
        if wp is not None and .2 <= wp <= .8 and q is not None and q <= 3:
            t["nplays"] += 1
            t["npass"] += 1 if is_pass else 0
        gs = _n(g(r, "game_seconds_remaining"))
        k = (pos_t, gid)
        if gs is not None and k in last_t and 0 < last_t[k] - gs < 60:
            t["secs"] += last_t[k] - gs
            t["nsec"] += 1
        if gs is not None:
            last_t[k] = gs
        passer, rcv, rush = (C.pid_of(g(r, c)) for c in ("passer_player_id", "receiver_player_id", "rusher_player_id"))
        if g(r, "pass_attempt") == "1" and g(r, "sack") != "1":
            comp = g(r, "complete_pass") == "1"
            if passer is not None and comp:
                p = per[(passer, gid)]
                p["long_comp"] = max(p["long_comp"] or 0, yds) if p["long_comp"] is not None else yds
            if rcv is not None:
                p = per[(rcv, gid)]
                if comp:
                    p["long_rec"] = max(p["long_rec"], yds) if p["long_rec"] is not None else yds
                if yl is not None and yl <= 20:
                    p["rz_tgt"] += 1
                ay = _n(g(r, "air_yards"))
                if ay is not None and ay >= 20:
                    p["deep_tgt"] += 1
                loc = {"left": "l", "middle": "m", "right": "r"}.get(g(r, "pass_location"))
                if ay is not None and loc:
                    d = "bl" if ay < 0 else "sh" if ay < 10 else "in" if ay < 20 else "dp"
                    c = tree[rcv][d + loc]
                    c[0] += 1
                    if comp:
                        c[1] += 1
                        c[2] += yds
        elif g(r, "rush_attempt") == "1" and rush is not None:
            p = per[(rush, gid)]
            p["long_rush"] = max(p["long_rush"], yds) if p["long_rush"] is not None else yds
            if yl is not None and yl <= 20:
                p["rz_rush"] += 1
            if g(r, "qb_scramble") != "1":
                loc, gap = g(r, "run_location"), g(r, "run_gap")
                d = "m" if loc == "middle" else ({"left": "l", "right": "r"}.get(loc, "") + {"end": "e", "tackle": "t", "guard": "g"}.get(gap, "")
                                                  if loc in ("left", "right") else "")
                if d in DIRS:
                    td = 1 if g(r, "touchdown") == "1" and C.pid_of(g(r, "td_player_id")) == rush else 0
                    for kk in (("p", str(rush)), ("d", def_t or "")):
                        c = rdir[kk][d]
                        c[0] += 1
                        c[1] += yds
                        c[2] += td
    return per, team, rdir, tree


def snap_map(season, cur, roster):
    """{(pid, gid): (offense snaps, share)} — snap counts key on PFR ids, joined through the roster (name + team when a
    PFR id is missing). Defense / kicking rows keep their own unit's snaps."""
    by_pfr = {r["pfr"]: pid for pid, r in roster.items() if r.get("pfr")}
    by_name = defaultdict(set)
    for pid, r in roster.items():
        by_name[(C.nosfx(C.fold(r["name"])), r["team"])].add(pid)
    out = {}
    for r in C.iter_rows(f"snap_counts/snap_counts_{season}.csv", _age(season, cur)):
        pid = by_pfr.get(r.get("pfr_player_id"))
        if pid is None:
            hit = by_name.get((C.nosfx(C.fold(r.get("player"))), C.team(r.get("team"))), set())
            pid = next(iter(hit)) if len(hit) == 1 else None
        if pid is None:
            continue
        off, dfn = _z(r.get("offense_snaps")), _z(r.get("defense_snaps"))
        if off >= dfn:
            out[(pid, r["game_id"])] = (off, _n(r.get("offense_pct")))
        else:
            out[(pid, r["game_id"])] = (dfn, _n(r.get("defense_pct")))
    return out


def build(seasons=None, db=DB, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    sched_all = C.schedule(None, CUR_MAX_AGE)
    cur, _ = C.current_week(sched_all, now)
    seasons = seasons or (cur - 1, cur)
    games = {g["gid"]: g for g in sched_all if g["season"] in seasons}
    con = sqlite3.connect(db)
    con.executescript(DDL)
    meta = {"built_at": now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat(), "seasons": list(seasons)}
    players, names = {}, {}
    for season in seasons:
        roster = C.rosters(season, _age(season, cur))
        if season == cur:
            players = roster
        snaps = snap_map(season, cur, roster)
        per, team, rdir, tree = from_pbp_cached(season, cur)
        stats = weekly(season, cur)
        team_carries = defaultdict(int)
        for r in stats:
            team_carries[(C.team(r.get("team")), r.get("game_id"))] += _z(r.get("carries"))
        rows, last_wk = [], 0
        for r in stats:
            if r.get("season_type") not in ("REG", "POST"):
                continue
            pid, gid, tm = C.pid_of(r.get("player_id")), r.get("game_id"), C.team(r.get("team"))
            g = games.get(gid)
            if pid is None or g is None or tm not in (g["home"], g["away"]):
                continue
            pos = r.get("position") or ""
            grp = r.get("position_group") or ""
            if pos not in OFF_POS and grp not in DEF_GROUPS:
                continue
            home = tm == g["home"]
            pf, pa = (g["home_score"], g["away_score"]) if home else (g["away_score"], g["home_score"])
            sp = None if g["spread"] is None else (-g["spread"] if home else g["spread"])
            x = per.get((pid, gid), {})
            sn = snaps.get((pid, gid), (None, None))
            fgm, pat = _z(r.get("fg_made")), _z(r.get("pat_made"))
            tc = team_carries.get((tm, gid)) or 0
            v = {"date": g["date"], "gid": gid, "week": g["week"], "team": tm, "opp": g["away"] if home else g["home"],
                 "home": 1 if home else 0, "margin": None if pf is None or pa is None else pf - pa,
                 "rest": g["home_rest"] if home else g["away_rest"], "spr": sp, "tot": g["total"],
                 "snaps": sn[0], "snap_pct": None if sn[1] is None else round(sn[1] * 100),
                 "pass_att": _z(r.get("attempts")), "pass_comp": _z(r.get("completions")), "pass_yds": _z(r.get("passing_yards")),
                 "pass_tds": _z(r.get("passing_tds")), "pass_int": _z(r.get("passing_interceptions")),
                 "sacked": _z(r.get("sacks_suffered")), "long_comp": x.get("long_comp"),
                 "rush_att": _z(r.get("carries")), "rush_yds": _z(r.get("rushing_yards")), "rush_tds": _z(r.get("rushing_tds")),
                 "long_rush": x.get("long_rush"), "rush_share": round(_z(r.get("carries")) / tc * 100) if tc else None,
                 "targets": _z(r.get("targets")), "rec": _z(r.get("receptions")), "rec_yds": _z(r.get("receiving_yards")),
                 "rec_tds": _z(r.get("receiving_tds")), "long_rec": x.get("long_rec"),
                 "air_yds": _z(r.get("receiving_air_yards")), "yac": _z(r.get("receiving_yards_after_catch")),
                 "tgt_share": None if _n(r.get("target_share")) is None else round(_n(r.get("target_share")) * 100),
                 "air_share": None if _n(r.get("air_yards_share")) is None else round(_n(r.get("air_yards_share")) * 100),
                 "rz_tgt": x.get("rz_tgt", 0), "rz_rush": x.get("rz_rush", 0), "deep_tgt": x.get("deep_tgt", 0),
                 "td": _z(r.get("rushing_tds")) + _z(r.get("receiving_tds")) + _z(r.get("special_teams_tds")),
                 "fg_made": fgm, "fg_att": _z(r.get("fg_att")), "pat_made": pat, "kick_pts": 3 * fgm + pat,
                 "sacks": _z(r.get("def_sacks")),
                 "tackles": _z(r.get("def_tackles_solo")) + _z(r.get("def_tackle_assists"))}
            # a longest play he had none of is 0 when he played the role (a receiver with no catch, a passer with no
            # completion), so an under at 9.5 yards grades the game he was blanked
            if v["snaps"]:
                if v["long_rec"] is None and pos in ("WR", "TE", "RB", "FB"):
                    v["long_rec"] = 0
                if v["long_rush"] is None and pos in ("RB", "FB", "QB"):
                    v["long_rush"] = 0
                if v["long_comp"] is None and v["pass_att"]:
                    v["long_comp"] = 0
            if pos not in OFF_POS:                       # a defender: only his defense counts (no stray zero rush rows)
                for c in ("pass_att", "pass_comp", "pass_yds", "pass_tds", "pass_int", "sacked", "rush_att", "rush_yds",
                          "rush_tds", "targets", "rec", "rec_yds", "rec_tds", "air_yds", "yac"):
                    v[c] = None if not v[c] else v[c]
            rows.append((season, pid, pos) + tuple(v[c] for c in LOG_COLS))
            names[pid] = (r.get("player_display_name") or r.get("player_name") or "", pos)
            last_wk = max(last_wk, g["week"])
        con.executemany(f"INSERT OR REPLACE INTO logs VALUES ({','.join('?' * (3 + len(LOG_COLS)))})", rows)
        for (tm, gid), t in team.items():
            g = games.get(gid)
            if g is None or tm not in (g["home"], g["away"]):
                continue
            home = tm == g["home"]
            pf, pa = (g["home_score"], g["away_score"]) if home else (g["away_score"], g["home_score"])
            con.execute("INSERT OR REPLACE INTO team_games VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (season, gid, g["week"], g["date"], tm, g["away"] if home else g["home"], 1 if home else 0,
                         t["plays"], t["pass"], t["rush"], round(t["npass"] / t["nplays"], 3) if t["nplays"] else None,
                         round(t["secs"] / t["nsec"], 1) if t["nsec"] else None, pf, pa))
        for (kind, key), cells in rdir.items():
            con.execute("INSERT OR REPLACE INTO rush_dir VALUES (?,?,?,?)",
                        (season, kind, key, json.dumps({d: cells[d] for d in DIRS if d in cells})))
        for pid, cells in tree.items():
            con.execute("INSERT OR REPLACE INTO tgt_tree VALUES (?,?,?)", (season, pid, json.dumps(dict(cells))))
        meta[f"logs_{season}"] = {"rows": len(rows), "last_week": last_wk}
    for pid, r in players.items():
        con.execute("INSERT OR REPLACE INTO players VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, r["name"], r["team"], r["pos"], r["headshot"], r["espn"], r["jersey"], r["depth_pos"], r["status"]))
    con.executemany("INSERT OR REPLACE INTO names VALUES (?,?,?)", [(k, v[0], v[1]) for k, v in names.items()])
    con.execute("INSERT OR REPLACE INTO meta VALUES ('meta', ?)", (json.dumps(meta),))
    con.commit()
    con.close()
    return meta


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()
    tmp = Path(a.db + ".build")
    if tmp.exists():
        tmp.unlink()
    m = build(db=tmp)
    os.replace(tmp, a.db)                       # readers never see a half-built store
    print(f"nfl_stats: {json.dumps(m)}")
